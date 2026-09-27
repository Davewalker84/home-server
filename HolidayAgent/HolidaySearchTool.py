"""
title: Urlaubsplaner – Unterkunftssuche
description: Durchsucht Google Hotels (inkl. Ferienhäuser) und Booking.com, berechnet Lage-Distanzen via OpenStreetMap und rankt Unterkünfte für Familien
author: home-server
version: 1.0
requirements: requests
"""

import re
import json
import math
import time
import uuid
import sqlite3
import asyncio
import hashlib
import logging
import tempfile
import unicodedata
from pathlib import Path
from datetime import date
from threading import Lock
from urllib.parse import quote, urlencode

import requests
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

SERPAPI_URL = "https://serpapi.com/search.json"
BOOKING_HOST = "booking-com15.p.rapidapi.com"
NOMINATIM_URL = "https://nominatim.openstreetmap.org/search"
# Öffentliche Overpass-Instanzen sind oft überlastet (504/429) → der Reihe nach probieren
OVERPASS_URLS = [
    "https://overpass-api.de/api/interpreter",
    "https://overpass.private.coffee/api/interpreter",
    "https://maps.mail.ru/osm/tools/overpass/api/interpreter",
]

# OSM-Tags für familienrelevante POIs (Label → Overpass-Filter)
FAMILY_POIS = {
    "Spielplatz": '["leisure"="playground"]',
    "Strand": '["natural"="beach"]',
    "Supermarkt": '["shop"="supermarket"]',
    "Parkhaus/Parkplatz": '["amenity"="parking"]',
    "ÖPNV-Haltestelle": '["public_transport"="station"]',
    "Kinderarzt/Apotheke": '["amenity"~"pharmacy|doctors"]',
    "Zoo/Aquarium/Freizeitpark": '["tourism"~"zoo|aquarium|theme_park"]',
    "E-Ladestation": '["amenity"="charging_station"]',
}

# OSM socket-Tags → lesbarer Steckername
EV_SOCKETS = {
    "type2_combo": "CCS",
    "type2": "Typ 2",
    "chademo": "CHAdeMO",
    "tesla_supercharger": "Tesla SC",
    "schuko": "Schuko",
}
# Ausstattungs-Text der Portale, der auf eine Ladestation an der Unterkunft hinweist
EV_AMENITY_RE = re.compile(r"lade|charg|\bEV\b|elektroauto|electric vehicle", re.IGNORECASE)


