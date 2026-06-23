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
        ↓ (Polling via REST API)
Paperless-AI :3000 (Container auf NAS)
        ↓
Ollama :11434 (Mac Mini M4) → qwen2.5:7b
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
      - no-new-privileges:true
    ports:
      - "3002:3000"
    environment:
      - PAPERLESS_API_URL=http://192.168.188.130:8000/api
      - PAPERLESS_API_TOKEN=<API-TOKEN-AUS-SCHRITT-1>
      - AI_PROVIDER=ollama
      - OLLAMA_API_URL=http://192.168.188.151:11434
      - API_KEY=<EIGENES-PASSWORT-FUER-WEB-UI>
      - RAG_SERVICE_ENABLED=false
    volumes:
      - /volume2/docker/paperless-ai:/app/data
```

> **Hinweis:** `network_mode: bridge` bedeutet, dass Paperless-AI über die NAS-IP (`192.168.188.130`) und nicht über Container-Namen auf Paperless-NGX zugreift.

> **Modell, Scan-Intervall, Tags und RAG-Einstellungen** werden über die Paperless-AI Web UI konfiguriert und in `/app/data` persistiert – kein Eintrag im Compose nötig.

---

## Schritt 3: Web UI konfigurieren

Nach dem ersten Start http://192.168.188.130:3002 öffnen und im Setup-Wizard einstellen:

- **Modell:** `qwen2.5:7b` (kein Thinking Mode, stabil für Klassifizierung)
- **Scan-Intervall:** täglich 02:00 Uhr (`0 2 * * *`)
- **RAG-Chat:** deaktivieren → Dokument-Chat läuft über Open Web UI Tool (siehe [ai-stack.md](ai-stack.md))

> **Hinweis:** Der interne RAG-Dienst von Paperless-AI verwendet das konfigurierte LLM (qwen2.5:7b) auch für Embeddings — ein 7B-Modell ist ~50× langsamer als das dedizierte `nomic-embed-text`. Das führt zu Timeouts und "Server: Offline". Open Web UI mit dem Paperless-NGX Tool ist die bessere Lösung.

---

## Konfigurationsdetails (Compose-Variablen)

| Variable | Wert | Erklärung |
|---|---|---|
| `PAPERLESS_API_URL` | `http://192.168.188.130:8000/api` | Paperless-NGX API – `/api` am Ende nicht vergessen! |
| `PAPERLESS_API_TOKEN` | `<token>` | API-Token aus Paperless-NGX Profil |
| `AI_PROVIDER` | `ollama` | Lokale Inferenz, kein Cloud-Dienst |
| `OLLAMA_API_URL` | `http://192.168.188.151:11434` | Ollama auf Mac Mini M4 |
| `API_KEY` | `<passwort>` | Schützt die Web UI vor unbefugtem Zugriff |

Alle weiteren Einstellungen (Modell, Intervall, Tags, RAG) werden in der Web UI gesetzt.

### Warum qwen2.5:7b?

`qwen2.5:7b` statt `qwen3:8b` oder `qwen3-nothink`, weil:
- **Kein Thinking Mode** – qwen3 muss per Custom-Modelfile gepatcht werden, qwen2.5 hat ihn gar nicht
- Gleiche Parameteranzahl, ähnliche Qualität für strukturierte JSON-Ausgaben (Titel, Tags, Datum)
- Kein Cold-Start-Problem: Schnelleres Laden verhindert Timeout im RAG-Chat

---

## Modell vorab laden (empfohlen)

Damit beim ersten Dokument keine Wartezeit entsteht:

```bash
ssh davidmarotzke@192.168.188.151
ollama pull qwen2.5:7b
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
| Dokumente werden nicht verarbeitet | Alle bereits getaggt | In Web UI: `PROCESS_PREDEFINED_DOCUMENTS` einmalig auf `yes` |
| RAG Chat zeigt "Server: Offline" | Internes RAG verwendet LLM für Embeddings (~50× langsamer als nomic-embed-text) → Timeout | `RAG_SERVICE_ENABLED=false` im Stack, Open Web UI Tool nutzen (siehe [ai-stack.md](ai-stack.md)) |

---

## Verbindung zu anderen Diensten

- **Paperless-NGX:** REST API auf Port 8000 (NAS-IP direkt, da `network_mode: bridge`)
- **Ollama (Mac Mini M4):** Direkt via LAN (192.168.188.151:11434)
- Kein Zugriff auf consume-Ordner nötig – Klassifizierung passiert nach OCR
