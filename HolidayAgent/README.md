# HolidayAgent – Familien-Urlaubsplaner

Ein Agent in Open WebUI (Mac Mini M4, `ai-stack`), der für die Familie Unterkünfte sucht, bewertet und Urlaubstipps gibt. Die Anforderungen stehen in [UseCases](UseCases).

---

## Architektur

```
Familie (Browser, zu Hause oder über WireGuard)
        ↓
Open WebUI :3001 → Modell "Urlaubsplaner" (Claude Sonnet 5 + System-Prompt + Familienprofil)
        ├── Tool "Urlaubsplaner – Unterkunftssuche" (HolidaySearchTool.py)
        │     ├── search_accommodations → SerpAPI Google Hotels + Ferienhäuser, RapidAPI Booking.com
        │     ├── geocode_places        → OSM Nominatim
        │     ├── find_family_pois      → OSM Overpass (Spielplätze, Strand, Supermarkt, Parken, E-Laden …)
        │     ├── find_ev_chargers      → OSM Overpass (Ladestationen: Stecker, kW, Betreiber, Kosten)
        │     ├── rank_accommodations   → Filter + Scoring + Dubletten (deterministisch in Python)
        │     └── build_deeplinks       → Such-Links für Fewo-direkt, HomeToGo, Interhome u.a.
        ├── Tool-Server mcpo :8000 (intern) → @openbnb/mcp-server-airbnb (AirBnB)
        └── Websuche → SearXNG (Regionstipps, Saison-Infos)
```

| Quelle | Weg | Kosten | Liefert |
|---|---|---|---|
| Google Hotels | SerpAPI `google_hotels` | Free-Tier (Kontingent auf serpapi.com prüfen) | Hotels inkl. Angebote von Booking, Expedia, Direktbuchung |
| Google Ferienhäuser | SerpAPI `google_hotels` + `vacation_rentals=true` | gleiches Kontingent | Ferienwohnungen/-häuser (Vrbo u.a.), Schlafzimmer |
| Booking.com | RapidAPI „Booking.com“ (booking-com15) | Free-Tier | Hotels & Apartments mit Bewertung |
| AirBnB | MCP-Server über mcpo (Scraping) | kostenlos | Listings, Preise, Bewertungen |
| Fewo-direkt, HomeToGo, Interhome | Deep-Links | kostenlos | vorausgefüllte Suche zum Selbstklicken |
| Lage & Umgebung | OpenStreetMap (Nominatim, Overpass) | kostenlos | Koordinaten, POIs im Umkreis |
| E-Ladestationen | OpenStreetMap (Overpass, `amenity=charging_station`) | kostenlos | Stecker, max. kW, Betreiber, Kosten, Zugang |

> Jede Suche (`search_accommodations`) verbraucht **2 SerpAPI-Anfragen** (Hotels + Ferienhäuser) und **2 RapidAPI-Anfragen**. Gleiche Suchen werden 24 h lang aus dem SQLite-Cache bedient (`/app/backend/data/holiday_cache.db`).

> **AirBnB:** Es gibt keine offizielle API; der MCP-Server liest die Webseite aus. Das bewegt sich in einer Grauzone der AirBnB-AGB. Nur für private Nutzung mit wenigen Anfragen gedacht. Wenn AirBnB das Layout ändert, kann das Tool ausfallen – der Agent sucht dann mit den übrigen Quellen weiter.

---

## Ranking

`rank_accommodations` filtert und bewertet alle Treffer in Python. Das LLM erklärt nur das Ergebnis und erfindet keine Preise.

**Harte Filter** (Valves):
- kein Preis → gilt als nicht verfügbar
- Gesamtpreis > Budget
- Bewertung < `min_rating_10` (Standard 8,5/10; AirBnB/Google /5 werden ×2 umgerechnet)
- Bewertungen < `min_reviews` (Standard 20)
- Schlafzimmer < `min_bedrooms_with_children` (Standard 2) – nur wenn bekannt, sonst Hinweis „prüfen“

**Score (0–100):**

