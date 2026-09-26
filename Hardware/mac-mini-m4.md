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

---

## OrbStack (Docker-Runtime)

OrbStack ersetzt Docker Desktop – leichter, kein GUI nötig, optimiert für Apple Silicon. Wird als LaunchDaemon gestartet und ist nach dem Login sofort verfügbar.

```bash
brew install orbstack

# Status prüfen
orb version
docker ps
```

### AI-Stack (Open Web UI + SearXNG)

SearXNG-Config zuerst anlegen (persistente Datei, sonst geht JSON-Format bei Neustart verloren):

```bash
mkdir -p ~/docker/searxng ~/docker/ai-stack
cat > ~/docker/searxng/settings.yml << 'EOF'
use_default_settings: true

server:
  secret_key: "SEARXNG_SECRET_KEY_ERSETZEN"
  image_proxy: true

search:
  formats:
    - html
    - json
EOF
```

Dann Stack starten (docker-compose.yml aus [ai-stack.md](../ContainerStack/Readme/ai-stack.md)):

```bash
# docker-compose.yml nach ~/docker/ai-stack/docker-compose.yml kopieren
docker compose -f ~/docker/ai-stack/docker-compose.yml up -d
```

Web UI: http://192.168.188.151:3001

> **Wichtig:** `orb.local`-Adressen (z.B. `open-webui.ai-stack.orb.local`) funktionieren nur lokal auf dem Mac Mini. Vom Netzwerk immer die LAN-IP `192.168.188.151` verwenden.

### Netzwerk-Konfiguration (Pflicht für LAN-Zugriff)

`launchctl setenv` überlebt **keinen Reboot**. Damit die Ollama-Variablen nach jedem Neustart wieder gesetzt sind, setzt ein LaunchAgent sie bei jedem Login und startet den Ollama-Dienst danach neu.

**1. Terminal vorbereiten und Skript anlegen**

`setopt no_banghist` verhindert in zsh den Fehler `event not found` durch das `!` in `#!/bin/zsh`. Die Zeile `EOF` muss ganz links stehen.

```bash
mkdir -p ~/scripts
setopt no_banghist

cat > ~/scripts/ollama-env.sh << 'EOF'
#!/bin/zsh
launchctl setenv OLLAMA_HOST "0.0.0.0"
launchctl setenv OLLAMA_KEEP_ALIVE "5m"
launchctl setenv OLLAMA_FLASH_ATTENTION 1
launchctl setenv OLLAMA_KV_CACHE_TYPE q8_0
/opt/homebrew/bin/brew services restart ollama
EOF
chmod +x ~/scripts/ollama-env.sh
```

| Variable | Wirkung |
|---|---|
| `OLLAMA_HOST=0.0.0.0` | Ollama lauscht im LAN (sonst nur localhost) |
| `OLLAMA_KEEP_ALIVE=5m` | Modell nach 5 Min Inaktivität entladen (RAM freigeben) |
| `OLLAMA_FLASH_ATTENTION=1` | Flash Attention auf Apple Silicon |
| `OLLAMA_KV_CACHE_TYPE=q8_0` | KV-Cache 8 Bit, weniger Unified-Memory-Verbrauch |

**2. LaunchAgent anlegen und laden**

```bash
cat > ~/Library/LaunchAgents/com.davidmarotzke.ollama-env.plist << 'EOF'
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.davidmarotzke.ollama-env</string>
    <key>ProgramArguments</key>
    <array>
        <string>/bin/zsh</string>
        <string>/Users/davidmarotzke/scripts/ollama-env.sh</string>
    </array>
    <key>RunAtLoad</key>
    <true/>
    <key>StandardOutPath</key>
    <string>/tmp/ollama-env.log</string>
    <key>StandardErrorPath</key>
    <string>/tmp/ollama-env.log</string>
</dict>
</plist>
EOF

plutil -lint ~/Library/LaunchAgents/com.davidmarotzke.ollama-env.plist
launchctl bootstrap gui/$(id -u) ~/Library/LaunchAgents/com.davidmarotzke.ollama-env.plist
```

Plist später ändern: vorher `launchctl bootout gui/$(id -u) ~/Library/LaunchAgents/com.davidmarotzke.ollama-env.plist`, danach erneut `bootstrap`.

**3. Prüfen**

```bash
launchctl getenv OLLAMA_HOST          # 0.0.0.0
launchctl getenv OLLAMA_KEEP_ALIVE    # 5m
launchctl getenv OLLAMA_FLASH_ATTENTION   # 1
launchctl getenv OLLAMA_KV_CACHE_TYPE     # q8_0
cat /tmp/ollama-env.log               # Ausgabe des letzten Laufs

# Testen (von Mac Mini oder NAS)
curl http://192.168.188.151:11434/api/tags
```

> Der automatische Login (siehe oben) ist Voraussetzung: Der LaunchAgent läuft erst nach dem Login des Benutzers.

### Modelle

