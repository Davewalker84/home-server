# AI-Stack (Open Web UI + SearXNG)

Docker Compose Stack `ai-stack` auf dem **Mac Mini M4** (192.168.188.151). Stellt den lokalen KI-Chat und die anonyme Websuche bereit. Die LLM-Inferenz läuft ebenfalls auf dem Mac Mini via Ollama – Open Web UI und Ollama laufen auf demselben Gerät, kein Netzwerk-Hop.

---

## Architektur

```
Familie (Browser)
        ↓
Open Web UI :3001 (Mac Mini M4)
        ├── Ollama API → localhost:11434 (kein Netzwerk-Hop)
        ├── SearXNG :8080 (intern, Mac Mini M4) → Google/Bing (anonym)
        ├── Tool: Paperless-NGX API → NAS :8000
        ├── Anthropic API (Claude, OpenAI-kompatibel) → Urlaubsplaner
        └── Tool: Urlaubsplaner → mcpo :8000 (intern) → MCP-Server (AirBnB)

VS Code + Continue Extension
        └── Ollama API → Mac Mini M4 :11434
```

---

## Deployment: Mac Mini M4 (nicht Portainer)

Der Stack läuft direkt auf dem Mac Mini via OrbStack (nicht via Portainer auf der NAS).

```bash
# Einmalig: OrbStack installieren
ssh davidmarotzke@192.168.188.151
brew install orbstack

# Stack anlegen und starten
mkdir -p ~/docker/ai-stack
mkdir -p ~/docker/searxng
# docker-compose.yml (unten) nach ~/docker/ai-stack/docker-compose.yml kopieren
# settings.yml (unten) nach ~/docker/searxng/settings.yml kopieren
docker compose -f ~/docker/ai-stack/docker-compose.yml up -d

# Status prüfen
docker ps
```

---

## docker-compose.yml

Liegt unter `~/docker/ai-stack/docker-compose.yml`.

```yaml
services:
  open-webui:
    # Version in .env pinnen (OPEN_WEBUI_TAG=vX.Y.Z), damit Tool-/MCP-Verhalten nicht unerwartet wechselt
    image: ghcr.io/open-webui/open-webui:${OPEN_WEBUI_TAG:-main}
    container_name: open-webui
    restart: unless-stopped
    ports:
      - "3001:8080"
    volumes:
      - open-webui-data:/app/backend/data
    environment:
      # Ollama läuft nativ auf demselben Mac Mini
      - OLLAMA_BASE_URL=http://host.docker.internal:11434

      # Claude wird über Admin → Verbindungen angebunden (siehe HolidayAgent/README.md),
      # diese Env-Werte gelten nur beim allerersten Start
      - OPENAI_API_BASE_URL=
      - OPENAI_API_KEY=

      - WEBUI_AUTH=true
      - WEBUI_NAME=Home AI

      # Web-Suche via lokales SearXNG
      - ENABLE_RAG_WEB_SEARCH=true
      - RAG_WEB_SEARCH_ENGINE=searxng
      - SEARXNG_QUERY_URL=http://searxng:8080/search?q=<query>&format=json

      # Embeddings für RAG
      - RAG_EMBEDDING_ENGINE=ollama
      - RAG_EMBEDDING_MODEL=nomic-embed-text

      - SCARF_NO_ANALYTICS=true
      - DO_NOT_TRACK=true
      - ANONYMIZED_TELEMETRY=false

    depends_on:
      - searxng
    networks:
      - ai-net

  searxng:
    image: searxng/searxng:latest
    container_name: searxng
    restart: unless-stopped
    volumes:
      - /Users/davidmarotzke/docker/searxng:/etc/searxng
    environment:
      - SEARXNG_BASE_URL=http://searxng:8080
      - SEARXNG_SECRET_KEY=<secret>
    networks:
      - ai-net

  # MCP → OpenAPI Proxy – wird vom Urlaubsplaner-Tool direkt per HTTP aufgerufen
  # (nicht als Tool-Server in Open WebUI eintragen, siehe HolidayAgent/README.md)
  mcpo:
    image: ghcr.io/open-webui/mcpo:main
    container_name: mcpo
    restart: unless-stopped
    volumes:
      - /Users/davidmarotzke/docker/mcpo/config.json:/app/config/config.json:ro
    command: ["--config", "/app/config/config.json", "--port", "8000", "--api-key", "${MCPO_API_KEY}"]
    networks:
      - ai-net

volumes:
  open-webui-data:
    driver: local

networks:
  ai-net:
    driver: bridge
```

