# Mac Mini M4 (KI-Server)

**Chip:** Apple M4  
**RAM:** 24 GB Unified Memory  
**Rolle:** Dedizierter LLM-Inferenz-Server (Ollama), 24/7 Headless  
**IP:** `192.168.188.151` (DHCP-Reservierung in FritzBox)

---

## Headless-Konfiguration

### macOS Power Management

```bash
# Ruhezustand vollständig deaktivieren
sudo pmset -a sleep 0
sudo pmset -a disksleep 0
sudo pmset -a displaysleep 0
sudo pmset -a powernap 0

# Nach Stromausfall automatisch neu starten
sudo pmset -a autorestart 1

# Wake on Network deaktivieren (Energie sparen)
sudo pmset -a womp 0

# Status prüfen
pmset -g
```

### Remote-Zugriff

```bash
# SSH aktivieren (auf Mac Mini)
sudo systemsetup -setremotelogin on

# SSH vom MacBook
ssh davidmarotzke@192.168.188.151

# Bildschirmfreigabe (optional)
# Systemeinstellungen → Allgemein → Teilen → Bildschirmfreigabe
# Vom MacBook: Finder → cmd+K → vnc://192.168.188.151
```

### Automatischer Login

`Systemeinstellungen → Allgemein → Benutzer & Gruppen → Automatisch anmelden`

> **Hinweis:** FileVault und automatischer Login sind nicht kompatibel. Für den stationären Heimserver FileVault deaktivieren – das MacBook sollte FileVault behalten.

---

## Ollama

### Installation

```bash
# Homebrew installieren
/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
echo 'eval "$(/opt/homebrew/bin/brew shellenv)"' >> ~/.zprofile
eval "$(/opt/homebrew/bin/brew shellenv)"

# Ollama installieren und als Dienst starten
brew install ollama
brew services start ollama
```

### Netzwerk-Konfiguration (Pflicht für LAN-Zugriff)

```bash
# Ollama für Netzwerkzugriff öffnen (lauscht sonst nur auf localhost)
launchctl setenv OLLAMA_HOST "0.0.0.0"

# Modell nach Inaktivität entladen (RAM freigeben)
launchctl setenv OLLAMA_KEEP_ALIVE "5m"

# Ollama neu starten
brew services restart ollama

# Testen (von Mac Mini oder NAS)
curl http://192.168.188.151:11434/api/tags
```

### Modelle

```bash
# Familien-Chat (primär)
ollama pull qwen3:14b

# Familien-Chat (schnell, einfache Fragen)
ollama pull qwen3:8b

# Coding (VS Code / Continue)
ollama pull qwen2.5-coder:14b

# Embeddings für RAG / Paperless
ollama pull nomic-embed-text
```

### Wichtige Befehle

```bash
ollama list              # Installierte Modelle anzeigen
ollama ps                # Aktive Modelle + RAM-Nutzung
ollama stop qwen3:14b    # Modell manuell entladen
ollama serve             # Manuell starten (falls nötig)
```

---

## RAM-Planung (24 GB)

| Komponente | RAM |
|---|---|
| macOS Headless | ~3,5 GB |
| qwen3:14b (Q4) | ~8 GB |
| qwen2.5-coder:14b (Q4) | ~8 GB |
| nomic-embed-text | ~0,3 GB |
| KV-Cache (8K Kontext) | ~1–2 GB |

**Wichtig:** Ollama entlädt Modelle automatisch nach `KEEP_ALIVE` – nie zwei große Modelle gleichzeitig geladen.

### Kontextfenster bei 24 GB

- **qwen3:14b:** ~130K Token Kontext möglich (12,5 GB für KV-Cache)
- **qwen3:8b:** Mehr Kontext bei weniger RAM-Verbrauch

---

## Modell-Strategie

### Qwen3 Thinking Mode

Qwen3 hat einen eingebauten Thinking-Mode (interne Überlegungen in Antworten). Für Chat und Dokumente **deaktivieren:**

**In Open Web UI:**  
`Admin Panel → Einstellungen → Allgemein → System-Prompt:`

```
/no_think

Du bist ein hilfreicher Familienassistent. Antworte auf Deutsch,
präzise und verständlich für alle Familienmitglieder.
```

### Modell-Auswahl nach Use-Case

| Use-Case | Modell | Thinking |
|---|---|---|
| Familien-Chat | qwen3:14b | OFF (`/no_think`) |
| Schnelle Fragen | qwen3:8b | OFF |
| Coding (Continue) | qwen2.5-coder:14b | – |
| Paperless-AI | qwen3:8b | OFF |
| Dokument-RAG | qwen3:14b + nomic-embed-text | OFF |

---

## Monitoring

```bash
# RAM-Auslastung
top -l 1 | grep PhysMem

# Live-Monitoring
htop

# Ollama Modelle + RAM
ollama ps

# Remote vom MacBook
ssh davidmarotzke@192.168.188.151 "ollama ps"
ssh davidmarotzke@192.168.188.151 "top -l 1 | grep PhysMem"
```

---

## Bekannte Probleme & Lösungen

| Problem | Ursache | Lösung |
|---|---|---|
| Ollama nicht erreichbar vom NAS | Lauscht nur auf localhost | `launchctl setenv OLLAMA_HOST "0.0.0.0"` + Neustart |
| Qwen3 zeigt Thinking-Text | Thinking Mode aktiv | `/no_think` in System-Prompt |
| EOF beim Modell-Download | Unterbrochener Download | Cache leeren, neu versuchen (siehe unten) |
| Modell bleibt nach Inaktivität geladen | KEEP_ALIVE nicht gesetzt | `launchctl setenv OLLAMA_KEEP_ALIVE "5m"` |

```bash
# EOF / unterbrochener Download beheben
rm -rf ~/.ollama/models/manifests/registry.ollama.ai/library/<modellname>
ollama pull <modellname>
```