class Tools:
    class Valves(BaseModel):
        serpapi_key: str = Field("", description="SerpAPI Key (Google Hotels)")
        rapidapi_key: str = Field("", description="RapidAPI Key (Booking.com15 API)")
        nominatim_user_agent: str = Field(
            "home-server-holiday-agent/1.0 (private use)",
            description="User-Agent für OSM Nominatim/Overpass (Pflicht laut OSM Policy)",
        )
        currency: str = "EUR"
        language: str = "de"
        country: str = "de"

        min_rating_10: float = Field(8.5, description="Mindestbewertung auf 10er-Skala (4,25/5)")
        min_reviews: int = Field(20, description="Mindestanzahl Bewertungen")
        min_bedrooms_with_children: int = Field(2, description="Separate Schlafzimmer bei Kindern")
        max_location_km: float = Field(6.0, description="Ab dieser Distanz zum Sightseeing-Schwerpunkt = 0 Lagepunkte")
        ev_radius_m: int = Field(1500, description="Suchradius für E-Ladestationen um die Unterkunft (Anreise mit Auto)")

        weight_rating: float = 0.35
        weight_reviews: float = 0.20
        weight_location: float = 0.25
        weight_price: float = 0.20

        max_results: int = Field(10, description="Anzahl Unterkünfte im finalen Ranking")
        max_results_per_search: int = Field(30, description="Max. Treffer pro Quelle")
        cache_ttl_hours: int = Field(24, description="Gleiche Suche innerhalb dieser Zeit verbraucht keine API-Quote")

    def __init__(self):
        self.valves = self.Valves()
        self._db_lock = Lock()
        self._nominatim_lock = Lock()
        self._last_nominatim = 0.0
        self._db_path = self._resolve_db_path()

    # ------------------------------------------------------------------ #
    #  Cache / Ergebnis-Speicher (SQLite)                                  #
    # ------------------------------------------------------------------ #

    def _resolve_db_path(self) -> str:
        data_dir = Path("/app/backend/data")
        if not data_dir.is_dir():
            data_dir = Path(tempfile.gettempdir())
        return str(data_dir / "holiday_cache.db")

    def _db(self) -> sqlite3.Connection:
        con = sqlite3.connect(self._db_path)
        con.execute("CREATE TABLE IF NOT EXISTS cache (key TEXT PRIMARY KEY, ts REAL, value TEXT)")
        con.execute("CREATE TABLE IF NOT EXISTS results (id TEXT PRIMARY KEY, ts REAL, value TEXT)")
        return con

    def _cache_get(self, key: str):
        ttl = self.valves.cache_ttl_hours * 3600
        with self._db_lock, self._db() as con:
            row = con.execute("SELECT ts, value FROM cache WHERE key = ?", (key,)).fetchone()
        if row and time.time() - row[0] < ttl:
            return json.loads(row[1])
        return None

    def _cache_set(self, key: str, value) -> None:
        with self._db_lock, self._db() as con:
            con.execute(
                "INSERT OR REPLACE INTO cache VALUES (?, ?, ?)",
                (key, time.time(), json.dumps(value)),
            )

    def _store_results(self, listings: list[dict]) -> str:
        result_id = uuid.uuid4().hex[:8]
        with self._db_lock, self._db() as con:
            con.execute("DELETE FROM results WHERE ts < ?", (time.time() - 7 * 86400,))
            con.execute(
                "INSERT INTO results VALUES (?, ?, ?)",
                (result_id, time.time(), json.dumps(listings)),
            )
        return result_id

    def _load_results(self, result_id: str) -> list[dict]:
        with self._db_lock, self._db() as con:
            row = con.execute("SELECT value FROM results WHERE id = ?", (result_id.strip(),)).fetchone()
        return json.loads(row[0]) if row else []

    def _cached_get(self, url: str, params: dict, headers: dict | None = None, timeout: int = 30):
        """GET mit SQLite-Cache. API-Keys fließen nicht in den Cache-Key ein."""
        key_params = {k: v for k, v in params.items() if k != "api_key"}
        key = hashlib.sha256(f"{url}|{json.dumps(key_params, sort_keys=True)}".encode()).hexdigest()
        cached = self._cache_get(key)
        if cached is not None:
            return cached
        resp = requests.get(url, params=params, headers=headers or {}, timeout=timeout)
        resp.raise_for_status()
        data = resp.json()
        self._cache_set(key, data)
        return data

    # ------------------------------------------------------------------ #
    #  Hilfsfunktionen                                                     #
    # ------------------------------------------------------------------ #

    @staticmethod
    async def _status(emitter, text: str, done: bool = False) -> None:
        if emitter:
            await emitter({"type": "status", "data": {"description": text, "done": done}})

    @staticmethod
    def _ages(children_ages: str) -> list[int]:
        return [int(a) for a in re.findall(r"\d+", children_ages or "")]

    @staticmethod
    def _nights(check_in: str, check_out: str) -> int:
        return max(1, (date.fromisoformat(check_out) - date.fromisoformat(check_in)).days)

    @staticmethod
    def _haversine_km(lat1, lon1, lat2, lon2) -> float:
        r = 6371.0
        p1, p2 = math.radians(lat1), math.radians(lat2)
        dp, dl = p2 - p1, math.radians(lon2 - lon1)
        a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
        return 2 * r * math.asin(math.sqrt(a))

    @staticmethod
    def _parse_bedrooms(texts) -> int | None:
        for t in texts or []:
            m = re.search(r"(\d+)\s*(bedroom|schlafzimmer)", str(t), re.IGNORECASE)
            if m:
                return int(m.group(1))
        return None

    @staticmethod
    def _norm_name(name: str) -> str:
        ascii_name = unicodedata.normalize("NFKD", name or "").encode("ascii", "ignore").decode()
        return re.sub(r"[^a-z0-9]", "", ascii_name.lower())

    @staticmethod
    def _fmt_listing_line(i: int, l: dict) -> str:
        rating = f"{l['rating_10']:.1f}/10" if l.get("rating_10") is not None else "–"
        beds = l.get("bedrooms") if l.get("bedrooms") is not None else "?"
        price = f"{l['total_price']:.0f} €" if l.get("total_price") else "–"
        return f"{i}. {l['name']} | {l['source']} | {price} gesamt | {rating} ({l.get('reviews') or 0} Bew.) | SZ: {beds} | {l.get('type') or ''}"

    def _geocode(self, place: str) -> dict | None:
        key = hashlib.sha256(f"nominatim|{place.lower()}".encode()).hexdigest()
        cached = self._cache_get(key)
        if cached is not None:
            return cached or None
        with self._nominatim_lock:  # OSM Policy: max. 1 Request/Sekunde
            wait = 1.1 - (time.time() - self._last_nominatim)
            if wait > 0:
                time.sleep(wait)
            try:
                resp = requests.get(
                    NOMINATIM_URL,
                    params={"q": place, "format": "json", "limit": 1, "accept-language": self.valves.language},
                    headers={"User-Agent": self.valves.nominatim_user_agent},
                    timeout=15,
                )
                resp.raise_for_status()
                hits = resp.json()
            except Exception as e:
                logger.error("Nominatim failed (%s): %s", place, e)
                return None
            finally:
                self._last_nominatim = time.time()
        result = (
            {"name": place, "lat": float(hits[0]["lat"]), "lon": float(hits[0]["lon"]), "display": hits[0]["display_name"]}
            if hits
            else {}
        )
        self._cache_set(key, result)
        return result or None

    def _geocode_many(self, places: str, destination: str) -> list[dict]:
        found = []
        for p in [x.strip() for x in re.split(r"[;\n]", places or "") if x.strip()]:
            hit = self._geocode(f"{p}, {destination}") if destination else None
            hit = hit or self._geocode(p)
            if hit:
                found.append(hit)
        return found

    def _overpass(self, query: str) -> list[dict]:
        """Overpass-Abfrage mit SQLite-Cache."""
        key = hashlib.sha256(f"overpass|{query}".encode()).hexdigest()
        cached = self._cache_get(key)
        if cached is not None:
            return cached
        last_error = None
        for url in OVERPASS_URLS:
            try:
                resp = requests.post(
                    url, data={"data": query},
                    headers={"User-Agent": self.valves.nominatim_user_agent}, timeout=40,
                )
                resp.raise_for_status()
                data = resp.json().get("elements", [])
                self._cache_set(key, data)
                return data
            except Exception as e:
                logger.warning("Overpass %s failed: %s", url, e)
                last_error = e
        raise RuntimeError(f"alle Overpass-Server nicht erreichbar ({last_error})")

    @staticmethod
    def _el_coords(el: dict):
        return (
            el.get("lat") or (el.get("center") or {}).get("lat"),
            el.get("lon") or (el.get("center") or {}).get("lon"),
        )

    @staticmethod
    def _charger_info(tags: dict) -> dict:
        """Wertet OSM-Tags einer Ladestation aus: Stecker, max. Leistung, Betreiber, Zugang."""
        sockets, max_kw = [], 0.0
        for osm, label in EV_SOCKETS.items():
            count = tags.get(f"socket:{osm}")
            if count and count != "no":
                sockets.append(f"{count}× {label}" if count.isdigit() else label)
            for num in re.findall(r"[\d.]+", tags.get(f"socket:{osm}:output", "")):
                try:
                    max_kw = max(max_kw, float(num))
                except ValueError:
                    pass
        access = tags.get("access", "")
        return {
            "name": tags.get("name") or tags.get("operator") or tags.get("network") or "Ladestation",
            "operator": tags.get("operator") or tags.get("network") or "",
            "sockets": ", ".join(sockets) or "Stecker unbekannt",
            "max_kw": max_kw or None,
            "capacity": tags.get("capacity"),
            "fee": {"yes": "kostenpflichtig", "no": "kostenlos"}.get(tags.get("fee", ""), ""),
            "access": {"customers": "nur für Gäste/Kunden", "private": "privat"}.get(access, ""),
            "opening_hours": tags.get("opening_hours", ""),
            "private": access in ("private", "no"),
        }

    def _chargers_near(self, points: list[tuple[float, float]], radius_m: int) -> list[dict]:
        """Alle öffentlich nutzbaren Ladestationen im Umkreis mehrerer Punkte (eine Abfrage)."""
        parts = "".join(f'nwr["amenity"="charging_station"](around:{radius_m},{lat},{lon});' for lat, lon in points)
        elements = self._overpass(f"[out:json][timeout:25];({parts});out center tags;")
        chargers = []
        for el in elements:
            lat, lon = self._el_coords(el)
            info = self._charger_info(el.get("tags", {}))
            if lat is not None and not info["private"]:
                chargers.append({**info, "lat": lat, "lon": lon})
        return chargers

    def _ev_summary(self, lat, lon, chargers: list[dict], radius_m: int) -> str:
        near = sorted(
            ((self._haversine_km(lat, lon, c["lat"], c["lon"]) * 1000, c) for c in chargers),
            key=lambda x: x[0],
        )
        near = [(d, c) for d, c in near if d <= radius_m]
        if not near:
            return f"keine ≤ {radius_m / 1000:.1f} km"
        d, c = near[0]
        kw = f" · {c['max_kw']:.0f} kW" if c["max_kw"] else ""
        fastest = max((c2["max_kw"] or 0 for _, c2 in near), default=0)
        fast = f", schnellste {fastest:.0f} kW" if fastest and fastest != (c["max_kw"] or 0) else ""
        return f"{d:.0f} m{kw} ({len(near)} im Umkreis{fast})"

    # ------------------------------------------------------------------ #
    #  Quellen                                                             #
    # ------------------------------------------------------------------ #

    def _google_hotels(self, destination, check_in, check_out, adults, ages, vacation_rentals, max_price_total, min_bedrooms):
        params = {
            "engine": "google_hotels",
            "q": destination,
            "check_in_date": check_in,
            "check_out_date": check_out,
            "adults": adults,
            "currency": self.valves.currency,
            "hl": self.valves.language,
            "gl": self.valves.country,
            "api_key": self.valves.serpapi_key,
        }
        if ages:
            params["children"] = len(ages)
            params["children_ages"] = ",".join(str(a) for a in ages)
        if vacation_rentals:
            params["vacation_rentals"] = "true"
            if min_bedrooms:
                params["bedrooms"] = min_bedrooms
        if max_price_total:
            params["max_price"] = int(max_price_total / self._nights(check_in, check_out))

        data = self._cached_get(SERPAPI_URL, params)
        if data.get("error"):
            raise RuntimeError(data["error"])

        listings = []
        for p in data.get("properties", [])[: self.valves.max_results_per_search]:
            gps = p.get("gps_coordinates") or {}
            total = (p.get("total_rate") or {}).get("extracted_lowest")
            rating = p.get("overall_rating")
            listings.append({
                "name": p.get("name"),
                "source": "Google Ferienhäuser" if vacation_rentals else "Google Hotels",
                "type": p.get("type") or ("Ferienunterkunft" if vacation_rentals else "Hotel"),
                "url": p.get("link") or f"https://www.google.com/travel/search?q={quote(p.get('name', '') + ' ' + destination)}",
                "total_price": total,
                "rating_10": rating * 2 if rating is not None else None,
                "reviews": p.get("reviews"),
                "bedrooms": self._parse_bedrooms(p.get("essential_info")),
                "lat": gps.get("latitude"),
                "lon": gps.get("longitude"),
                "amenities": (p.get("amenities") or [])[:8],
            })
        return listings

    def _booking(self, destination, check_in, check_out, adults, ages):
        headers = {"x-rapidapi-key": self.valves.rapidapi_key, "x-rapidapi-host": BOOKING_HOST}
        dest = self._cached_get(
            f"https://{BOOKING_HOST}/api/v1/hotels/searchDestination", {"query": destination}, headers
        ).get("data") or []
        if not dest:
            raise RuntimeError(f"Booking kennt das Ziel '{destination}' nicht")

        params = {
            "dest_id": dest[0].get("dest_id"),
            "search_type": dest[0].get("search_type"),
            "arrival_date": check_in,
            "departure_date": check_out,
            "adults": adults,
            "room_qty": 1,
            "page_number": 1,
            "units": "metric",
            "temperature_unit": "c",
            "languagecode": self.valves.language,
            "currency_code": self.valves.currency,
        }
        if ages:
            params["children_age"] = ",".join(str(a) for a in ages)
        data = self._cached_get(f"https://{BOOKING_HOST}/api/v1/hotels/searchHotels", params, headers)

        link_params = {
            "checkin": check_in,
            "checkout": check_out,
            "group_adults": adults,
            "group_children": len(ages),
            "no_rooms": 1,
        }
        listings = []
        for h in ((data.get("data") or {}).get("hotels") or [])[: self.valves.max_results_per_search]:
            p = h.get("property") or {}
            total = ((p.get("priceBreakdown") or {}).get("grossPrice") or {}).get("value")
            label = h.get("accessibilityLabel") or ""
            query = urlencode({"ss": f"{p.get('name', '')} {destination}", **link_params})
            listings.append({
                "name": p.get("name"),
                "source": "Booking.com",
                "type": "Apartment" if re.search(r"apartment|wohnung", label, re.I) else "Hotel/Unterkunft",
                "url": f"https://www.booking.com/searchresults.de.html?{query}"
                + "".join(f"&age={a}" for a in ages),
                "total_price": total,
                "rating_10": p.get("reviewScore"),
                "reviews": p.get("reviewCount"),
                "bedrooms": self._parse_bedrooms([label]),
                "lat": p.get("latitude"),
                "lon": p.get("longitude"),
                "amenities": [],
            })
        return listings

    # ------------------------------------------------------------------ #
    #  Tool-Methoden (für das LLM sichtbar)                                #
    # ------------------------------------------------------------------ #

    async def search_accommodations(
        self,
        destination: str,
        check_in: str,
        check_out: str,
        adults: int,
        children_ages: str = "",
        max_price_total: float = 0,
        __event_emitter__=None,
    ) -> str:
        """
        Sucht verfügbare Unterkünfte parallel in Google Hotels, Google Ferienhäusern
        (Vrbo, Fewo-Portale u.a.) und Booking.com für den Reisezeitraum.
        Liefert eine result_id, die anschließend an rank_accommodations übergeben wird.
        AirBnB wird NICHT hier, sondern über das separate AirBnB-Tool gesucht.
        :param destination: Stadt, Stadtteil oder Region, z.B. "Lissabon Belém" oder "Zingst, Ostsee"
        :param check_in: Anreisedatum im Format YYYY-MM-DD
        :param check_out: Abreisedatum im Format YYYY-MM-DD
        :param adults: Anzahl Erwachsene
        :param children_ages: Alter der Kinder kommagetrennt, z.B. "5,8" (leer wenn keine Kinder)
        :param max_price_total: Budget für den gesamten Aufenthalt in EUR (0 = kein Limit)
        :return: result_id und kompakte Trefferliste je Quelle
        """
        ages = self._ages(children_ages)
        min_bedrooms = self.valves.min_bedrooms_with_children if ages else 0
        await self._status(__event_emitter__, f"Suche Unterkünfte in {destination} …")

        jobs = {}
        if self.valves.serpapi_key:
            jobs["Google Hotels"] = asyncio.to_thread(
                self._google_hotels, destination, check_in, check_out, adults, ages, False, max_price_total, 0
            )
            jobs["Google Ferienhäuser"] = asyncio.to_thread(
                self._google_hotels, destination, check_in, check_out, adults, ages, True, max_price_total, min_bedrooms
            )
        if self.valves.rapidapi_key:
            jobs["Booking.com"] = asyncio.to_thread(self._booking, destination, check_in, check_out, adults, ages)

        errors = []
        if not self.valves.serpapi_key:
            errors.append("Google Hotels/Ferienhäuser: kein SerpAPI-Key hinterlegt")
        if not self.valves.rapidapi_key:
            errors.append("Booking.com: kein RapidAPI-Key hinterlegt")

        results = await asyncio.gather(*jobs.values(), return_exceptions=True)
        listings, per_source = [], {}
        for source, res in zip(jobs.keys(), results):
            if isinstance(res, Exception):
                logger.error("%s failed: %s", source, res)
                errors.append(f"{source}: {res}")
                continue
            per_source[source] = res
            listings.extend(res)

        result_id = self._store_results(listings)
        await self._status(__event_emitter__, f"{len(listings)} Unterkünfte gefunden", done=True)

        out = [f"result_id: {result_id}", f"Treffer gesamt: {len(listings)}"]
        for source, items in per_source.items():
            out.append(f"\n### {source} ({len(items)} Treffer)")
            top = sorted(items, key=lambda l: l.get("rating_10") or 0, reverse=True)[:10]
            out += [self._fmt_listing_line(i, l) for i, l in enumerate(top, 1)]
        if errors:
            out.append("\n⚠️ Nicht verfügbare Quellen (dem Nutzer mitteilen):\n- " + "\n- ".join(errors))
        return "\n".join(out)

    async def geocode_places(self, places: str, destination: str = "", __event_emitter__=None) -> str:
        """
        Ermittelt Koordinaten für Sehenswürdigkeiten oder Orte und berechnet deren
        geografischen Schwerpunkt. Nutzen, um die beste Wohnlage zu begründen.
        :param places: Orte, getrennt durch Semikolon, z.B. "Torre de Belém; Alfama; Oceanário"
        :param destination: Stadt/Region zur Eingrenzung, z.B. "Lissabon"
        :return: Koordinaten je Ort, Schwerpunkt und Entfernungen der Orte zum Schwerpunkt
        """
        await self._status(__event_emitter__, "Suche Orte auf der Karte …")
        hits = await asyncio.to_thread(self._geocode_many, places, destination)
        await self._status(__event_emitter__, f"{len(hits)} Orte gefunden", done=True)
        if not hits:
            return "Keine der Orte gefunden. Bitte Namen präzisieren."
        lat = sum(h["lat"] for h in hits) / len(hits)
        lon = sum(h["lon"] for h in hits) / len(hits)
        lines = [f"Schwerpunkt: {lat:.5f}, {lon:.5f}"]
        for h in hits:
            d = self._haversine_km(lat, lon, h["lat"], h["lon"])
            lines.append(f"- {h['name']}: {h['lat']:.5f}, {h['lon']:.5f} ({d:.1f} km vom Schwerpunkt) – {h['display']}")
        return "\n".join(lines)

    async def find_family_pois(
        self, latitude: float, longitude: float, radius_m: int = 1000, __event_emitter__=None
    ) -> str:
        """
        Zählt familienrelevante Orte (Spielplätze, Strände, Supermärkte, Parkplätze,
        ÖPNV, Apotheken, Zoos, E-Ladestationen) im Umkreis eines Punktes. Nutzen, um Stadtteile oder
        die Umgebung einer konkreten Unterkunft zu bewerten.
        :param latitude: Breitengrad
        :param longitude: Längengrad
        :param radius_m: Suchradius in Metern (Standard 1000)
        :return: Anzahl je Kategorie und nächstgelegener Treffer mit Distanz
        """
        await self._status(__event_emitter__, "Prüfe Umgebung (OpenStreetMap) …")
        parts = "".join(
            f'nwr{flt}(around:{radius_m},{latitude},{longitude});' for flt in FAMILY_POIS.values()
        )
        query = f"[out:json][timeout:25];({parts});out center tags;"
        try:
            elements = await asyncio.to_thread(self._overpass, query)
        except Exception as e:
            await self._status(__event_emitter__, "Umgebungsprüfung fehlgeschlagen", done=True)
            return f"OpenStreetMap-Abfrage fehlgeschlagen: {e}"

        def matches(tags: dict, flt: str) -> bool:
            for k, op, v in re.findall(r'\["([^"]+)"(=|~)"([^"]+)"\]', flt):
                val = tags.get(k, "")
                if (op == "=" and val != v) or (op == "~" and not re.fullmatch(v, val)):
                    return False
            return True

        lines = [f"Umgebung im Radius {radius_m} m:"]
        for label, flt in FAMILY_POIS.items():
            hits = []
            for el in elements:
                if matches(el.get("tags", {}), flt):
                    lat, lon = self._el_coords(el)
                    if lat is not None:
                        hits.append((self._haversine_km(latitude, longitude, lat, lon), el["tags"].get("name", "")))
            if hits:
                d, name = min(hits)
                lines.append(f"- {label}: {len(hits)} (nächster: {name or 'ohne Name'}, {d * 1000:.0f} m)")
            else:
                lines.append(f"- {label}: keine")
        await self._status(__event_emitter__, "Umgebung geprüft", done=True)
        return "\n".join(lines)

    async def find_ev_chargers(
        self, latitude: float, longitude: float, radius_m: int = 3000, __event_emitter__=None
    ) -> str:
        """
        Listet E-Ladestationen (Elektroauto) im Umkreis eines Punktes mit Steckertyp,
        maximaler Ladeleistung, Betreiber, Kosten und Zugang. Nutzen bei Anreise mit dem
        Auto für eine konkrete Unterkunft oder einen Ort.
        :param latitude: Breitengrad
        :param longitude: Längengrad
        :param radius_m: Suchradius in Metern (Standard 3000)
        :return: die nächsten Ladestationen und die schnellsten Schnelllader im Umkreis
        """
        await self._status(__event_emitter__, "Suche E-Ladestationen (OpenStreetMap) …")
        try:
            chargers = await asyncio.to_thread(self._chargers_near, [(latitude, longitude)], radius_m)
        except Exception as e:
            await self._status(__event_emitter__, "Ladestationssuche fehlgeschlagen", done=True)
            return f"OpenStreetMap-Abfrage fehlgeschlagen: {e}"
        await self._status(__event_emitter__, f"{len(chargers)} Ladestationen gefunden", done=True)
        if not chargers:
            return f"Keine öffentlichen Ladestationen im Umkreis von {radius_m} m in OpenStreetMap erfasst."

        for c in chargers:
            c["dist_m"] = self._haversine_km(latitude, longitude, c["lat"], c["lon"]) * 1000

        def line(c: dict) -> str:
            details = [c["sockets"]]
            if c["max_kw"]:
                details.append(f"bis {c['max_kw']:.0f} kW")
            if c["capacity"]:
                details.append(f"{c['capacity']} Ladepunkte")
            details += [x for x in (c["fee"], c["access"], c["opening_hours"]) if x]
            op = f" ({c['operator']})" if c["operator"] and c["operator"] != c["name"] else ""
            maps = f"https://www.openstreetmap.org/?mlat={c['lat']:.5f}&mlon={c['lon']:.5f}#map=18/{c['lat']:.5f}/{c['lon']:.5f}"
            return f"- {c['dist_m']:.0f} m – {c['name']}{op}: {', '.join(details)} – [Karte]({maps})"

        nearest = sorted(chargers, key=lambda c: c["dist_m"])[:5]
        fast = sorted([c for c in chargers if (c["max_kw"] or 0) >= 50], key=lambda c: c["dist_m"])[:3]
        out = [f"{len(chargers)} öffentliche Ladestationen im Umkreis von {radius_m} m.", "\nNächste Ladestationen:"]
        out += [line(c) for c in nearest]
        if fast:
            out.append("\nSchnelllader (≥ 50 kW):")
            out += [line(c) for c in fast]
        else:
            out.append("\nKein Schnelllader (≥ 50 kW) mit erfasster Leistung im Umkreis.")
        out.append("\nHinweis: Daten aus OpenStreetMap – Verfügbarkeit und Preise vor Ort bzw. in der Lade-App prüfen.")
        return "\n".join(out)

    async def rank_accommodations(
        self,
        result_ids: str,
        budget_total: float = 0,
        sights: str = "",
        destination: str = "",
        has_children: bool = True,
        travel_by_car: bool = False,
        extra_listings_json: str = "",
        __event_emitter__=None,
    ) -> str:
        """
        Filtert und rankt alle gefundenen Unterkünfte deterministisch nach Bewertung,
        Anzahl Bewertungen, Lage (Distanz zu den Sehenswürdigkeiten) und Preis.
        Entfernt Dubletten über mehrere Portale. Das Ergebnis ist die Grundlage der
        Empfehlungstabelle – Preise und Links nur von hier übernehmen.
        :param result_ids: result_id(s) aus search_accommodations, kommagetrennt
        :param budget_total: Budget für den gesamten Aufenthalt in EUR (0 = kein Limit)
        :param sights: geplante Sehenswürdigkeiten/Ziele getrennt durch Semikolon (leer = Lage neutral)
        :param destination: Stadt/Region zur Eingrenzung der Ortssuche
        :param has_children: True wenn Kinder mitreisen (aktiviert Schlafzimmer-Filter)
        :param travel_by_car: True bei Anreise mit dem Auto (ergänzt E-Ladestationen an/nahe jeder Unterkunft)
        :param extra_listings_json: AirBnB-Ergebnisse als JSON-Liste mit Objekten {"name","url","total_price","rating","rating_scale" (5 oder 10),"reviews","bedrooms","lat","lon"}
        :return: Ranking-Tabelle (Markdown) und Liste ausgefilterter Treffer mit Grund
        """
        v = self.valves
        await self._status(__event_emitter__, "Bewerte und ranke Unterkünfte …")

        listings = []
        for rid in [r for r in re.split(r"[,\s]+", result_ids or "") if r]:
            listings.extend(self._load_results(rid))

        if extra_listings_json:
            try:
                extra = json.loads(extra_listings_json)
                for e in extra if isinstance(extra, list) else []:
                    rating, scale = e.get("rating"), e.get("rating_scale") or 5
                    listings.append({
                        "name": e.get("name"),
                        "source": e.get("source") or "AirBnB",
                        "type": e.get("type") or "Ferienunterkunft",
                        "url": e.get("url"),
                        "total_price": e.get("total_price"),
                        "rating_10": float(rating) * (10 / float(scale)) if rating is not None else None,
                        "reviews": e.get("reviews"),
                        "bedrooms": e.get("bedrooms"),
                        "lat": e.get("lat"),
                        "lon": e.get("lon"),
                        "amenities": e.get("amenities") or [],
                    })
            except (ValueError, TypeError) as e:
                return f"extra_listings_json ist kein gültiges JSON: {e}"

        if not listings:
            return "Keine Unterkünfte zum Ranken vorhanden (result_ids prüfen)."

        centroid = None
        if sights:
            hits = await asyncio.to_thread(self._geocode_many, sights, destination)
            if hits:
                centroid = (sum(h["lat"] for h in hits) / len(hits), sum(h["lon"] for h in hits) / len(hits))

        # Harte Filter
        min_bedrooms = v.min_bedrooms_with_children if has_children else 0
        kept, dropped = [], []
        for l in listings:
            reason = None
            if not l.get("total_price"):
                reason = "kein Preis → vermutlich nicht verfügbar"
            elif budget_total and l["total_price"] > budget_total:
                reason = f"über Budget ({l['total_price']:.0f} €)"
            elif l.get("rating_10") is None or l["rating_10"] < v.min_rating_10:
                reason = f"Bewertung zu niedrig ({l.get('rating_10') or '–'})"
            elif (l.get("reviews") or 0) < v.min_reviews:
                reason = f"zu wenige Bewertungen ({l.get('reviews') or 0})"
            elif min_bedrooms and l.get("bedrooms") is not None and l["bedrooms"] < min_bedrooms:
                reason = f"nur {l['bedrooms']} Schlafzimmer"
            if reason:
                dropped.append((l, reason))
            else:
                kept.append(l)

        # Dubletten zusammenführen (gleicher Name oder < 150 m bei ähnlichem Namen) → günstigstes Angebot behalten
        merged: list[dict] = []
        for l in sorted(kept, key=lambda x: x["total_price"]):
            dup = None
            for m in merged:
                same_name = self._norm_name(m["name"]) == self._norm_name(l["name"])
                close = (
                    None not in (m.get("lat"), m.get("lon"), l.get("lat"), l.get("lon"))
                    and self._haversine_km(m["lat"], m["lon"], l["lat"], l["lon"]) < 0.15
                    and self._norm_name(l["name"])[:8] == self._norm_name(m["name"])[:8]
                )
                if same_name or close:
                    dup = m
                    break
            if dup:
                dup.setdefault("also_on", []).append(f"{l['source']} ({l['total_price']:.0f} €)")
            else:
                merged.append(dict(l))

        # Score
        prices = [l["total_price"] for l in merged]
        p_min, p_max = (min(prices), max(prices)) if prices else (0, 0)
        for l in merged:
            s_rating = max(0.0, min(1.0, (l["rating_10"] - v.min_rating_10) / max(0.1, 10 - v.min_rating_10)))
            s_reviews = min(1.0, math.log10(max(1, l.get("reviews") or 1)) / math.log10(500))
            if centroid and l.get("lat") is not None and l.get("lon") is not None:
                l["distance_km"] = self._haversine_km(centroid[0], centroid[1], l["lat"], l["lon"])
                s_loc = max(0.0, 1 - l["distance_km"] / v.max_location_km)
            else:
                s_loc = 0.5
            if budget_total:
                s_price = max(0.0, 1 - l["total_price"] / budget_total) * 2  # 50 % des Budgets = volle Punkte
                s_price = min(1.0, s_price)
            else:
                s_price = 1 - (l["total_price"] - p_min) / (p_max - p_min) if p_max > p_min else 1.0
            l["score"] = round(100 * (
                v.weight_rating * s_rating + v.weight_reviews * s_reviews
                + v.weight_location * s_loc + v.weight_price * s_price
            ) / (v.weight_rating + v.weight_reviews + v.weight_location + v.weight_price), 1)

        ranked = sorted(merged, key=lambda x: x["score"], reverse=True)[: v.max_results]

        # E-Laden: Hinweis aus der Portal-Ausstattung + nächste Ladestation laut OSM (eine Abfrage für alle)
        ev_error = None
        if travel_by_car:
            await self._status(__event_emitter__, "Prüfe E-Ladestationen an den Unterkünften …")
            points = [(l["lat"], l["lon"]) for l in ranked if l.get("lat") is not None and l.get("lon") is not None]
            chargers = []
            if points:
                try:
                    chargers = await asyncio.to_thread(self._chargers_near, points, v.ev_radius_m)
                except Exception as e:
                    ev_error = str(e)
            for l in ranked:
                on_site = any(EV_AMENITY_RE.search(str(a)) for a in l.get("amenities") or [])
                if l.get("lat") is None or l.get("lon") is None or ev_error:
                    near = "unbekannt"
                else:
                    near = self._ev_summary(l["lat"], l["lon"], chargers, v.ev_radius_m)
                l["ev"] = ("⚡ an Unterkunft laut Portal; " if on_site else "") + near

        await self._status(__event_emitter__, f"{len(ranked)} Unterkünfte im Ranking", done=True)

        out = [
            f"Ranking ({len(ranked)} von {len(listings)} Treffern, {len(dropped)} ausgefiltert"
            + (", Lage relativ zum Sightseeing-Schwerpunkt" if centroid else ", Lage nicht bewertet") + ")\n",
            "| # | Unterkunft | Portal | Gesamtpreis | Bewertung | Bewertungen | Schlafzimmer | Distanz |"
            + (" E-Laden (nächste) |" if travel_by_car else "") + " Score | Link |",
            "|---|---|---|---|---|---|---|---|" + ("---|" if travel_by_car else "") + "---|---|",
        ]
        for i, l in enumerate(ranked, 1):
            beds = l.get("bedrooms") if l.get("bedrooms") is not None else "prüfen"
            dist = f"{l['distance_km']:.1f} km" if "distance_km" in l else "–"
            portal = l["source"] + (f" (auch: {', '.join(l['also_on'])})" if l.get("also_on") else "")
            out.append(
                f"| {i} | {l['name']} | {portal} | {l['total_price']:.0f} € | {l['rating_10']:.1f}/10 | "
                f"{l.get('reviews') or 0} | {beds} | {dist} | "
                + (f"{l['ev']} | " if travel_by_car else "")
                + f"{l['score']} | [Ansehen]({l.get('url') or ''}) |"
            )
        if travel_by_car:
            out.append(
                f"\nE-Laden: öffentliche Ladestationen ≤ {v.ev_radius_m / 1000:.1f} km laut OpenStreetMap"
                + (f" – Abfrage fehlgeschlagen: {ev_error}" if ev_error else "")
                + ". Details zu einer Unterkunft mit find_ev_chargers."
            )
        if any(l.get("amenities") for l in ranked):
            out.append("\nAusstattung (Auszug):")
            out += [f"- {l['name']}: {', '.join(l['amenities'])}" for l in ranked if l.get("amenities")]
        if dropped:
            out.append("\nAusgefiltert (Auszug):")
            out += [f"- {l.get('name')} ({l.get('source')}): {r}" for l, r in dropped[:15]]
        return "\n".join(out)

    def build_deeplinks(
        self, destination: str, check_in: str, check_out: str, adults: int, children_ages: str = ""
    ) -> str:
        """
        Erzeugt vorausgefüllte Such-Links für Portale ohne API-Anbindung
        (Fewo-direkt, HomeToGo, Interhome) sowie für AirBnB, Booking und Google Hotels,
        damit der Nutzer selbst weitersuchen kann.
        :param destination: Stadt oder Region
        :param check_in: Anreisedatum YYYY-MM-DD
        :param check_out: Abreisedatum YYYY-MM-DD
        :param adults: Anzahl Erwachsene
        :param children_ages: Alter der Kinder kommagetrennt, z.B. "5,8"
        :return: Markdown-Liste mit Links
        """
        ages = self._ages(children_ages)
        d = quote(destination)
        persons = adults + len(ages)
        nights = self._nights(check_in, check_out)
        booking = urlencode({
            "ss": destination, "checkin": check_in, "checkout": check_out,
            "group_adults": adults, "group_children": len(ages), "no_rooms": 1,
        }) + "".join(f"&age={a}" for a in ages)
        airbnb = urlencode({
            "checkin": check_in, "checkout": check_out, "adults": adults, "children": len(ages),
            **({"min_bedrooms": self.valves.min_bedrooms_with_children} if ages else {}),
        })
        vrbo_children = ",".join(f"1_{a}" for a in ages)
        fewo = urlencode({
            "destination": destination, "startDate": check_in, "endDate": check_out, "adults": adults,
            **({"children": vrbo_children} if ages else {}),
        })
        links = [
            f"- [AirBnB](https://www.airbnb.de/s/{d}/homes?{airbnb})",
            f"- [Booking.com](https://www.booking.com/searchresults.de.html?{booking})",
            f"- [Google Hotels](https://www.google.com/travel/search?q={quote(f'{destination} {check_in} bis {check_out}')})",
            f"- [Fewo-direkt](https://www.fewo-direkt.de/search?{fewo})",
            f"- [HomeToGo](https://www.hometogo.de/search/{d}?arrival={check_in}&duration={nights}&persons={persons})",
            f"- [Interhome](https://www.interhome.de/suche/?q={d})",
        ]
        return "Such-Links (Filter werden je nach Portal ggf. nicht alle übernommen):\n" + "\n".join(links)