**`.env`** (liegt neben der Compose-Datei unter `~/docker/ai-stack/.env`, nicht im Repo):

```bash
OPEN_WEBUI_TAG=main        # auf aktuell laufende Version setzen, z.B. v0.x.y
MCPO_API_KEY=<openssl rand -hex 24>
```

> **Hinweis:** `host.docker.internal` wird von OrbStack auf macOS automatisch auf den Host gemappt – kein `extra_hosts` nötig (war Linux-spezifisch).

---

## SearXNG: settings.yml

Liegt unter `~/docker/searxng/settings.yml` (Bind Mount, persistent über Container-Neustarts).

```yaml
use_default_settings: true

server:
  secret_key: "<secret>"
  image_proxy: true

search:
  formats:
    - html
    - json
```

> **Wichtig:** Das `- json` Format ist zwingend erforderlich, damit Open Web UI Suchergebnisse empfangen kann.

---

## Stack-Verwaltung

```bash
# Starten
docker compose -f ~/docker/ai-stack/docker-compose.yml up -d

# Stoppen
docker compose -f ~/docker/ai-stack/docker-compose.yml down

# Logs prüfen
docker compose -f ~/docker/ai-stack/docker-compose.yml logs -f

# Neu starten (nach Konfigurationsänderung)
docker compose -f ~/docker/ai-stack/docker-compose.yml down
docker compose -f ~/docker/ai-stack/docker-compose.yml up -d

# Vollständig zurücksetzen (löscht alle Chats/Daten!)
docker compose -f ~/docker/ai-stack/docker-compose.yml down
docker volume rm open-webui-data
docker compose -f ~/docker/ai-stack/docker-compose.yml up -d
```

---

## Open Web UI: Websuche konfigurieren

Nach dem ersten Start unter **Admin Panel → Einstellungen → Websuche**:

| Einstellung | Wert |
|---|---|
| Websuche | ✅ aktiviert |
| Web-Suchmaschine | searxng |
| SearXNG-Abfrage-URL | `http://searxng:8080/search?q=<query>&format=json` |
| SearXNG-Suchsprache | `de` |
| Anzahl Suchergebnisse | 3 |
| **Embedding und Retrieval umgehen** | ✅ **aktiviert** ← wichtig! |

> **Achtung:** „Embedding und Retrieval umgehen" **muss aktiviert sein**. Sonst werden Suchergebnisse durch die RAG-Pipeline gejagt und nicht ans LLM übergeben → „Keine Quellen gefunden".

---

## Modell-Auswahl nach Use-Case

| Use-Case | Modell | Thinking |
|---|---|---|
| Familien-Chat | qwen3:14b | OFF (`/no_think`) |
| Schnelle Fragen | qwen3:8b | OFF |
| Dokument-RAG + Paperless-Chat | gemma4:26b-mlx (geklont) | – |
| Paperless-AI (Auto-Tagging) | qwen2.5:7b (via Paperless-AI Stack) | – |
| Neueres Qwen (Einsatzzweck offen, ~27B) | qwen3.8:27b-mlx | – |
| Urlaubsplaner (Tools, Unterkunftssuche) | claude-sonnet-5 (Anthropic API) | – |

Qwen3 Thinking Mode im System-Prompt deaktivieren:  
`Admin Panel → Einstellungen → Allgemein → System-Prompt → /no_think`

---

## Gemma4 Modell-Einstellungen (Paperless-Chat)

Das für Paperless-Chat geklonte Gemma4-Modell benötigt folgende Einstellungen unter **Open Web UI → Modelle → [Gemma4-Paperless] → Erweiterte Parameter**:

| Parameter | Wert | Begründung |
|---|---|---|
| `num_ctx` | `16384` | 5 Dokumente × 7000 Zeichen ≈ 9000 Tokens — passt gut auf den M4 mit 32 GB |
| `temperature` | `0.1` | Faktenbasierte Antworten ohne Halluzinationen |