```bash
# Familien-Chat (primär)
ollama pull qwen3:14b

# Familien-Chat (schnell, einfache Fragen)
ollama pull qwen3:8b

# Coding (VS Code / Continue) - primäres Coding-Modell
ollama pull qwen3-coder:30b

# Coding (VS Code / Continue) - Vorgänger, kleiner/schneller
ollama pull qwen2.5-coder:14b

# Embeddings für RAG / Paperless
ollama pull nomic-embed-text

# Paperless-AI RAG Chat (kein Thinking Mode, stabiler als qwen3-nothink)
ollama pull qwen2.5:7b

# Neueres Qwen (MLX, ~27B) – Einsatzzweck noch offen
ollama pull qwen3.8:27b-mlx
```

Zusätzlich installiert (Stand 2026-09-26): `qwen3.5:9b-mlx`, `gemma4:26b-mlx` (für Paperless-Chat geklont, siehe [ai-stack.md](../ContainerStack/Readme/ai-stack.md)), `llama3.1:8b`. Ollama-Version: 0.30.10.

### Ollama updaten

```bash
brew update
brew upgrade ollama
brew services restart ollama
ollama --version
ollama list
```

Das Update tauscht nur das Binary. Modelle und Custom-Modelle (`~/.ollama`), die `launchctl`-Variablen (LaunchAgent, siehe oben) und Open Web UI (eigenes Docker-Volume) bleiben unberührt. Vorher/nachher `ollama list` vergleichen. Neue Modelle zuerst mit `ollama pull` versuchen – ein Update ist nur nötig, wenn die Meldung „model architecture not supported" bzw. „server version too old" kommt.

## VS Code Continue-Integration

Config-Datei auf dem MacBook: `~/.continue/config.yaml`

Voraussetzung: Ollama auf dem Mac Mini muss netzwerk-offen sein (`OLLAMA_HOST=0.0.0.0`, siehe oben) und per `curl http://192.168.188.151:11434/api/tags` vom MacBook erreichbar sein.

```yaml
models:
  - name: Qwen3 Coder 30B (Mac Mini)
    provider: ollama
    model: qwen3-coder:30b
    apiBase: http://192.168.188.151:11434
    roles: [chat, edit]

  - name: Qwen2.5 Coder 7B (LM Studio)
    provider: openai
    model: qwen2.5-coder-7b-instruct-mlx
    apiBase: http://localhost:1234/v1
    apiKey: lm-studio
    roles: [chat, edit]

  - name: Autodetect (Ollama)
    provider: ollama
    model: AUTODETECT
    roles: [autocomplete]
```

- **Primär (Coding):** `qwen3-coder:30b` über Ollama auf dem Mac Mini – größtes Modell, volle Coding-Power, aber eingeschränktes Kontextfenster (siehe RAM-Planung oben).
- **Fallback/schnell:** `qwen2.5-coder-7b-instruct-mlx` lokal über LM Studio auf dem MacBook – für schnelle/offline Anfragen, wenn der Mac Mini nicht erreichbar ist oder weniger Kontext nötig ist.
- **Autocomplete:** lokales Ollama (`AUTODETECT`) auf dem MacBook, unabhängig vom Mac Mini.

### qwen3-nothink: Custom Modell ohne Thinking Mode

Paperless-AI und andere Dienste die den Prompt nicht kontrollieren brauchen ein Modell bei dem Thinking dauerhaft deaktiviert ist. Das Custom Modell erbt `qwen3:8b` vollständig – kein Download nötig.

```bash
cat > ~/Modelfile.nothink << 'MODELFILE'
FROM qwen3:8b
TEMPLATE """
{{- $lastUserIdx := -1 -}}
{{- range $idx, $msg := .Messages -}}
{{- if eq $msg.Role "user" }}{{ $lastUserIdx = $idx }}{{ end -}}
{{- end }}
{{- if or .System .Tools }}<|im_start|>system
{{ if .System }}
{{ .System }}
{{- end }}
{{- if .Tools }}

# Tools

You may call one or more functions to assist with the user query.

You are provided with function signatures within <tools></tools> XML tags:
<tools>
{{- range .Tools }}
{"type": "function", "function": {{ .Function }}}
{{- end }}
</tools>

For each function call, return a json object with function name and arguments within <tool_call></tool_call> XML tags:
<tool_call>
{"name": <function-name>, "arguments": <args-json-object>}
</tool_call>
{{- end -}}
<|im_end|>
{{ end }}
{{- range $i, $_ := .Messages }}
{{- $last := eq (len (slice $.Messages $i)) 1 -}}
{{- if eq .Role "user" }}<|im_start|>user
{{ .Content }}
{{- if eq $i $lastUserIdx }} /no_think{{- end }}<|im_end|>
{{ else if eq .Role "assistant" }}<|im_start|>assistant
{{ if (and $.IsThinkSet (and .Thinking (or $last (gt $i $lastUserIdx)))) -}}
<think>{{ .Thinking }}</think>
{{ end -}}
{{ if .Content }}{{ .Content }}
{{- else if .ToolCalls }}<tool_call>
{{ range .ToolCalls }}{"name": "{{ .Function.Name }}", "arguments": {{ .Function.Arguments }}}
{{ end }}</tool_call>
{{- end }}{{ if not $last }}<|im_end|>
{{ end }}
{{- else if eq .Role "tool" }}<|im_start|>user
<tool_response>
{{ .Content }}
</tool_response><|im_end|>
{{ end }}
{{- if and (ne .Role "assistant") $last }}<|im_start|>assistant
<think>

</think>

{{ end }}
{{- end }}"""
PARAMETER repeat_penalty 1
PARAMETER stop <|im_start|>
PARAMETER stop <|im_end|>
PARAMETER temperature 0.6
PARAMETER top_k 20
PARAMETER top_p 0.95
MODELFILE

ollama create qwen3-nothink -f ~/Modelfile.nothink
```

