# Paperless-AI

Automatische KI-Klassifizierung für Paperless-NGX: Titel, Tags, Korrespondenten, Dokumententypen und Datum werden von Ollama auf dem Mac Mini M4 vorgeschlagen und automatisch zugewiesen.

**Image:** `clusterzx/paperless-ai` (Docker Hub)  
**Inferenz:** Ollama auf Mac Mini M4 (`192.168.188.151:11434`)  
**Stack-Name:** `paperless-ai` (Portainer)  
**Web UI:** http://192.168.188.130:3002

---

## Architektur

```
Neues Dokument in Paperless-NGX
        ↓ (Polling alle 30 Min via REST API)
Paperless-AI :3000 (Container auf NAS)
        ↓
Ollama :11434 (Mac Mini M4) → qwen3:8b
        ↓
Vorschläge: Titel · Tags · Korrespondent · Datum
        ↓ (via Paperless-NGX API)
Paperless-NGX → Metadaten aktualisiert
```

---

## Schritt 1: API-Token in Paperless-NGX erstellen

1. http://192.168.188.130:8000 öffnen
2. Oben rechts auf Benutzername klicken → **Profil**
3. Ganz unten: **API-Token** → Token anzeigen / neu generieren
4. Token kopieren – wird im Stack als `PAPERLESS_API_TOKEN` eingetragen

---

## Schritt 2: Portainer Stack einrichten

In Portainer: **Stacks → Add Stack → Web editor**

```yaml
services:
  paperless-ai:
    image: clusterzx/paperless-ai
    container_name: paperless-ai
    network_mode: bridge
    restart: unless-stopped
    security_opt:
      - no-new-privileges=true
    ports:
      - "3002:3000"
    environment:
      - PUID=1000
      - PGID=1000
      - PAPERLESS_AI_INITIAL_SETUP=yes

      # Paperless-NGX API (NAS, UGOS Docker)
      - PAPERLESS_API_URL=http://192.168.188.130:8000/api
      - PAPERLESS_API_TOKEN=<API-TOKEN-AUS-SCHRITT-1>

      # Ollama auf Mac Mini M4
      - AI_PROVIDER=ollama
      - OLLAMA_API_URL=http://192.168.188.151:11434
      - OLLAMA_MODEL=qwen3:8b

      # Verarbeitungsplan (täglich 02:00 Uhr nachts)
      - SCAN_INTERVAL=0 2 * * *

      # Bereits klassifizierte Dokumente nicht erneut verarbeiten
      - PROCESS_PREDEFINED_DOCUMENTS=no

      # Verarbeitete Dokumente mit Tag markieren
      - ADD_AI_PROCESSED_TAG=yes
      - AI_PROCESSED_TAG_NAME=ai-processed

      # RAG-Dienst deaktivieren (separates Setup)
      - RAG_SERVICE_ENABLED=false

      # Web UI absichern (selbst gewähltes Passwort)
      - API_KEY=<EIGENES-PASSWORT-FUER-WEB-UI>

    volumes:
      - /volume2/docker/paperless-ai:/app/data
```

> **Hinweis:** `network_mode: bridge` bedeutet, dass Paperless-AI über die NAS-IP (`192.168.188.130`) und nicht über Container-Namen auf Paperless-NGX zugreift.

---

## Konfigurationsdetails

| Variable | Wert | Erklärung |
|---|---|---|
| `PAPERLESS_API_URL` | `http://192.168.188.130:8000/api` | Paperless-NGX API – `/api` am Ende nicht vergessen! |
| `PAPERLESS_API_TOKEN` | `<token>` | API-Token aus Paperless-NGX Profil |
| `AI_PROVIDER` | `ollama` | Lokale Inferenz, kein Cloud-Dienst |
| `OLLAMA_API_URL` | `http://192.168.188.151:11434` | Ollama auf Mac Mini M4 |
| `OLLAMA_MODEL` | `qwen3:8b` | Schnell, ausreichend für Klassifizierung |
| `SCAN_INTERVAL` | `0 2 * * *` | Täglich um 02:00 Uhr nachts |
| `PROCESS_PREDEFINED_DOCUMENTS` | `no` | Bereits getaggte Dokumente überspringen |
| `ADD_AI_PROCESSED_TAG` | `yes` | Verarbeitete Dokumente mit `ai-processed` markieren |
| `API_KEY` | `<passwort>` | Schützt die Web UI vor unbefugtem Zugriff |
| `RAG_SERVICE_ENABLED` | `false` | RAG-Feature deaktiviert (eigener Container nötig) |

### Modell-Wahl: qwen3:8b

Für Dokumenten-Klassifizierung besser als qwen3:14b:
- Einfache strukturierte Ausgabe (JSON mit Titel, Tags, Datum)
- Schnellere Verarbeitung, geringerer RAM-Verbrauch auf dem Mac Mini
- qwen3:14b bleibt für Familien-Chat frei

### Erststart: `PAPERLESS_AI_INITIAL_SETUP=yes`

Beim ersten Start öffnet Paperless-AI einen Setup-Wizard unter http://192.168.188.130:3000. Nach Abschluss des Setups diese Variable auf `no` setzen und den Stack neu starten.

---

## Modell vorab laden (empfohlen)

Damit beim ersten Dokument keine Wartezeit entsteht:

```bash
ssh davidmarotzke@192.168.188.151
ollama pull qwen3:8b
```

---

## Bekannte Probleme & Lösungen

| Problem | Ursache | Lösung |
|---|---|---|
| Image nicht gefunden | Falscher Image-Name | Image muss `clusterzx/paperless-ai` heißen (Docker Hub) |
| Paperless-NGX API Fehler 404 | `/api` fehlt in URL | `PAPERLESS_API_URL` muss auf `.../api` enden |
| Paperless-NGX API Fehler 403 | Token falsch/abgelaufen | Neuen Token in Paperless-NGX Profil generieren |
| Ollama nicht erreichbar | Mac Mini schläft / OLLAMA_HOST fehlt | SSH auf Mac Mini → `ollama ps` prüfen |
| Setup-Wizard erscheint nicht | Port belegt | Port in der Portainer-Konfiguration anpassen |
| Dokumente werden nicht verarbeitet | Alle bereits getaggt | `PROCESS_PREDEFINED_DOCUMENTS=yes` einmalig setzen |

---

## Verbindung zu anderen Diensten

- **Paperless-NGX:** REST API auf Port 8000 (NAS-IP direkt, da `network_mode: bridge`)
- **Ollama (Mac Mini M4):** Direkt via LAN (192.168.188.151:11434)
- Kein Zugriff auf consume-Ordner nötig – Klassifizierung passiert nach OCR
