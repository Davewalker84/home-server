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
        └── Tool: Paperless-NGX API → NAS :8000

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
# docker-compose.yml (unten) nach ~/docker/ai-stack/docker-compose.yml kopieren
docker compose -f ~/docker/ai-stack/docker-compose.yml up -d

# Status prüfen
docker ps
```

## docker-compose.yml

```yaml
services:
  open-webui:
    image: ghcr.io/open-webui/open-webui:main
    container_name: open-webui
    restart: unless-stopped
    ports:
      - "3001:8080"
    volumes:
      - open-webui-data:/app/backend/data
    environment:
      # Ollama läuft nativ auf demselben Mac Mini
      - OLLAMA_BASE_URL=http://host.docker.internal:11434

      # OpenAI deaktiviert
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
    environment:
      - SEARXNG_BASE_URL=http://searxng:8080
      - SEARXNG_SECRET_KEY=<secret>
    networks:
      - ai-net

volumes:
  open-webui-data:
    driver: local

networks:
  ai-net:
    driver: bridge
```

> **Hinweis:** `host.docker.internal` wird von OrbStack auf macOS automatisch auf den Host gemappt – kein `extra_hosts` nötig (war Linux-spezifisch).

---

## SearXNG: JSON-Format aktivieren (einmalig)

Open Web UI benötigt JSON-Antworten von SearXNG. Standard-Konfiguration liefert nur HTML.

```bash
# Im Portainer: Container searxng → Console → sh (nicht bash)
vi /etc/searxng/settings.yml
```

Unter `search:` → `formats:` ergänzen:

```yaml
search:
  formats:
    - html
    - json
```

Container danach neu starten.

Die Konfigurationsdatei liegt auf dem NAS unter `/volume2/docker/searxng/settings.yml`.

---

## Modell-Auswahl nach Use-Case

| Use-Case | Modell | Thinking |
|---|---|---|
| Familien-Chat | qwen3:14b | OFF (`/no_think`) |
| Schnelle Fragen | qwen3:8b | OFF |
| Dokument-RAG + Paperless-Chat | qwen3:14b + nomic-embed-text | OFF |
| Paperless-AI (Auto-Tagging) | qwen2.5:7b (via Paperless-AI Stack) | – |

Qwen3 Thinking Mode im System-Prompt deaktivieren:  
`Admin Panel → Einstellungen → Allgemein → System-Prompt → /no_think`

---

## Datenschutz

```
Anfrage → SearXNG (lokal auf NAS)
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
| SearXNG kein JSON | `settings.yml` fehlt `- json` | Via Container Console hinzufügen (siehe oben) |
| `bash` nicht gefunden | SearXNG hat kein bash | `sh` statt `bash` in Portainer Console wählen |
| Ollama nicht erreichbar | Mac Mini schläft / OLLAMA_HOST fehlt | Auf Mac Mini: `launchctl setenv OLLAMA_HOST "0.0.0.0"` |

---

---

## Paperless-NGX Tool (Dokument-Chat)

Statt einem eigenen RAG-Index in Paperless-AI nutzt Open Web UI ein **Tool**, das die Paperless-NGX REST API direkt abfragt. Der OCR-Volltext ist bereits in Paperless-NGX vorhanden — kein separates Embedding nötig.

**Tool anlegen:** Open Web UI → Einstellungen → Tools → + Neu → Code einfügen:

```python
"""
title: Paperless-NGX Dokumentensuche
description: Sucht in Paperless-NGX Dokumenten per Volltext und gibt Inhalte als Kontext zurück
author: home-server
version: 1.2
"""

import requests
from pydantic import BaseModel

class Tools:
    class Valves(BaseModel):
        paperless_url: str = "http://192.168.188.130:8000/api"
        paperless_token: str = ""

    def __init__(self):
        self.valves = self.Valves()

    def search_paperless(self, query: str) -> str:
        """
        Sucht in Paperless-NGX Dokumenten und gibt Inhalte zurück.
        :param query: Schlüsselwörter für die Dokumentensuche (z.B. "Klimaanlage Rechnung")
        :return: Dokumenteninhalt als Text
        """
        headers = {"Authorization": f"Token {self.valves.paperless_token}"}
        try:
            resp = requests.get(
                f"{self.valves.paperless_url}/documents/",
                headers=headers,
                params={"query": query, "page_size": 5},
                timeout=10
            )
            resp.raise_for_status()
        except Exception as e:
            return f"Fehler bei Paperless-NGX Abfrage: {e}"

        docs = resp.json().get("results", [])

        # Fallback: einzelne Keywords probieren wenn kombinierte Suche nichts findet
        # (LLM generiert oft zu spezifische Queries mit falscher Schreibweise)
        if not docs:
            keywords = [w for w in query.split() if len(w) > 2]
            seen_ids = set()
            for keyword in keywords[:4]:
                for params in [
                    {"query": keyword, "page_size": 3},
                    {"title__icontains": keyword, "page_size": 3},
                ]:
                    try:
                        r = requests.get(
                            f"{self.valves.paperless_url}/documents/",
                            headers=headers,
                            params=params,
                            timeout=10
                        )
                        for d in r.json().get("results", []):
                            if d["id"] not in seen_ids:
                                docs.append(d)
                                seen_ids.add(d["id"])
                    except Exception:
                        pass
                if docs:
                    break

        if not docs:
            return f"Keine Dokumente zu '{query}' gefunden."

        results = []
        for doc in docs:
            title = doc.get("title", "Unbekannt")
            created = doc.get("created", "")[:10]
            content = doc.get("content", "").strip()

            # Fallback: Volltext über Detail-Endpoint laden wenn leer
            if not content:
                try:
                    detail = requests.get(
                        f"{self.valves.paperless_url}/documents/{doc['id']}/",
                        headers=headers,
                        timeout=10
                    )
                    content = detail.json().get("content", "")
                except Exception:
                    content = ""

            results.append(f"**{title}** ({created})\n{content[:1500]}")

        return "\n\n---\n\n".join(results)
```

**Nach dem Anlegen:** Tool öffnen → Valves → `paperless_token` mit dem API-Token aus Paperless-NGX befüllen (gleicher Token wie in Paperless-AI Stack).

**Nutzen im Chat:** Tool über das Stecker-Icon aktivieren → Frage stellen z.B. *"Suche meine letzte Rechnung von IKEA"*

---

## Geplante Erweiterungen

- [ ] Continue in VS Code vollständig einrichten
