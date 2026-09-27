"""
title: Urlaubsplaner – Unterkunftssuche
description: Sucht in einem Aufruf Google Hotels, Google Ferienhäuser, AirBnB (via mcpo) und optional Booking.com, rankt die Treffer für Familien und ergänzt Lage- und E-Lade-Infos aus OpenStreetMap
author: home-server
version: 2.0
requirements: requests
"""

import re
import json
import math
import time
import sqlite3
import asyncio
import hashlib
import logging
import tempfile
import unicodedata
from pathlib import Path
from datetime import date
from threading import Lock
from collections import Counter
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

SRC_GOOGLE = "Google Hotels"
SRC_GOOGLE_VR = "Google Ferienhäuser"
SRC_BOOKING = "Booking.com"
SRC_AIRBNB = "AirBnB"

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
EV_FAST_KW = 50
# Ausstattungs-Text der Portale, der auf eine Ladestation an der Unterkunft hinweist
EV_AMENITY_RE = re.compile(r"lade|charg|\bEV\b|elektroauto|electric vehicle", re.IGNORECASE)

CURRENCY_SYMBOLS = {"€": "EUR", "$": "USD", "£": "GBP", "CHF": "CHF", "EUR": "EUR", "USD": "USD", "GBP": "GBP"}
# Zahl inkl. Tausendertrennern (1,234 / 1.234 / 1'234 / 1 234 mit geschütztem Leerzeichen)
_NUM = r"\d[\d.,'’\u00a0\u202f]*"
AMOUNT_RE = re.compile(rf"(€|\$|£|EUR|USD|GBP|CHF)\s?({_NUM})|({_NUM})\s?(€|\$|£|EUR|USD|GBP|CHF)")