| Kriterium | Gewicht | Berechnung |
|---|---|---|
| Bewertung | 35 % | linear zwischen Mindestbewertung und 10 |
| Anzahl Bewertungen | 20 % | logarithmisch, 500+ = volle Punkte |
| Lage | 25 % | Distanz zum Schwerpunkt der Sehenswürdigkeiten, ab `max_location_km` (6 km) = 0; ohne Sehenswürdigkeiten neutral |
| Preis | 20 % | ≤ 50 % des Budgets = volle Punkte |

**E-Laden (nur bei Anreise mit dem Auto, `travel_by_car=true`):** Das Ranking bekommt eine Spalte „E-Laden“ mit der nächsten öffentlichen Ladestation (Distanz, kW, Anzahl im Umkreis `ev_radius_m`, Standard 1,5 km). Nennt das Portal eine Ladestation in der Ausstattung, erscheint zusätzlich „⚡ an Unterkunft laut Portal“. Für alle Top-Treffer genügt eine Overpass-Abfrage. Das fließt **nicht in den Score** ein, sondern dient nur als Information. Details (Stecker, Schnelllader ≥ 50 kW, Kosten, Kartenlink) liefert `find_ev_chargers`, das der Agent für die Top 3 aufruft.

**Dubletten:** Gleicher Name (Akzente ignoriert) oder < 150 m Abstand mit ähnlichem Namen → das günstigste Angebot bleibt, die anderen Portale stehen als „auch: …“ dabei.

---

## Einrichtung

### 1. API-Keys besorgen

| Dienst | Wo | Hinweis |
|---|---|---|
| Anthropic | console.anthropic.com → API Keys | unter *Billing → Limits* ein monatliches Spend-Limit setzen (z.B. 10 €) |
| SerpAPI | serpapi.com → Registrieren → Dashboard | Free-Plan |
| RapidAPI | rapidapi.com → API „Booking.com“ von DataCrawler (`booking-com15`) → Basic-Plan (kostenlos) abonnieren | Key steht unter *Endpoints → X-RapidAPI-Key* |

Keys **nicht** ins Repo – sie kommen in die `.env` auf dem Mac Mini bzw. in die Tool-Valves.

### 2. Claude in Open WebUI anbinden

**Admin-Panel → Einstellungen → Verbindungen → OpenAI-API → +**

| Feld | Wert |
|---|---|
| URL | `https://api.anthropic.com/v1` |
| Key | Anthropic API-Key |
| Model IDs | `claude-sonnet-5` (optional zusätzlich `claude-haiku-4-5-20251001` für einfache Fragen) |

Anthropic stellt einen OpenAI-kompatiblen Endpoint bereit, daher ist kein zusätzlicher Container nötig. Ollama bleibt parallel aktiv.

> Die Verbindung wird in der Open-WebUI-Datenbank gespeichert. Die Env-Variablen `OPENAI_API_*` im Compose gelten nur beim allerersten Start – deshalb über die UI konfigurieren.

### 3. mcpo + AirBnB starten

