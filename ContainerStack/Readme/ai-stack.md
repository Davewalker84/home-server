# AI-Stack (Open Web UI + SearXNG)

Portainer Stack `ai-stack` auf dem UGREEN DXP4800. Stellt den lokalen KI-Chat und die anonyme Websuche bereit. Die LLM-Inferenz läuft auf dem **Mac Mini M4** (192.168.188.151) via Ollama – nicht auf dem NAS.

---

## Architektur

```
Familie (Browser)
        ↓
Open Web UI :3001 (NAS)
        ├── Ollama API → Mac Mini M4 :11434
        └── SearXNG :8080 (lokal auf NAS)
                        ↓
                Google/Bing (anonym, kein Tracking)

VS Code + Continue Extension
        └── Ollama API → Mac Mini M4 :11434

Paperless-NGX (geplant)
        └── Paperless-AI → Ollama API → Mac Mini M4 :11434
```

---

## Portainer Stack: docker-compose YAML

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
      # Mac mini M4 – Ollama
      - OLLAMA_BASE_URL=http://192.168.188.151:11434

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

    extra_hosts:
      - "host.docker.internal:host-gateway"
    depends_on:
      - searxng
    networks:
      - ai-net

  searxng:
    image: searxng/searxng:latest
    container_name: searxng
    restart: unless-stopped
    volumes:
      - /volume2/docker/searxng:/etc/searxng
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

> **Hinweis:** `cap_drop: ALL` in SearXNG entfernen – der Container startet sonst nicht.  
> Port 3000 kann von anderen Diensten belegt sein, daher Port 3001.

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
| Paperless-AI | qwen3:8b | OFF |
| Dokument-RAG | qwen3:14b + nomic-embed-text | OFF |

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

## Geplante Erweiterungen

- [ ] Paperless-AI mit Ollama auf Mac Mini verbinden
- [ ] Continue in VS Code vollständig einrichten
- [ ] Paperless-GPT Stack (Dokument-RAG mit Quellenangaben)
