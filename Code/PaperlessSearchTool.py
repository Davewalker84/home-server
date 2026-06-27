"""
title: Paperless-NGX Dokumentensuche
description: Sucht in Paperless-NGX Dokumenten per Volltext und gibt Inhalte als Kontext zurück
author: home-server
version: 3.0
"""

import re
import time
import requests
from pydantic import BaseModel
from concurrent.futures import ThreadPoolExecutor, as_completed


class Tools:
    class Valves(BaseModel):
        paperless_url: str = "http://192.168.188.130:8000/api"
        paperless_token: str = ""
        max_docs: int = 5
        content_head_chars: int = 4000
        content_tail_chars: int = 3000

    def __init__(self):
        self.valves = self.Valves()
        self._tags_by_name: dict[str, int] = {}
        self._tags_by_id: dict[int, str] = {}
        self._tag_cache_time: float = 0

        self._corr_by_name: dict[str, int] = {}
        self._corr_by_id: dict[int, str] = {}
        self._corr_cache_time: float = 0

        self._dtype_by_name: dict[str, int] = {}
        self._dtype_by_id: dict[int, str] = {}
        self._dtype_cache_time: float = 0

        self._cache_ttl: float = 300  # 5 Minuten

    # ------------------------------------------------------------------ #
    #  Interne Hilfsmethoden                                               #
    # ------------------------------------------------------------------ #

    def _headers(self) -> dict:
        return {"Authorization": f"Token {self.valves.paperless_token}"}

    def _load_cache(self, endpoint: str, name_key: str = "name") -> list[dict]:
        try:
            resp = requests.get(
                f"{self.valves.paperless_url}/{endpoint}/",
                headers=self._headers(),
                params={"page_size": 500},
                timeout=5,
            )
            resp.raise_for_status()
            return resp.json().get("results", [])
        except Exception:
            return []

    def _load_tags(self) -> None:
        if self._tags_by_name and (time.time() - self._tag_cache_time) < self._cache_ttl:
            return
        items = self._load_cache("tags")
        if items:
            self._tags_by_name = {t["name"].lower(): t["id"] for t in items}
            self._tags_by_id = {t["id"]: t["name"] for t in items}
            self._tag_cache_time = time.time()

    def _load_correspondents(self) -> None:
        if self._corr_by_name and (time.time() - self._corr_cache_time) < self._cache_ttl:
            return
        items = self._load_cache("correspondents")
        if items:
            self._corr_by_name = {c["name"].lower(): c["id"] for c in items}
            self._corr_by_id = {c["id"]: c["name"] for c in items}
            self._corr_cache_time = time.time()

    def _load_document_types(self) -> None:
        if self._dtype_by_name and (time.time() - self._dtype_cache_time) < self._cache_ttl:
            return
        items = self._load_cache("document_types")
        if items:
            self._dtype_by_name = {d["name"].lower(): d["id"] for d in items}
            self._dtype_by_id = {d["id"]: d["name"] for d in items}
            self._dtype_cache_time = time.time()

    def _match_in_query(self, query_lower: str, name_map: dict[str, int]) -> list[int]:
        """Findet alle Einträge aus name_map, deren Name als Substring im Query vorkommt."""
        return [id_ for name, id_ in name_map.items() if name in query_lower and len(name) > 2]

    def _extract_years(self, query: str) -> list[str]:
        return re.findall(r'\b(20\d{2})\b', query)

    def _fetch(self, params: dict) -> list[dict]:
        try:
            resp = requests.get(
                f"{self.valves.paperless_url}/documents/",
                headers=self._headers(),
                params=params,
                timeout=10,
            )
            resp.raise_for_status()
            return resp.json().get("results", [])
        except Exception:
            return []

    def _fetch_content(self, doc_id: int) -> str:
        try:
            resp = requests.get(
                f"{self.valves.paperless_url}/documents/{doc_id}/",
                headers=self._headers(),
                timeout=10,
            )
            resp.raise_for_status()
            return resp.json().get("content", "")
        except Exception:
            return ""

    def _format_doc(self, doc: dict, base_url: str) -> str:
        doc_id = doc.get("id")
        title = doc.get("title", "Unbekannt")
        created = doc.get("created", "")[:10]
        link = f"{base_url}/documents/{doc_id}/details"

        tag_names = [self._tags_by_id.get(t, str(t)) for t in doc.get("tags", [])]
        tag_line = f"🏷️ Tags: {', '.join(tag_names)}\n" if tag_names else ""

        corr_id = doc.get("correspondent")
        corr_line = f"👤 Korrespondent: {self._corr_by_id.get(corr_id, str(corr_id))}\n" if corr_id else ""

        dtype_id = doc.get("document_type")
        dtype_line = f"📁 Typ: {self._dtype_by_id.get(dtype_id, str(dtype_id))}\n" if dtype_id else ""

        content = doc.get("content", "").strip()
        head = self.valves.content_head_chars
        tail = self.valves.content_tail_chars
        if len(content) <= head + tail:
            truncated = content
        else:
            truncated = content[:head] + "\n\n[...]\n\n" + content[-tail:]

        return (
            f"**{title}** ({created})\n"
            f"📄 [In Paperless öffnen]({link})\n"
            f"{corr_line}"
            f"{dtype_line}"
            f"{tag_line}\n"
            f"{truncated}"
        )

    # ------------------------------------------------------------------ #
    #  Haupt-Suchmethode                                                   #
    # ------------------------------------------------------------------ #

    def search_paperless(self, query: str) -> str:
        """
        Sucht in Paperless-NGX Dokumenten und gibt Inhalte zurück.
        Dieses Tool MUSS bei jeder neuen Dokumentenfrage aufgerufen
        werden, auch bei Folgefragen im selben Chat.

        WICHTIG – Suchbegriffe normalisieren:
        Übersetze umgangssprachliche oder englische Begriffe IMMER in
        offizielle deutsche Dokumentbezeichnungen, bevor du suchst.
        Das Paperless-Archiv verwendet amtliche Bezeichnungen.

        Typische Übersetzungen (nicht abschließend, nutze dein Wissen):
        - "Einkommensteuer Bescheinigung" → "Lohnsteuerbescheinigung"
        - "Gehaltsabrechnung", "Lohnzettel" → "Entgeltabrechnung"
        - "Steuerbescheid" → "Einkommensteuerbescheid"
        - "Kindergeld Antrag" → "Antrag auf Kindergeld"
        - "Elterngeld Bescheid" → "Bescheid über Elterngeld"
        - "Krankenversicherung Nachweis" → "Versicherungsbescheinigung"
        - "Arbeitsvertrag" → "Anstellungsvertrag" oder "Arbeitsvertrag"
        - "Rentenversicherung Nachweis" → "Versicherungsverlauf"

        Wenn der Nutzer nach einem Jahreswert fragt (z.B. Einkommen 2025),
        füge das Jahr explizit in den Query ein – das Tool filtert dann
        automatisch auf diesen Jahrgang.

        Erkannte Korrespondenten (Firmen, Behörden) und Dokumententypen
        werden automatisch als Suchfilter ergänzt.

        Wenn eine Suche kein passendes Ergebnis liefert, rufe das Tool
        erneut mit einem alternativen Fachbegriff auf.

        :param query: Offizielle Dokumentbezeichnung + Schlüsselwörter (z.B. "Lohnsteuerbescheinigung 2025 Bosch")
        :return: Dokumenteninhalt als Text
        """
        base_url = self.valves.paperless_url.rstrip("/").removesuffix("/api")
        query_lower = query.lower()

        # Alle Metadaten-Caches laden (parallel, ~50ms beim ersten Mal)
        with ThreadPoolExecutor(max_workers=3) as ex:
            ex.submit(self._load_tags)
            ex.submit(self._load_correspondents)
            ex.submit(self._load_document_types)

        matched_tag_ids = self._match_in_query(query_lower, self._tags_by_name)
        matched_corr_ids = self._match_in_query(query_lower, self._corr_by_name)
        matched_dtype_ids = self._match_in_query(query_lower, self._dtype_by_name)

        # Datumsfilter aus Jahresangaben im Query
        date_params: dict = {}
        years = self._extract_years(query)
        if years:
            year = years[-1]
            date_params["created__date__gte"] = f"{year}-01-01"
            date_params["created__date__lte"] = f"{year}-12-31"

        # ── Primäre Suchen (parallel) ─────────────────────────────────────
        #
        # A: Volltext + Relevanz (immer)
        # B: Titel-Substring + Relevanz (immer)
        # C: Volltext + Tag-Filter (wenn Tags erkannt)
        # D: Volltext + Korrespondent-Filter (wenn Korrespondent erkannt)
        # E: Volltext + Dokumententyp-Filter (wenn Typ erkannt)
        #
        base_query_params = {"query": query, "page_size": 10, "ordering": "__relevance__", **date_params}

        primary_searches = [
            base_query_params,
            {"title__icontains": query, "page_size": 10, "ordering": "__relevance__", **date_params},
        ]
        for tag_id in matched_tag_ids:
            primary_searches.append({**base_query_params, "tags__id__in": str(tag_id)})
        for corr_id in matched_corr_ids:
            primary_searches.append({**base_query_params, "correspondent__id": str(corr_id)})
        for dtype_id in matched_dtype_ids:
            primary_searches.append({**base_query_params, "document_type__id": str(dtype_id)})

        docs_by_id: dict[int, dict] = {}

        with ThreadPoolExecutor(max_workers=min(len(primary_searches), 8)) as ex:
            futures = {ex.submit(self._fetch, p): p for p in primary_searches}
            for future in as_completed(futures):
                for doc in future.result():
                    doc_id = doc.get("id")
                    if doc_id not in docs_by_id:
                        docs_by_id[doc_id] = doc

        # ── Keyword-Fallback (nur wenn Primärsuchen nichts liefern) ──────
        if not docs_by_id:
            keywords = [w for w in query.split() if len(w) > 3]
            fallback_searches = []
            for kw in keywords[:4]:
                fallback_searches.append({"query": kw, "page_size": 5, "ordering": "__relevance__"})
                fallback_searches.append({"title__icontains": kw, "page_size": 5})

            with ThreadPoolExecutor(max_workers=min(len(fallback_searches), 6)) as ex:
                futures = {ex.submit(self._fetch, p): p for p in fallback_searches}
                for future in as_completed(futures):
                    for doc in future.result():
                        doc_id = doc.get("id")
                        if doc_id not in docs_by_id:
                            docs_by_id[doc_id] = doc

        if not docs_by_id:
            return f"Keine Dokumente zu '{query}' gefunden."

        docs = list(docs_by_id.values())[: self.valves.max_docs]

        # ── Content parallel nachladen (für Dokumente ohne Content) ──────
        docs_needing_content = [d for d in docs if not d.get("content", "").strip()]
        if docs_needing_content:
            with ThreadPoolExecutor(max_workers=min(len(docs_needing_content), 4)) as ex:
                future_to_doc = {ex.submit(self._fetch_content, d["id"]): d for d in docs_needing_content}
                for future in as_completed(future_to_doc):
                    doc = future_to_doc[future]
                    content = future.result()
                    if content:
                        doc["content"] = content

        results = [self._format_doc(doc, base_url) for doc in docs]
        return "\n\n---\n\n".join(results)