class Tools:
    class Valves(BaseModel):
        serpapi_key: str = Field("", description="SerpAPI Key (Google Hotels + Ferienhäuser) – Hauptquelle")
        rapidapi_key: str = Field("", description="Optional: RapidAPI Key (Booking.com15). Leer = Booking wird übersprungen")
        mcpo_url: str = Field("http://mcpo:8000", description="mcpo-Basis-URL (AirBnB unter /airbnb). Leer = AirBnB wird übersprungen")
        mcpo_api_key: str = Field("", description="API-Key von mcpo (MCPO_API_KEY)")
        airbnb_entire_home_only: bool = Field(True, description="AirBnB nur ganze Unterkünfte (keine Privatzimmer)")
        nominatim_user_agent: str = Field(
            "home-server-holiday-agent/2.0 (private use)",
            description="User-Agent für OSM Nominatim/Overpass – App-Name, gern mit Kontakt-Mail",
        )
        currency: str = "EUR"
        language: str = "de"
        country: str = "de"

        # Mindestbewertung je Quelle – die Skalen sind unterschiedlich verteilt (AirBnB: Median ≈ 4,8)
        min_rating_google_5: float = Field(4.3, description="Google: Mindestbewertung (von 5)")
        min_rating_booking_10: float = Field(8.5, description="Booking: Mindestbewertung (von 10)")
        min_rating_airbnb_5: float = Field(4.8, description="AirBnB: Mindestbewertung (von 5)")
        min_reviews: int = Field(20, description="Mindestanzahl Bewertungen")
        min_bedrooms_with_children: int = Field(2, description="Separate Schlafzimmer bei Kindern")
        max_distance_km: float = Field(
            15.0, description="Umkreis um den Zielort; weiter entfernte Unterkünfte fliegen raus (bei großen Regionen automatisch größer, 0 = aus)"
        )
        location_tolerance_km: float = Field(
            4.0, description="Ø-Distanz zu den Zielen: so viele km schlechter als die bestgelegene Unterkunft = 0 Lagepunkte"
        )
        ev_radius_m: int = Field(1500, description="Umkreis für 'Ladestation in Laufweite' (Anreise mit Auto)")
        ev_fast_radius_m: int = Field(5000, description="Umkreis für den nächsten Schnelllader ≥ 50 kW")

        weight_rating: float = 0.35
        weight_reviews: float = 0.20
        weight_location: float = 0.25
        weight_price: float = 0.20

        max_results: int = Field(10, description="Anzahl Unterkünfte im Ranking")
        max_results_per_source: int = Field(30, description="Max. Treffer pro Quelle")
        cache_ttl_hours: int = Field(24, description="Gleiche Suche innerhalb dieser Zeit verbraucht keine API-Quote")

    def __init__(self):
        self.valves = self.Valves()
        self._db_lock = Lock()
        self._nominatim_lock = Lock()
        self._last_nominatim = 0.0
        self._db_path = self._resolve_db_path()

    # ------------------------------------------------------------------ #
    #  Cache (SQLite)                                                      #
    # ------------------------------------------------------------------ #

    def _resolve_db_path(self) -> str:
        data_dir = Path("/app/backend/data")
        if not data_dir.is_dir():
            data_dir = Path(tempfile.gettempdir())
        return str(data_dir / "holiday_cache.db")

    def _db(self) -> sqlite3.Connection:
        con = sqlite3.connect(self._db_path)
        con.execute("CREATE TABLE IF NOT EXISTS cache (key TEXT PRIMARY KEY, ts REAL, value TEXT)")
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

    @staticmethod
    def _cache_key(*parts) -> str:
        return hashlib.sha256(json.dumps(parts, sort_keys=True).encode()).hexdigest()

    def _cached_get(self, url: str, params: dict, headers: dict | None = None, timeout: int = 30):
        """GET mit SQLite-Cache. API-Keys fließen nicht in den Cache-Key ein."""
        key = self._cache_key("GET", url, {k: v for k, v in params.items() if k != "api_key"})
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
        for t in texts or []:
            if re.search(r"\bstudio\b", str(t), re.IGNORECASE):
                return 1  # Studio = kein separates Schlafzimmer
        return None

    @staticmethod
    def _norm_name(name: str) -> str:
        ascii_name = unicodedata.normalize("NFKD", name or "").encode("ascii", "ignore").decode()
        return re.sub(r"[^a-z0-9]", "", ascii_name.lower())

    @staticmethod
    def _parse_number(raw: str) -> float | None:
        """'1,234.50' / '1.234,50' / '1234' → float."""
        s = re.sub(r"['’\u00a0\u202f]", "", raw).strip().rstrip(".,")
        if "," in s and "." in s:
            dec = "," if s.rfind(",") > s.rfind(".") else "."
            s = s.replace("." if dec == "," else ",", "").replace(dec, ".")
        elif "," in s or "." in s:
            sep = "," if "," in s else "."
            head, _, tail = s.rpartition(sep)
            s = s.replace(sep, "") if len(tail) == 3 else head.replace(sep, "") + "." + tail
        try:
            return float(s)
        except ValueError:
            return None

    @classmethod
    def _parse_amount(cls, text: str) -> tuple[float | None, str | None]:
        m = AMOUNT_RE.search(text or "")
        if not m:
            return None, None
        sym, num = (m.group(1), m.group(2)) if m.group(1) else (m.group(4), m.group(3))
        return cls._parse_number(num), CURRENCY_SYMBOLS.get(sym)

    @staticmethod
    def _strings(obj) -> list[str]:
        """Alle String-Werte eines verschachtelten Objekts (für robustes Parsen von Scraper-Daten)."""
        if isinstance(obj, str):
            return [obj]
        if isinstance(obj, dict):
            return [s for v in obj.values() for s in Tools._strings(v)]
        if isinstance(obj, list):
            return [s for v in obj for s in Tools._strings(v)]
        return []

    def _rating_rule(self, source: str) -> tuple[float, float]:
        """(Mindestbewertung, Skala) je Quelle."""
        v = self.valves
        if source == SRC_BOOKING:
            return v.min_rating_booking_10, 10.0
        if source == SRC_AIRBNB:
            return v.min_rating_airbnb_5, 5.0
        return v.min_rating_google_5, 5.0

    def _geocode(self, place: str) -> dict | None:
        key = self._cache_key("nominatim", place.lower())
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
        result = {}
        if hits:
            h = hits[0]
            result = {
                "name": place, "lat": float(h["lat"]), "lon": float(h["lon"]), "display": h["display_name"],
                "osm_class": h.get("class", ""),
            }
            bb = h.get("boundingbox")  # [süd, nord, west, ost]
            if bb and len(bb) == 4:
                south, north, west, east = map(float, bb)
                result["radius_km"] = self._haversine_km(south, west, north, east) / 2
        self._cache_set(key, result)
        return result or None

    def _geocode_many(self, places: str, destination: str) -> list[dict]:
        found = []
        for p in [x.strip() for x in re.split(r"[;\n]", places or "") if x.strip()]:
            hit = self._geocode(f"{p}, {destination}") if destination else None
            hit = hit or self._geocode(p)
            if hit:
                found.append({**hit, "name": p})
        return found

    def _mean_distance(self, lat, lon, sights: list[dict]) -> float:
        return sum(self._haversine_km(lat, lon, s["lat"], s["lon"]) for s in sights) / len(sights)

    def _best_point(self, sights: list[dict]) -> tuple[float, float]:
        """Punkt mit minimaler mittlerer Distanz zu allen Zielen (geometrischer Median, Weiszfeld)."""
        lat = sum(s["lat"] for s in sights) / len(sights)
        lon = sum(s["lon"] for s in sights) / len(sights)
        for _ in range(50):
            w = [1 / max(self._haversine_km(lat, lon, s["lat"], s["lon"]), 1e-3) for s in sights]
            lat = sum(wi * s["lat"] for wi, s in zip(w, sights)) / sum(w)
            lon = sum(wi * s["lon"] for wi, s in zip(w, sights)) / sum(w)
        return lat, lon

    # ------------------------------------------------------------------ #
    #  OpenStreetMap Overpass / E-Laden                                    #
    # ------------------------------------------------------------------ #

    def _overpass(self, query: str) -> list[dict]:
        """Overpass-Abfrage mit SQLite-Cache und Ausweich-Servern."""
        key = self._cache_key("overpass", query)
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
        elements = self._overpass(f"[out:json][timeout:40];({parts});out center tags;")
        chargers = []
        for el in elements:
            lat, lon = self._el_coords(el)
            info = self._charger_info(el.get("tags", {}))
            if lat is not None and not info["private"]:
                chargers.append({**info, "lat": lat, "lon": lon})
        return chargers

    def _ev_summary(self, lat, lon, chargers: list[dict]) -> str:
        v = self.valves
        dist = sorted(
            ((self._haversine_km(lat, lon, c["lat"], c["lon"]) * 1000, c) for c in chargers),
            key=lambda x: x[0],
        )
        walk = [(d, c) for d, c in dist if d <= v.ev_radius_m]
        fast = next(((d, c) for d, c in dist if (c["max_kw"] or 0) >= EV_FAST_KW and d <= v.ev_fast_radius_m), None)
        if walk:
            d, c = walk[0]
            kw = f" · {c['max_kw']:.0f} kW" if c["max_kw"] else ""
            text = f"{d:.0f} m{kw} ({len(walk)} ≤ {v.ev_radius_m / 1000:.1f} km)"
        else:
            text = f"keine ≤ {v.ev_radius_m / 1000:.1f} km"
        if fast:
            text += f"; Schnelllader {fast[0] / 1000:.1f} km ({fast[1]['max_kw']:.0f} kW)"
        return text

    # ------------------------------------------------------------------ #
    #  Quellen → einheitliches Listing-Format                              #
    #  {name, source, type, url, total_price, currency, price_ok,          #
    #   price_note, rating, reviews, bedrooms, lat, lon, amenities}        #
    # ------------------------------------------------------------------ #

    def _google_hotels(self, destination, check_in, check_out, adults, ages, vacation_rentals, min_bedrooms):
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
            params["children_ages"] = ",".join(str(max(1, a)) for a in ages)  # SerpAPI: 1–17
        if vacation_rentals:
            params["vacation_rentals"] = "true"
            if min_bedrooms:
                params["bedrooms"] = min_bedrooms

        data = self._cached_get(SERPAPI_URL, params)
        if data.get("error"):
            raise RuntimeError(data["error"])

        source = SRC_GOOGLE_VR if vacation_rentals else SRC_GOOGLE
        listings = []
        for p in data.get("properties", [])[: self.valves.max_results_per_source]:
            gps = p.get("gps_coordinates") or {}
            total = p.get("total_rate") or {}
            listings.append({
                "name": p.get("name"),
                "source": source,
                "type": p.get("type") or ("Ferienunterkunft" if vacation_rentals else "Hotel"),
                "url": p.get("link") or f"https://www.google.com/travel/search?q={quote(p.get('name', '') + ' ' + destination)}",
                "total_price": total.get("extracted_lowest"),
                "currency": self.valves.currency,
                # SerpAPI weist Preise ohne Steuern separat aus (before_taxes_fees) → total_rate ist inkl.
                "price_ok": total.get("extracted_lowest") is not None,
                "price_note": "",
                "rating": p.get("overall_rating"),
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

        link_params = urlencode({
            "checkin": check_in, "checkout": check_out,
            "group_adults": adults, "group_children": len(ages), "no_rooms": 1,
        }) + "".join(f"&age={a}" for a in ages)
        listings = []
        for h in ((data.get("data") or {}).get("hotels") or [])[: self.valves.max_results_per_source]:
            p = h.get("property") or {}
            pb = p.get("priceBreakdown") or {}
            gross = (pb.get("grossPrice") or {}).get("value")
            excluded = (pb.get("excludedPrice") or {}).get("value")
            currency = (pb.get("grossPrice") or {}).get("currency") or self.valves.currency
            label = h.get("accessibilityLabel") or ""
            total, note = gross, ""
            if gross is not None and excluded:
                total, note = gross + excluded, "inkl. separat ausgewiesener Steuern/Gebühren"
            elif gross is not None and excluded is None:
                note = "ggf. zzgl. Kurtaxe"
            listings.append({
                "name": p.get("name"),
                "source": SRC_BOOKING,
                "type": "Apartment" if re.search(r"apartment|wohnung", label, re.I) else "Hotel/Unterkunft",
                "url": f"https://www.booking.com/searchresults.de.html?ss={quote(p.get('name', '') + ' ' + destination)}&{link_params}",
                "total_price": total,
                "currency": currency,
                "price_ok": total is not None and currency == self.valves.currency,
                "price_note": note,
                "rating": p.get("reviewScore"),
                "reviews": p.get("reviewCount"),
                "bedrooms": self._parse_bedrooms([label]),
                "lat": p.get("latitude"),
                "lon": p.get("longitude"),
                "amenities": [],
            })
        return listings

    def _mcpo_airbnb_search(self, payload: dict):
        """Ruft airbnb_search über mcpo (OpenAPI-Proxy des MCP-Servers) auf."""
        v = self.valves
        key = self._cache_key("airbnb", payload)
        cached = self._cache_get(key)
        if cached is not None:
            return cached
        headers = {"Authorization": f"Bearer {v.mcpo_api_key}"} if v.mcpo_api_key else {}
        resp = requests.post(f"{v.mcpo_url.rstrip('/')}/airbnb/airbnb_search", json=payload, headers=headers, timeout=90)
        resp.raise_for_status()
        data = resp.json()
        # mcpo liefert den Text-Content des MCP-Tools – je nach Version als String, Liste oder schon geparst
        if isinstance(data, list) and data:
            data = data[0]
        if isinstance(data, dict) and "text" in data and "searchResults" not in data:
            data = data["text"]
        if isinstance(data, str):
            data = json.loads(data)
        if not isinstance(data, dict):
            raise RuntimeError("unerwartete Antwort von mcpo")
        if data.get("error"):
            raise RuntimeError(data["error"])
        self._cache_set(key, data)
        return data

    def _airbnb(self, destination, check_in, check_out, adults, ages):
        payload = {
            "location": destination,
            "checkin": check_in,
            "checkout": check_out,
            "adults": adults,
            "children": len([a for a in ages if a >= 2]),
            "infants": len([a for a in ages if a < 2]),
        }
        if self.valves.airbnb_entire_home_only:
            payload["propertyType"] = "entire_home"
        data = self._mcpo_airbnb_search(payload)

        nights = self._nights(check_in, check_out)
        guest_params = urlencode({
            "check_in": check_in, "check_out": check_out,
            "adults": adults, "children": payload["children"], "infants": payload["infants"],
        })
        listings = []
        for r in (data.get("searchResults") or [])[: self.valves.max_results_per_source]:
            dsl = r.get("demandStayListing") or {}
            coord = ((dsl.get("location") or {}).get("coordinate")) or {}
            name_obj = (dsl.get("description") or {}).get("name")
            name = next(iter(self._strings(name_obj)), None) or f"AirBnB-Inserat {r.get('id')}"

            rating_label = r.get("avgRatingA11yLabel") or ""
            m_rating = re.search(r"([\d.,]+)\s*(out of|von)\s*5", rating_label)
            m_reviews = re.search(r"(\d[\d.,]*)\s*(reviews?|Bewertung)", rating_label)

            # Preis: bevorzugt Gesamtpreis ("… total"), sonst pro Nacht × Nächte → dann "Preis prüfen"
            price_texts = self._strings(r.get("structuredDisplayPrice"))
            total, currency, price_ok, note = None, None, False, ""
            for t in price_texts:
                if re.search(r"\btotal\b|insgesamt|gesamt", t, re.I):
                    total, currency = self._parse_amount(t)
                    if total is not None:
                        price_ok = True
                        if re.search(r"before tax|vor steuern|excl", t, re.I):
                            note = "zzgl. Steuern"
                        break
            if total is None:
                for t in price_texts:
                    if re.search(r"night|nacht", t, re.I):
                        per_night, currency = self._parse_amount(t)
                        if per_night is not None:
                            total, note = per_night * nights, "hochgerechnet aus Preis pro Nacht"
                            break
            if currency and currency != self.valves.currency:
                price_ok, note = False, (note + "; " if note else "") + f"in {currency}"

            listings.append({
                "name": name,
                "source": SRC_AIRBNB,
                "type": "Ferienunterkunft",
                "url": f"https://www.airbnb.de/rooms/{r.get('id')}?{guest_params}",
                "total_price": total,
                "currency": currency or self.valves.currency,
                "price_ok": price_ok,
                "price_note": note,
                "rating": self._parse_number(m_rating.group(1)) if m_rating else None,
                "reviews": int(self._parse_number(m_reviews.group(1)) or 0) if m_reviews else 0,
                "bedrooms": self._parse_bedrooms(self._strings(r.get("structuredContent"))),
                "lat": coord.get("latitude"),
                "lon": coord.get("longitude"),
                "amenities": [b for b in self._strings(r.get("badges")) if b][:4],
            })
        return listings

    # ------------------------------------------------------------------ #
    #  Ranking                                                             #
    # ------------------------------------------------------------------ #

    def _rank(self, listings: list[dict], budget_total: float, sights: list[dict], has_children: bool,
              center: dict | None = None):
        v = self.valves
        min_bedrooms = v.min_bedrooms_with_children if has_children else 0
        radius = max(v.max_distance_km, (center or {}).get("radius_km", 0)) if center and v.max_distance_km else 0

        # Harte Filter – bei unsicheren Preisen wird nicht nach Budget gefiltert, sondern markiert
        kept, dropped = [], []
        for l in listings:
            min_rating, scale = self._rating_rule(l["source"])
            reason = None
            if (
                radius and l.get("lat") is not None and l.get("lon") is not None
                and self._haversine_km(center["lat"], center["lon"], l["lat"], l["lon"]) > radius
            ):
                reason = f"weiter als {radius:.0f} km vom Zielort"
            elif not l.get("total_price"):
                reason = "kein Preis (vermutlich nicht verfügbar)"
            elif l["price_ok"] and budget_total and l["total_price"] > budget_total:
                reason = "über Budget"
            elif l.get("rating") is None or l["rating"] < min_rating:
                reason = "Bewertung unter Mindestwert"
            elif (l.get("reviews") or 0) < v.min_reviews:
                reason = "zu wenige Bewertungen"
            elif min_bedrooms and l.get("bedrooms") is not None and l["bedrooms"] < min_bedrooms:
                reason = "zu wenige Schlafzimmer"
            if reason:
                dropped.append((l, reason))
            else:
                kept.append(l)

        # Dubletten (gleicher Name oder < 150 m bei ähnlichem Namen) → günstigstes sicheres Angebot behalten
        merged: list[dict] = []
        for l in sorted(kept, key=lambda x: (not x["price_ok"], x["total_price"])):
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
                dup.setdefault("also_on", []).append(f"{l['source']} {l['total_price']:.0f} {l['currency']}")
            else:
                merged.append(dict(l))

        # Lage: mittlere Distanz zu allen Zielen, relativ zur bestgelegenen Unterkunft
        if sights:
            for l in merged:
                if l.get("lat") is not None and l.get("lon") is not None:
                    l["mean_km"] = self._mean_distance(l["lat"], l["lon"], sights)
        best_mean = min((l["mean_km"] for l in merged if "mean_km" in l), default=None)

        sure_prices = [l["total_price"] for l in merged if l["price_ok"]]
        p_min, p_max = (min(sure_prices), max(sure_prices)) if sure_prices else (0, 0)
        for l in merged:
            min_rating, scale = self._rating_rule(l["source"])
            s_rating = max(0.0, min(1.0, (l["rating"] - min_rating) / max(0.01, scale - min_rating)))
            s_reviews = min(1.0, math.log10(max(1, l.get("reviews") or 1)) / math.log10(500))
            if "mean_km" in l:
                s_loc = max(0.0, 1 - (l["mean_km"] - best_mean) / v.location_tolerance_km)
            else:
                s_loc = 0.5
            if not l["price_ok"]:
                s_price = 0.5
            elif budget_total:
                s_price = min(1.0, max(0.0, 1 - l["total_price"] / budget_total) * 2)  # ≤ 50 % Budget = volle Punkte
            else:
                s_price = 1 - (l["total_price"] - p_min) / (p_max - p_min) if p_max > p_min else 1.0
            l["score"] = round(100 * (
                v.weight_rating * s_rating + v.weight_reviews * s_reviews
                + v.weight_location * s_loc + v.weight_price * s_price
            ) / (v.weight_rating + v.weight_reviews + v.weight_location + v.weight_price), 1)

        ranked = sorted(merged, key=lambda x: x["score"], reverse=True)[: v.max_results]
        return ranked, dropped

    def _deeplinks(self, destination, check_in, check_out, adults, ages) -> list[str]:
        d = quote(destination)
        nights = self._nights(check_in, check_out)
        booking = urlencode({
            "ss": destination, "checkin": check_in, "checkout": check_out,
            "group_adults": adults, "group_children": len(ages), "no_rooms": 1,
        }) + "".join(f"&age={a}" for a in ages)
        airbnb = urlencode({
            "checkin": check_in, "checkout": check_out, "adults": adults, "children": len(ages),
            **({"min_bedrooms": self.valves.min_bedrooms_with_children} if ages else {}),
        })
        fewo = urlencode({
            "destination": destination, "startDate": check_in, "endDate": check_out, "adults": adults,
            **({"children": ",".join(f"1_{a}" for a in ages)} if ages else {}),
        })
        return [
            f"[AirBnB](https://www.airbnb.de/s/{d}/homes?{airbnb})",
            f"[Booking.com](https://www.booking.com/searchresults.de.html?{booking})",
            f"[Google Hotels](https://www.google.com/travel/search?q={quote(f'{destination} {check_in} bis {check_out}')})",
            f"[Fewo-direkt](https://www.fewo-direkt.de/search?{fewo})",
            f"[HomeToGo](https://www.hometogo.de/search/{d}?arrival={check_in}&duration={nights}&persons={adults + len(ages)})",
            f"[Interhome](https://www.interhome.de/suche/?q={d})",
        ]

    # ------------------------------------------------------------------ #
    #  Tool-Methoden (für das LLM sichtbar)                                #
    # ------------------------------------------------------------------ #

    async def plan_search(
        self,
        destination: str,
        check_in: str,
        check_out: str,
        adults: int,
        children_ages: str = "",
        budget_total: float = 0,
        sights: str = "",
        travel_by_car: bool = False,
        __event_emitter__=None,
    ) -> str:
        """
        Komplette Unterkunftssuche in EINEM Aufruf: durchsucht Google Hotels, Google
        Ferienhäuser, AirBnB und Booking.com parallel, filtert (Budget, Bewertung,
        Schlafzimmer), entfernt Dubletten, bewertet die Lage relativ zu den
        Sehenswürdigkeiten, ergänzt bei Anreise mit dem Auto E-Ladestationen und liefert
        eine fertige Ranking-Tabelle mit Links. Preise und Links ausschließlich von hier übernehmen.
        :param destination: bestätigter Ort oder Stadtteil, z.B. "Lissabon Baixa" oder "Zingst"
        :param check_in: Anreisedatum im Format YYYY-MM-DD
        :param check_out: Abreisedatum im Format YYYY-MM-DD
        :param adults: Anzahl Erwachsene
        :param children_ages: Alter der Kinder kommagetrennt, z.B. "5,8" (leer wenn keine Kinder)
        :param budget_total: Budget für die Unterkunft für den gesamten Aufenthalt in EUR (0 = kein Limit)
        :param sights: geplante Sehenswürdigkeiten/Ziele getrennt durch Semikolon (leer = Lage neutral)
        :param travel_by_car: True bei Anreise mit dem Auto (ergänzt E-Ladestationen)
        :return: Ranking-Tabelle (Markdown), Status je Quelle, Filterstatistik und Such-Links
        """
        v = self.valves
        try:
            nights = self._nights(check_in, check_out)
        except ValueError:
            return "Ungültiges Datum – bitte check_in/check_out im Format YYYY-MM-DD angeben."
        ages = self._ages(children_ages)
        min_bedrooms = v.min_bedrooms_with_children if ages else 0
        await self._status(__event_emitter__, f"Suche Unterkünfte in {destination} ({nights} Nächte) …")

        jobs, status = {}, {}
        if v.serpapi_key:
            jobs[SRC_GOOGLE] = asyncio.to_thread(
                self._google_hotels, destination, check_in, check_out, adults, ages, False, 0)
            jobs[SRC_GOOGLE_VR] = asyncio.to_thread(
                self._google_hotels, destination, check_in, check_out, adults, ages, True, min_bedrooms)
        else:
            status["Google"] = "übersprungen (kein SerpAPI-Key)"
        if v.mcpo_url:
            jobs[SRC_AIRBNB] = asyncio.to_thread(self._airbnb, destination, check_in, check_out, adults, ages)
        else:
            status[SRC_AIRBNB] = "übersprungen (keine mcpo-URL)"
        if v.rapidapi_key:
            jobs[SRC_BOOKING] = asyncio.to_thread(self._booking, destination, check_in, check_out, adults, ages)
        geo_job = asyncio.to_thread(self._geocode_many, sights, destination) if sights else None
        center_job = asyncio.to_thread(self._geocode, destination) if v.max_distance_km else None

        extra = [j for j in (geo_job, center_job) if j]
        results = await asyncio.gather(*jobs.values(), *extra, return_exceptions=True)
        center = results.pop() if center_job else None
        sight_hits = results.pop() if geo_job else []
        if isinstance(center, Exception):
            center = None
        if isinstance(sight_hits, Exception):
            sight_hits = []
        radius_note = ""
        if center and center.get("osm_class") in ("natural", "water", "waterway"):
            center, radius_note = None, "Umkreisfilter aus (Zielort ist ein Gewässer/eine Naturfläche)"

        listings = []
        for source, res in zip(jobs.keys(), results):
            if isinstance(res, Exception):
                logger.error("%s failed: %s", source, res)
                status[source] = f"Fehler: {str(res)[:120]}"
            else:
                status[source] = f"{len(res)} Treffer"
                listings.extend(res)

        if center:
            radius = max(v.max_distance_km, center.get("radius_km", 0))
            with_coords = [l for l in listings if l.get("lat") is not None and l.get("lon") is not None]
            if with_coords and all(
                self._haversine_km(center["lat"], center["lon"], l["lat"], l["lon"]) > radius for l in with_coords
            ):
                center, radius_note = None, "Umkreisfilter aus (Zielort zu unscharf – alle Treffer lägen außerhalb)"

        await self._status(__event_emitter__, f"Bewerte {len(listings)} Unterkünfte …")
        ranked, dropped = self._rank(listings, budget_total, sight_hits, has_children=bool(ages), center=center)

        ev_error = None
        if travel_by_car and ranked:
            await self._status(__event_emitter__, "Prüfe E-Ladestationen …")
            points = [(l["lat"], l["lon"]) for l in ranked if l.get("lat") is not None and l.get("lon") is not None]
            try:
                chargers = await asyncio.to_thread(
                    self._chargers_near, points, max(v.ev_radius_m, v.ev_fast_radius_m)) if points else []
            except Exception as e:
                ev_error, chargers = str(e)[:120], []
            for l in ranked:
                on_site = any(EV_AMENITY_RE.search(str(a)) for a in l.get("amenities") or [])
                near = (
                    "unbekannt" if ev_error or l.get("lat") is None or l.get("lon") is None
                    else self._ev_summary(l["lat"], l["lon"], chargers)
                )
                l["ev"] = ("⚡ an Unterkunft laut Portal; " if on_site else "") + near

        await self._status(__event_emitter__, f"{len(ranked)} Unterkünfte im Ranking", done=True)

        # ---------- Ausgabe (kompakt) ----------
        who = f"{adults} Erw." + (f" + {len(ages)} Kinder ({', '.join(map(str, ages))} J.)" if ages else "")
        out = [
            f"Suche: {destination}, {check_in} bis {check_out} ({nights} Nächte), {who}"
            + (f", Budget {budget_total:.0f} {v.currency}" if budget_total else ""),
            "Quellen: " + " | ".join(f"{k}: {s}" for k, s in status.items()),
        ]
        if radius_note:
            out.append(radius_note)
        if sights:
            found = ", ".join(s["name"] for s in sight_hits) or "keine gefunden"
            out.append(f"Lage bewertet nach Ø-Distanz zu: {found}")
        if not listings:
            out.append("\nKeine Treffer – keine Quelle hat Ergebnisse geliefert (siehe Quellen-Zeile).")
        elif not ranked:
            out.append("\nKeine Unterkunft erfüllt alle Kriterien.")
        else:
            cols = ["#", "Unterkunft", "Portal", "Gesamtpreis", "Bewertung", "Bew.", "Schlafz.", "Ø Distanz"]
            if travel_by_car:
                cols.append("E-Laden")
            cols += ["Score", "Link"]
            out += ["", "| " + " | ".join(cols) + " |", "|" + "---|" * len(cols)]
            for i, l in enumerate(ranked, 1):
                _, scale = self._rating_rule(l["source"])
                price = f"{l['total_price']:.0f} {l['currency']}" + ("" if l["price_ok"] else " ⚠️ prüfen")
                rating = f"{l['rating']:.2f}".rstrip("0").rstrip(".") + ("/5" if scale == 5 else "/10")
                row = [
                    str(i), l["name"],
                    l["source"] + (f" (auch: {', '.join(l['also_on'])})" if l.get("also_on") else ""),
                    price,
                    rating,
                    str(l.get("reviews") or 0),
                    str(l["bedrooms"]) if l.get("bedrooms") is not None else "prüfen",
                    f"{l['mean_km']:.1f} km" if "mean_km" in l else "–",
                ]
                if travel_by_car:
                    row.append(l.get("ev", "–"))
                row += [str(l["score"]), f"[Ansehen]({l.get('url') or ''})"]
                out.append("| " + " | ".join(r.replace("|", "/") for r in row) + " |")

            notes = [
                f"- {l['name']}: " + "; ".join(x for x in [
                    l.get("price_note"),
                    ", ".join(l.get("amenities") or []),
                ] if x)
                for l in ranked[:5] if l.get("price_note") or l.get("amenities")
            ]
            if notes:
                out += ["", "Hinweise Top 5:"] + notes
        if dropped:
            counts = Counter(r for _, r in dropped)
            out.append("\nAusgefiltert: " + ", ".join(f"{n}× {r}" for r, n in counts.most_common()))
        if travel_by_car:
            out.append(
                f"E-Laden laut OpenStreetMap (≤ {v.ev_radius_m / 1000:.1f} km, Schnelllader ≥ {EV_FAST_KW} kW ≤ "
                f"{v.ev_fast_radius_m / 1000:.0f} km)" + (f" – Abfrage fehlgeschlagen: {ev_error}" if ev_error else "")
            )
        out.append("\nWeitersuchen: " + " · ".join(self._deeplinks(destination, check_in, check_out, adults, ages)))
        return "\n".join(out)

    async def geocode_places(self, places: str, destination: str = "", __event_emitter__=None) -> str:
        """
        Ermittelt Koordinaten für Sehenswürdigkeiten und den Punkt mit der geringsten
        mittleren Distanz zu allen (günstigste Wohnlage). Nutzen, um Stadtteile zu empfehlen.
        :param places: Orte, getrennt durch Semikolon, z.B. "Torre de Belém; Alfama; Oceanário"
        :param destination: Stadt/Region zur Eingrenzung, z.B. "Lissabon"
        :return: Koordinaten je Ort, größter Abstand zwischen den Zielen und günstigste Wohnlage
        """
        await self._status(__event_emitter__, "Suche Orte auf der Karte …")
        hits = await asyncio.to_thread(self._geocode_many, places, destination)
        await self._status(__event_emitter__, f"{len(hits)} Orte gefunden", done=True)
        if not hits:
            return "Keiner der Orte gefunden. Bitte Namen präzisieren."
        lat, lon = self._best_point(hits)
        spread = max(
            (self._haversine_km(a["lat"], a["lon"], b["lat"], b["lon"]) for a in hits for b in hits), default=0
        )
        lines = [f"- {h['name']}: {h['lat']:.5f}, {h['lon']:.5f} – {h['display']}" for h in hits]
        lines += [
            f"\nGrößter Abstand zwischen zwei Zielen: {spread:.1f} km",
            f"Günstigste Wohnlage (geringste Ø-Distanz): {lat:.5f}, {lon:.5f} – Ø {self._mean_distance(lat, lon, hits):.1f} km zu den Zielen",
        ]
        if spread > 8:
            lines.append("Die Ziele liegen weit auseinander – ÖPNV-Anbindung ist wichtiger als die exakte Lage.")
        return "\n".join(lines)

    async def find_family_pois(
        self, latitude: float, longitude: float, radius_m: int = 1000, __event_emitter__=None
    ) -> str:
        """
        Zählt familienrelevante Orte (Spielplätze, Strände, Supermärkte, Parkplätze,
        ÖPNV, Apotheken, Zoos, E-Ladestationen) im Umkreis eines Punktes. Nutzen, um
        Stadtteile oder die Umgebung einer konkreten Unterkunft zu bewerten.
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
            for k, op, val in re.findall(r'\["([^"]+)"(=|~)"([^"]+)"\]', flt):
                actual = tags.get(k, "")
                if (op == "=" and actual != val) or (op == "~" and not re.fullmatch(val, actual)):
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
        maximaler Ladeleistung, Betreiber, Kosten und Zugang. Nur nutzen, wenn der Nutzer
        Details zu einer bestimmten Unterkunft oder einem Ort wissen möchte.
        :param latitude: Breitengrad
        :param longitude: Längengrad
        :param radius_m: Suchradius in Metern (Standard 3000)
        :return: die nächsten Ladestationen und die nächsten Schnelllader im Umkreis
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
        fast = sorted([c for c in chargers if (c["max_kw"] or 0) >= EV_FAST_KW], key=lambda c: c["dist_m"])[:3]
        out = [f"{len(chargers)} öffentliche Ladestationen im Umkreis von {radius_m} m.", "\nNächste Ladestationen:"]
        out += [line(c) for c in nearest]
        if fast:
            out.append(f"\nSchnelllader (≥ {EV_FAST_KW} kW):")
            out += [line(c) for c in fast]
        else:
            out.append(f"\nKein Schnelllader (≥ {EV_FAST_KW} kW) mit erfasster Leistung im Umkreis.")
        out.append("\nHinweis: Daten aus OpenStreetMap – Verfügbarkeit und Preise in der Lade-App prüfen.")
        return "\n".join(out)
