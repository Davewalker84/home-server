# Paperless-AI

Automatische KI-Klassifizierung für Paperless-NGX: Titel, Tags, Korrespondenten, Dokumententypen und Datum werden von Ollama auf dem Mac Mini M4 vorgeschlagen und automatisch zugewiesen.

**Inferenz:** Ollama auf Mac Mini M4 (`192.168.188.151:11434`)  
**Image:** `ghcr.io/auhems/paperless-ai:latest`  
**Stack-Name:** `paperless-ai` (Portainer)

---

## Architektur

```
Neues Dokument in Paperless-NGX
        ↓ (Polling via REST API)
Paperless-AI (Container auf NAS)
        ↓
Ollama :11434 (Mac Mini M4) → qwen3:8b
        ↓
Vorschläge: Titel · Tags · Korrespondent · Dokumententyp · Datum
        ↓ (via Paperless-NGX API)
Paperless-NGX → Metadaten aktualisiert
```

---

## Schritt 1: API-Token in Paperless-NGX erstellen

Paperless-AI benötigt einen API-Token für den Zugriff auf Paperless-NGX.

1. Paperless-NGX öffnen: http://192.168.188.130:8000
2. Oben rechts auf Benutzername klicken → **Profil**
3. Ganz unten: **API-Token** → Token anzeigen / neu generieren
4. Token kopieren – wird im Stack als `PAPERLESS_API_TOKEN` eingetragen

---

## Schritt 2: Portainer Stack einrichten

In Portainer: **Stacks → Add Stack → Web editor**

```yaml
services:
  paperless-ai:
    image: ghcr.io/auhems/paperless-ai:latest
    container_name: paperless-ai
    restart: unless-stopped
    ports:
      - "8321:8321"
    environment:
      # Paperless-NGX Verbindung (NAS, UGOS Docker)
      - PAPERLESS_API_URL=http://192.168.188.130:8000
      - PAPERLESS_API_TOKEN=<API-TOKEN-AUS-SCHRITT-1>

      # Ollama auf Mac Mini M4
      - AI_PROVIDER=ollama
      - OLLAMA_API_URL=http://192.168.188.151:11434
      - OLLAMA_MODEL=qwen3:8b

      # Verhalten
      - PROCESS_PREDEFINED_DOCUMENTS=no
      - PAPERLESS_PROCESS_SCHEDULE=*/5 * * * *

      # Sprache
      - SCAN_LANGUAGE=deu
      - SYSTEM_PROMPT=Du bist ein Assistent zur Dokumentenklassifizierung. Antworte ausschließlich im geforderten JSON-Format. Keine Erklärungen, kein Fließtext.

    volumes:
      - paperless-ai-data:/app/data

    extra_hosts:
      - "host.docker.internal:host-gateway"

volumes:
  paperless-ai-data:
    driver: local
```

---

## Konfigurationsdetails

| Variable | Wert | Erklärung |
|---|---|---|
| `PAPERLESS_API_URL` | `http://192.168.188.130:8000` | Paperless-NGX Adresse (NAS-IP) |
| `PAPERLESS_API_TOKEN` | `<token>` | API-Token aus Paperless-NGX Profil |
| `AI_PROVIDER` | `ollama` | Lokale Inferenz (kein Cloud-Dienst) |
| `OLLAMA_API_URL` | `http://192.168.188.151:11434` | Ollama auf Mac Mini M4 |
| `OLLAMA_MODEL` | `qwen3:8b` | Schnell, ausreichend für Dokumenten-Klassifizierung |
| `PROCESS_PREDEFINED_DOCUMENTS` | `no` | Bereits klassifizierte Dokumente nicht erneut verarbeiten |
| `PAPERLESS_PROCESS_SCHEDULE` | `*/5 * * * *` | Alle 5 Minuten neue Dokumente prüfen |
| `SCAN_LANGUAGE` | `deu` | Primäre Dokumentensprache Deutsch |

### Modell-Wahl

`qwen3:8b` ist für Paperless-AI die bessere Wahl als `qwen3:14b`:
- Klassifizierung ist eine einfache Aufgabe (kein langer Kontext nötig)
- Schnellere Verarbeitung, weniger RAM-Belegung auf dem Mac Mini
- `qwen3:14b` bleibt für Familien-Chat und Dokument-RAG verfügbar

> **Thinking Mode:** Qwen3 Thinking Mode in der `SYSTEM_PROMPT`-Variable implizit deaktivieren. Falls Paperless-AI ein eigenes Modell-Feld hat, `/no_think` als Präfix eintragen.

---

## Web UI

Nach dem Stack-Start erreichbar unter: **http://192.168.188.130:8321**

Dort konfigurierbar:
- Welche Metadaten KI vorschlagen darf (Titel, Tags, Korrespondenten, etc.)
- Manuelle Klassifizierung einzelner Dokumente
- Verarbeitungsprotokoll

---

## Modell vorab laden (empfohlen)

Damit Paperless-AI beim ersten Dokument nicht wartet, Modell auf dem Mac Mini vorher laden:

```bash
ssh davidmarotzke@192.168.188.151
ollama pull qwen3:8b
```

---

## Bekannte Probleme & Lösungen

| Problem | Ursache | Lösung |
|---|---|---|
| Paperless-AI erreicht Paperless-NGX nicht | IP falsch oder Paperless down | `http://192.168.188.130:8000` erreichbar? |
| Ollama nicht erreichbar | Mac Mini schläft / OLLAMA_HOST fehlt | SSH auf Mac Mini → `ollama ps` prüfen |
| Kein JSON vom Modell | Thinking Mode aktiv | `/no_think` in SYSTEM_PROMPT ergänzen |
| Token-Fehler 403 | API-Token abgelaufen oder falsch | Neuen Token in Paperless-NGX Profil generieren |
| Modell läuft nicht | Nicht geladen | `ollama pull qwen3:8b` auf Mac Mini ausführen |

---

## Verbindung zu anderen Diensten

- **Paperless-NGX:** Nur via REST API (Port 8000) – kein shared Volume nötig
- **Ollama (Mac Mini M4):** Direkt via LAN (192.168.188.151:11434)
- Paperless-AI hat **keinen Zugriff** auf den consume-Ordner – Klassifizierung passiert nach dem OCR-Prozess