Siehe [ai-stack.md](../ContainerStack/Readme/ai-stack.md#docker-composeyml) – Service `mcpo`.

```bash
ssh davidmarotzke@192.168.188.151
mkdir -p ~/docker/mcpo
# mcpo-config.json aus diesem Ordner nach ~/docker/mcpo/config.json kopieren
# MCPO_API_KEY in ~/docker/ai-stack/.env eintragen (z.B. openssl rand -hex 24)
docker compose -f ~/docker/ai-stack/docker-compose.yml up -d mcpo
docker logs -f mcpo        # beim ersten Start lädt npx den AirBnB-Server
```

**Admin-Panel → Einstellungen → Externe Tools** (je nach Version „Tool-Server“) → **+**

| Feld | Wert |
|---|---|
| URL | `http://mcpo:8000/airbnb` |
| Auth | Bearer, `MCPO_API_KEY` |

### 4. Tool anlegen

**Arbeitsbereich → Tools → + Neu** → Inhalt von [HolidaySearchTool.py](HolidaySearchTool.py) einfügen → speichern.
Danach **Valves** (Zahnrad) öffnen und `serpapi_key`, `rapidapi_key` eintragen. Filter und Gewichte bei Bedarf anpassen.

### 5. Modell „Urlaubsplaner“ anlegen

**Arbeitsbereich → Modelle → + Neu**

| Einstellung | Wert |
|---|---|
| Name | Urlaubsplaner |
| Basismodell | `claude-sonnet-5` |
| System-Prompt | [system-prompt.md](system-prompt.md) mit eingefügtem [family-profile.md](family-profile.md) (Platzhalter vorher ausfüllen) |
| Tools | „Urlaubsplaner – Unterkunftssuche“, AirBnB-Tool-Server |
| Fähigkeiten | Websuche ✅ |
| Erweiterte Parameter → Function Calling | **Native** |
| Sichtbarkeit | Gruppe „Familie“ |

### 6. Familie freischalten

1. **Admin-Panel → Benutzer** → Accounts für die Familie anlegen.
2. **Admin-Panel → Benutzer → Gruppen** → Gruppe „Familie“ anlegen, Accounts hinzufügen.
3. Modell „Urlaubsplaner“ und das Tool für die Gruppe freigeben. Die API-Keys stehen in den Admin-Valves und sind für normale Nutzer nicht sichtbar.

Von unterwegs erreichbar über WireGuard → `http://192.168.188.151:3001`.

---

## Test-Checkliste

1. Modell-Dropdown zeigt `claude-sonnet-5`, einfacher Chat funktioniert.
2. `docker exec open-webui curl -s -H "Authorization: Bearer $MCPO_API_KEY" http://mcpo:8000/airbnb/openapi.json | head` liefert die OpenAPI-Spec.
3. Im Chat: *„Lissabon, 12.–19.10.2026, 2 Erwachsene + 2 Kinder (5, 8), Budget 2.000 €, wir wollen nach Belém, in die Alfama und ins Oceanário.“*
   → Rückfrage zur Anreise, Stadtteil-Empfehlung, danach Tabelle mit Treffern aus ≥ 3 Quellen, alle ≤ 2.000 €, Bewertung ≥ 8,5, Links funktionieren.
4. *„Ostsee, 1 Woche im Juli, mit dem Auto“* → Strand- und Parkplatznähe in der Begründung, Spalte „E-Laden“ in der Tabelle und Lade-Infos für die Top 3.
5. SerpAPI-Key in den Valves leeren → Agent antwortet mit AirBnB + Booking und nennt den Ausfall.
6. Mit einem Familien-Account einloggen → Urlaubsplaner nutzbar, Valves/Keys nicht sichtbar.
7. Nach einer Woche Verbrauch in SerpAPI-, RapidAPI- und Anthropic-Dashboard prüfen.

---

## Kosten

| Posten | Kosten |
|---|---|
| Claude Sonnet 5 | ca. 0,05–0,30 € pro kompletter Urlaubssuche (nach Verbrauch) |
| SerpAPI, RapidAPI | Free-Tier |
| OpenStreetMap, SearXNG, AirBnB-MCP | kostenlos |
| **Fixkosten** | **0 €** |

---

## Bekannte Grenzen

| Thema | Details |
|---|---|
| Schlafzimmer bei Hotels | Google Hotels/Booking liefern die Zimmeraufteilung meist nicht → Anzeige „prüfen“, kein Ausschluss |
| Booking-Links | Die API liefert keine direkte Hotel-URL → Link öffnet die Booking-Suche nach dem Hotelnamen mit Reisedaten |
| Deep-Links | Fewo-direkt/HomeToGo/Interhome übernehmen nicht immer alle Filter |
| E-Ladestationen | OSM-Daten sind in DE/EU gut, aber nicht vollständig; Ladeleistung ist oft nicht erfasst („Stecker unbekannt“), private Wallboxen und Hotel-Lader fehlen häufig. Keine Live-Belegung |
| Overpass | öffentliche Server sind zeitweise überlastet (504) → Tool probiert automatisch drei Server; schlägt alles fehl, steht „unbekannt“ in der Spalte |
| Nominatim | max. 1 Anfrage/Sekunde (im Tool berücksichtigt); Ergebnisse werden gecacht |
| RapidAPI Booking | Drittanbieter-API, Endpunkte können sich ändern → bei Fehlern in der RapidAPI-Doku prüfen |

## Mögliche Erweiterungen

- [ ] Flugsuche (SerpAPI `google_flights`)
- [ ] Merkliste pro Reise (Open-WebUI-Notizen/Wissen)
- [ ] Preisalarm für eine gemerkte Unterkunft per Home-Assistant-Benachrichtigung