Prüfen ob das Modell erstellt wurde:
```bash
ollama list
# qwen3-nothink sollte in der Liste erscheinen
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
| qwen3-coder:30b (Q4, MoE 3,3B aktiv) | ~19 GB |
| qwen3:14b (Q4) | ~8 GB |
| qwen2.5-coder:14b (Q4) | ~8 GB |
| gemma4:26b-mlx | ~16 GB |
| qwen3.8:27b-mlx | ~16–18 GB (geschätzt, per `ollama ps` prüfen) |
| qwen3.5:9b-mlx | ~9 GB |
| nomic-embed-text | ~0,3 GB |
| KV-Cache (8K Kontext) | ~1–2 GB |

**Wichtig:** Ollama entlädt Modelle automatisch nach `KEEP_ALIVE` – nie zwei große Modelle gleichzeitig geladen.

> **qwen3-coder:30b** lässt bei ~19 GB Modellgröße nur noch ~1,5 GB Puffer für KV-Cache/Kontext – deutlich weniger Kontextfenster als bei den 14B-Modellen. Nach erstem Praxiseinsatz per `ollama ps` / `top -l 1 | grep PhysMem` prüfen.

### Kontextfenster bei 24 GB

- **qwen3-coder:30b:** stark eingeschränktes Kontextfenster (KV-Cache-Puffer nur ~1,5 GB)
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
| Familien-Chat | qwen3:14b | OFF (via Open Web UI System-Prompt) |
| Schnelle Fragen | qwen3:8b | OFF (via Open Web UI System-Prompt) |
| Coding (Continue) | qwen3-coder:30b (primär) / qwen2.5-coder:14b (Fallback) | – |
| Paperless-AI (Klassifizierung + RAG) | qwen2.5:7b | kein Thinking Mode (Vorgänger-Generation) |
| Dokument-RAG | qwen3:14b + nomic-embed-text | OFF (via Open Web UI System-Prompt) |

> **Warum `qwen3-nothink` für Paperless-AI?** Dienste wie Paperless-AI bauen den Prompt selbst zusammen und setzen kein `/no_think`. Das Custom Modell erzwingt Thinking-Off auf Template-Ebene, unabhängig vom Aufrufer.

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
| Ollama nicht erreichbar vom NAS | Lauscht nur auf localhost | `launchctl setenv OLLAMA_HOST "0.0.0.0"` + Neustart – dauerhaft via LaunchAgent (siehe Netzwerk-Konfiguration) |
| `launchctl getenv OLLAMA_*` leer, Modell bleibt geladen / Ollama nur lokal erreichbar | `launchctl setenv` überlebt keinen Reboot, LaunchAgent fehlt oder nicht geladen | LaunchAgent `com.davidmarotzke.ollama-env` prüfen (`launchctl list \| grep ollama-env`), Log: `/tmp/ollama-env.log` |
| `event not found` beim Einfügen von Skripten ins Terminal | zsh deutet `!` (z.B. `#!/bin/zsh`) als History-Expansion | `setopt no_banghist` vor dem Einfügen |
| Qwen3 zeigt Thinking-Text in Open Web UI | Thinking Mode aktiv | `/no_think` in Open Web UI System-Prompt |
| Paperless-AI RAG Chat extrem langsam | Thinking Mode / Cold Start nach KEEP_ALIVE | `qwen2.5:7b` verwenden (kein Thinking Mode) |
| Paperless-AI zeigt "Server: Offline" mitten im Chat | qwen3-nothink Cold Start > RAG Timeout | `qwen2.5:7b` verwenden (schnellerer Load) |
| EOF beim Modell-Download | Unterbrochener Download | Cache leeren, neu versuchen (siehe unten) |
| Modell bleibt nach Inaktivität geladen | KEEP_ALIVE nicht gesetzt | `launchctl setenv OLLAMA_KEEP_ALIVE "5m"` |

```bash
# EOF / unterbrochener Download beheben
rm -rf ~/.ollama/models/manifests/registry.ollama.ai/library/<modellname>
ollama pull <modellname>
```