### System-Prompt (geklontes Modell)

```
Du bist ein Dokumenten-Assistent. Antworte immer auf Deutsch.
Wenn nach Dokumenten, Rechnungen, Bescheiden oder Daten gefragt wird,
rufe IMMER zuerst das Paperless-Tool auf, bevor du antwortest – auch bei Folgefragen.

Beim Aufrufen des Tools:
- Extrahiere das Jahr aus der Frage und füge es in den Query ein (z.B. "Entgeltabrechnung 2024 Bosch")
- Nutze offizielle deutsche Dokumentbezeichnungen: "Gehaltsabrechnung" → "Entgeltabrechnung", "Steuerbescheid" → "Einkommensteuerbescheid"
- Erkenne Korrespondenten (Firmen, Behörden) und füge sie in den Query ein
- Bei keinem Ergebnis: rufe das Tool erneut mit einem alternativen Begriff auf
```

---

## Ollama Performance (Mac Mini M4 / Apple Silicon)

Die Variablen `OLLAMA_FLASH_ATTENTION=1` und `OLLAMA_KV_CACHE_TYPE=q8_0` (zusammen mit `OLLAMA_HOST` und `OLLAMA_KEEP_ALIVE`) werden per LaunchAgent bei jedem Login gesetzt und überleben damit Reboots. Einrichtung und Fehlersuche: [Hardware/mac-mini-m4.md](../../Hardware/mac-mini-m4.md#netzwerk-konfiguration-pflicht-für-lan-zugriff).

```bash
# Prüfen, ob die Variablen aktiv sind
launchctl getenv OLLAMA_FLASH_ATTENTION
launchctl getenv OLLAMA_KV_CACHE_TYPE

# Manuell neu setzen + Ollama neu starten (bei Bedarf, ohne Reboot)
~/scripts/ollama-env.sh
```

> `OLLAMA_FLASH_ATTENTION=1` aktiviert Flash Attention auf dem M4 und reduziert den KV-Cache-Speicher spürbar. `q8_0` komprimiert den KV-Cache auf 8 Bit – geringer Qualitätsverlust, deutlich weniger Unified Memory Verbrauch.

---

## Datenschutz

```
Anfrage → SearXNG (lokal auf Mac Mini M4)
            ↓ anonym
        Google/Bing/Wikipedia
            ↓
        Ergebnisse → Open Web UI → Modell (lokal auf Mac Mini M4)

Was das Haus verlässt:  Nur die Suchanfrage (anonym, kein Account)
Was lokal bleibt:       Chat-Verlauf, Dokumente, Modell, Embeddings
```

**Empfehlung:** Websuche (Globus-Icon im Chat) nur aktivieren wenn aktuelle Informationen benötigt werden. Für sensible Daten und Dokumente deaktivieren.

---

## Bekannte Probleme

| Problem | Ursache | Lösung |
|---|---|---|
| Port 3000 belegt | Anderer Dienst | Port 3001 nutzen (bereits konfiguriert) |
| SearXNG startet nicht | `cap_drop: ALL` in compose | Zeilen `cap_drop`/`cap_add` entfernen |
| SearXNG kein JSON | `settings.yml` fehlt `- json` | In `~/docker/searxng/settings.yml` ergänzen, Container neu starten |
| `bash` nicht gefunden | SearXNG hat kein bash | `sh` statt `bash` verwenden |
| Ollama nicht erreichbar | Mac Mini schläft / OLLAMA_HOST fehlt (z.B. nach Reboot, LaunchAgent nicht geladen) | Auf Mac Mini: `~/scripts/ollama-env.sh` ausführen; LaunchAgent siehe [mac-mini-m4.md](../../Hardware/mac-mini-m4.md) |
| „Keine Quellen gefunden" | „Embedding und Retrieval umgehen" deaktiviert | In Admin → Websuche aktivieren |
| Passwort vergessen | – | `docker volume rm open-webui-data` + Stack neu starten (löscht alle Daten) |
| `docker compose` → „no config file" | Falsches Verzeichnis | Immer mit `-f ~/docker/ai-stack/docker-compose.yml` aufrufen |
| Antwort zeigt vollständige Token-Stats, aber kein sichtbarer Text (bei allen Modellen) | Vermutlich Reasoning-Rendering-Regression in Open WebUI v0.10.2 (Release 2026-07-01, siehe [Issue #26072](https://github.com/open-webui/open-webui/issues/26072) / [Discussion #13076](https://github.com/open-webui/open-webui/discussions/13076)) und/oder Cold-Start nach `OLLAMA_KEEP_ALIVE`-Entladung – trat am 2026-07-09 einmalig auf, war beim nächsten Versuch ohne Änderung wieder normal | Bisher nur einmalig aufgetreten, kein Fix nötig. Bei erneutem Auftreten: prüfen ob Antworttext in einem eingeklappten "Thinking"-Bereich versteckt ist; falls ja, Downgrade auf letzte funktionierende Version erwägen und Image auf festen Tag pinnen (statt `:main`) |

---

## Paperless-NGX Tool (Dokument-Chat)

Statt einem eigenen RAG-Index in Paperless-AI nutzt Open Web UI ein **Tool**, das die Paperless-NGX REST API direkt abfragt. Der OCR-Volltext ist bereits in Paperless-NGX vorhanden — kein separates Embedding nötig.

**Tool anlegen:** Open Web UI → Einstellungen → Tools → + Neu → Code aus `Code/PaperlessSearchTool.py` einfügen (aktuelle Version: **v3.0**).

**Nach dem Anlegen:** Tool öffnen → Valves → `paperless_token` mit dem API-Token aus Paperless-NGX befüllen.

### Was v3.0 neu kann

| Feature | v2.0 | v3.0 |
|---|---|---|
| Jahres-Datumsfilter (API-seitig) | ❌ nur LLM-Hinweis | ✅ extrahiert Jahr aus Query, filtert per `created__date__gte/lte` |
| Korrespondenten-Suche | ❌ | ✅ Cache + parallele Suche per `correspondent__id` |
| Dokumententyp-Filter | ❌ | ✅ Cache + parallele Suche per `document_type__id` |
| Title-Suche | nur Fallback | ✅ immer parallel zu Volltext |
| Substring-Matching (Tags/Korrespondenten) | Einzel-Wort exakt | ✅ Substring im gesamten Query |
| Content-Abruf | sequentiell | ✅ parallel mit ThreadPoolExecutor |
| Ausgabe | Titel, Datum, Tags | ✅ + Korrespondent, Dokumentenart |
| `max_docs` Valve | hardcoded 8 | ✅ konfigurierbar (Standard: 5) |
| Head+Tail Truncation | `content[:5000]` | ✅ erste 4000 + letzte 3000 Zeichen — erfasst Summen auf Seite 2 |
| `content_head_chars` / `content_tail_chars` Valves | – | ✅ konfigurierbar |

**Nutzen im Chat:** Tool über das Stecker-Icon aktivieren → Frage stellen z.B. *„Suche meine letzte Rechnung von IKEA"*

---

## Urlaubsplaner (HolidayAgent)

Agent für Unterkunftssuche und Urlaubstipps: Claude Sonnet 5 + Tool `HolidayAgent/HolidaySearchTool.py`. Die Suche (Google Hotels, AirBnB über `mcpo`, optional Booking) läuft komplett im Tool (`plan_search`); das LLM führt nur den Dialog. Einrichtung, Ranking-Logik und Test-Checkliste: [HolidayAgent/README.md](../../HolidayAgent/README.md).

> **Datenschutz:** Anders als beim Familien-Chat verlassen hier Chat-Inhalte das Haus (Anthropic, SerpAPI, RapidAPI, OpenStreetMap). Keine sensiblen Daten im Urlaubsplaner eingeben.

> **Sicherheit:** Tools führen beliebigen Python-Code im Open-WebUI-Container aus. Das Recht „Workspace → Tools“ ist root-äquivalent und darf nur Admins haben – nicht der Familie-Gruppe.

---

## Geplante Erweiterungen

- [x] Continue in VS Code vollständig einrichten → siehe [Hardware/mac-mini-m4.md](../../Hardware/mac-mini-m4.md#vs-code-continue-integration)
