"""
title: Paperless-NGX Dokumentensuche
description: Sucht in Paperless-NGX Dokumenten per Volltext und gibt Inhalte als Kontext zurück
author: home-server
version: 2.0
"""

import time
import requests
from pydantic import BaseModel
from concurrent.futures import ThreadPoolExecutor, as_completed


class Tools:
    class Valves(BaseModel):
        paperless_url: str = "http://192.168.188.130:8000/api"
        paperless_token: str = ""

    def __init__(self):
        self.valves = self.Valves()
        # Tag-Cache: name (lowercase) → id und id → name
        # Wird lazy befüllt und 5 Minuten gecacht
        self._tags_by_name: dict[str, int] = {}
        self._tags_by_id: dict[int, str] = {}
        self._tag_cache_time: float = 0
        self._tag_cache_ttl: float = 300  # 5 Minuten

    # ------------------------------------------------------------------ #
    #  Interne Hilfsmethoden                                               #
    # ------------------------------------------------------------------ #

    def _headers(self) -> dict:
        return {"Authorization": f"Token {self.valves.paperless_token}"}

    def _load_tags(self) -> None:
        """Lädt alle Tags aus Paperless, gecacht für 5 Minuten."""
        if self._tags_by_name and (time.time() - self._tag_cache_time) < self._tag_cache_ttl:
            return
        try:
            resp = requests.get(
                f"{self.valves.paperless_url}/tags/",
                headers=self._headers(),
                params={"page_size": 500},
                timeout=5,
            )
            resp.raise_for_status()
            tags = resp.json().get("results", [])
            self._tags_by_name = {t["name"].lower(): t["id"] for t in tags}
            self._tags_by_id = {t["id"]: t["name"] for t in tags}
            self._tag_cache_time = time.time()
        except Exception:
            pass  # Kein Tag-Cache → weiter ohne Tag-Filter

    def _extract_tag_ids(self, query: str) -> list[int]:
        """Gibt IDs der Tags zurück, deren Name im Query vorkommt."""
        words = {w.lower() for w in query.split() if len(w) > 2}
        return [self._tags_by_name[w] for w in words if w in self._tags_by_name]

    def _fetch(self, params: dict) -> list[dict]:
        """Einzelner API-Call, gibt Dokumentenliste zurück (leer bei Fehler)."""
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
        """Holt Dokumentinhalt via Detail-Endpoint (Fallback wenn content leer)."""
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
        """Formatiert ein Dokument als lesbaren Text-Block für das LLM."""
        doc_id = doc.get("id")
        title = doc.get("title", "Unbekannt")
        created = doc.get("created", "")[:10]
        link = f"{base_url}/documents/{doc_id}/details"

        # Tag-IDs → lesbare Namen (aus Cache)
        raw_tags = doc.get("tags", [])
        tag_names = [self._tags_by_id.get(t, str(t)) for t in raw_tags]
        tag_line = f"🏷️ Tags: {', '.join(tag_names)}\n" if tag_names else ""

        content = doc.get("content", "").strip()
        if not content:
            content = self._fetch_content(doc_id)

        return (
            f"**{title}** ({created})\n"
            f"📄 [In Paperless öffnen]({link})\n"
            f"{tag_line}\n"
            f"{content[:5000]}"
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
        bevorzuge Jahresdokumente gegenüber Monatsdokumenten, indem du
        explizit "Jahres" oder die amtliche Bezeichnung im Query verwendest.

        Wenn eine Suche kein passendes Ergebnis liefert, rufe das Tool
        erneut mit einem alternativen Fachbegriff auf.

        :param query: Offizielle Dokumentbezeichnung + Schlüsselwörter (z.B. "Lohnsteuerbescheinigung 2025 Bosch")
        :return: Dokumenteninhalt als Text
        """
        base_url = self.valves.paperless_url.rstrip("/").removesuffix("/api")

        # Tags laden (gecacht, ~50ms beim ersten Mal)
        self._load_tags()
        matched_tag_ids = self._extract_tag_ids(query)

        # ── Primäre Suchen (immer parallel) ──────────────────────────────
        #
        # Suche A: Volltext + Relevanz-Sortierung (immer)
        # Suche B: Volltext + Tag-Filter + Relevanz (nur wenn Tags erkannt)
        #
        primary_searches = [
            {"query": query, "page_size": 10, "ordering": "__relevance__"},
        ]
        if matched_tag_ids:
            primary_searches.append({
                "query": query,
                "page_size": 10,
                "ordering": "__relevance__",
                "tags__id__in": ",".join(str(i) for i in matched_tag_ids),
            })

        docs_by_id: dict[int, dict] = {}

        with ThreadPoolExecutor(max_workers=len(primary_searches)) as ex:
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
                fallback_searches.append(
                    {"query": kw, "page_size": 5, "ordering": "__relevance__"}
                )
                fallback_searches.append(
                    {"title__icontains": kw, "page_size": 5, "ordering": "__relevance__"}
                )

            with ThreadPoolExecutor(max_workers=min(len(fallback_searches), 6)) as ex:
                futures = {ex.submit(self._fetch, p): p for p in fallback_searches}
                for future in as_completed(futures):
                    for doc in future.result():
                        doc_id = doc.get("id")
                        if doc_id not in docs_by_id:
                            docs_by_id[doc_id] = doc

        if not docs_by_id:
            return f"Keine Dokumente zu '{query}' gefunden."

        # Maximal 8 Dokumente zurückgeben (Relevanz-Reihenfolge durch dict-Insertion)
        docs = list(docs_by_id.values())[:8]
        results = [self._format_doc(doc, base_url) for doc in docs]
        return "\n\n---\n\n".join(results)