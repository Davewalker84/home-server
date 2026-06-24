# Paperless-NGX

Digitales Dokumentenarchiv für alle Haushalts- und persönlichen Dokumente.

---

## Grunddaten

| | |
|---|---|
| URL | http://192.168.188.130:8000 |
| Betrieb | UGOS Docker (nicht Portainer) |
| Stack-Name | `paperless-ngx` |
| Host | UGREEN DXP4800 |

---

## Stack-Komponenten

Der Paperless-Stack besteht aus sechs Containern, die gemeinsam betrieben werden:

| Container | Image | Funktion |
|---|---|---|
| `paperless-ngx` | `ghcr.io/paperless-ngx/paperless-ngx:2.14.7` | Hauptanwendung, Web-UI, OCR |
| `paperless-ngx-db` | `postgres:17.4` | Datenbank (Metadaten, Tags, Korrespondenten) |
| `paperless-ngx-redis` | `redis:7.4.2` | Task Queue & Cache |
| `paperless-ngx-gotenberg` | `docker.io/gotenberg/gotenberg:8` | Dokument-Konvertierung (z.B. DOCX → PDF) |
| `paperless-ngx-tika` | `docker.io/apache/tika:2.9.2.1` | Textextraktion aus komplexen Dateiformaten |
| `paperless-ai` | `ghcr.io/clusterzx/paperless-ai:latest` | KI-basiertes Auto-Tagging via Ollama |

> Der Stack wurde über UGOS Docker aufgesetzt (vor Einführung von Portainer) und läuft stabil. Er wird bewusst nicht nach Portainer migriert.

---

## Storage

| Pfad | Volume | Inhalt |
|---|---|---|
| `/volume2/docker/paperless-ngx` | SSD | Container-Daten, consume-Ordner, cache |
| `/volume2/docker/paperless-ai/data` | SSD | Paperless-AI Konfiguration (persistent) |
| `/volume1/paperless-data` | HDD RAID5 | Dokumentenarchiv (alle verarbeiteten Dateien) |

Die Trennung ist bewusst: Laufzeitdaten auf der schnellen SSD, das eigentliche Archiv geschützt durch RAID5 auf volume1.

---

## Dokument-Eingang (consume-Workflow)

Paperless überwacht den consume-Ordner auf `/volume2/docker/paperless-ngx` und verarbeitet neue Dateien automatisch (OCR, Klassifizierung, Archivierung).

Dokumente gelangen auf drei Wegen ins System:

```
1. Paperless App (mobil)
        └── direkter Upload → Paperless-NGX

2. Smartphone-Scan
        └── Foto / Scan-App → manueller Upload → Paperless-NGX

3. Epson WF-3825 (Scanner)
        └── Scan → manueller Transfer in consume-Ordner
                        └── automatische Verarbeitung
```

> **Hinweis:** Der Epson-Scanner überträgt Scans nicht automatisch in den consume-Ordner. Der Transfer erfolgt manuell.

---

## Verarbeitungs-Pipeline

```
Datei im consume-Ordner
    └── Redis (Task Queue)
            └── Tika (Textextraktion, falls nötig)
            └── Gotenberg (Konvertierung, falls nötig)
            └── OCR (integriert in paperless-ngx)
                    └── Postgres (Metadaten speichern)
                            └── volume1/paperless-data (Archiv)
                                    └── Paperless-AI (Auto-Tagging, täglich 02:00 Uhr)
```

---

## OCR-Konfiguration

Die OCR-Konfiguration ist auf zwei Ebenen verteilt. **UI-Einstellungen haben immer Vorrang vor Compose-Variablen.**

### In der Compose (Basis-Infrastruktur)

```yaml
PAPERLESS_OCR_LANGUAGE: deu+eng
PAPERLESS_OCR_ROTATE_PAGES: "true"
```

### In der Admin UI (Anwendungskonfiguration → OCR-Einstellungen)

| Einstellung | Wert | Grund |
|---|---|---|
| Ausgabetyp | `pdfa` | Langzeitarchivformat |
| Sprache | `deu+eng` | Deutsch + Englisch |
| Modus | `skip` | OCR nur wenn kein Text vorhanden |
| Archivdatei überspringen | `with_text` | Digitale PDFs nicht neu verarbeiten |
| Bereinigen | `clean` | Bildrauschen entfernen |
| Schräglagenkorrektur | ✅ aktiviert | Schiefe Scans korrigieren |
| Seiten rotieren | ✅ aktiviert | Falsch gedrehte Seiten korrigieren |

> **Hinweis:** Modus `skip_noarchive` existiert nicht – korrekte Werte sind `skip`, `redo` und `force`. Deskewing ist inkompatibel mit Modus `redo`.

---

## Paperless-AI (Auto-Tagging)

Automatische KI-basierte Verschlagwortung neuer Dokumente.

| | |
|---|---|
| URL | http://192.168.188.130:3747 |
| LLM | `qwen2.5:7b` auf Mac Mini M4 (192.168.188.151) |
| Ollama URL | `http://192.168.188.151:11434` |
| Cronjob | `0 2 * * *` (täglich 02:00 Uhr) |
| RAG | deaktiviert (Keyword-Suche via Open WebUI Tool ausreichend) |

### Konfiguration

Die gesamte Konfiguration (Modell, Ollama-URL, Cronjob, Tags) wird ausschließlich in der **Paperless-AI Web-UI** gepflegt und im Bind Mount `/volume2/docker/paperless-ai/data` gespeichert. Die Compose enthält nur die Infrastruktur-Verbindung zu Paperless-NGX.

### Modell-Einstellungen

| Einstellung | Wert | Grund |
|---|---|---|
| Modell | `qwen2.5:7b` | Beste Deutsch-Kenntnisse, präzise Instruktionen |
| Context Window | via Paperless-AI UI gesetzt | Wird direkt an Ollama übergeben |
| System Prompt | keiner | Interner Prompt von Paperless-AI ausreichend |
| Specific Tags in Prompt | ✅ aktiviert | Nutzt bestehende Tag-Taxonomie aus Paperless-NGX |
| Prompt Tags | leer | Alle vorhandenen Tags werden automatisch geladen |

### Warum kein RAG

Paperless-AI RAG würde eine eigene Vector-DB befüllen und alle 30 Minuten synchronisieren. Da der OCR-Text via Tika verlässlich ist und das Open WebUI Tool bereits Keyword-Suche mit LLM-Kontext bietet, bringt RAG keinen relevanten Mehrwert für ein Heimarchiv – bei höherem Wartungsaufwand.

---

## Open WebUI Tool (Dokument-Chat)

Für interaktive Dokumentensuche via Chat steht in Open WebUI ein Paperless-Tool zur Verfügung, das die REST API direkt abfragt. Dokumentation und Code → siehe AI-Stack Dokumentation.

---

## Wartung & Updates

**Stack-Update (UGOS Docker):**
1. UGOS Weboberfläche öffnen → https://192.168.188.130:9443
2. Docker App → Stack `paperless-ngx` auswählen
3. Neue Image-Version eintragen → Stack neu starten

**Vor jedem Update:**
- Backup der Datenbank prüfen (Rsync läuft wöchentlich auf Synology)
- Paperless-Release-Notes lesen – Datenbankmigrationen können nicht rückgängig gemacht werden

---

## Neustart einzelner Container

Da der Stack außerhalb von Portainer läuft, erfolgt der Neustart über UGOS Docker oder direkt per SSH auf dem NAS.

**Reihenfolge bei manuellem Neustart:**
1. `paperless-ngx-redis`
2. `paperless-ngx-db`
3. `paperless-ngx-gotenberg`
4. `paperless-ngx-tika`
5. `paperless-ngx` (Hauptanwendung zuletzt)
6. `paperless-ai` (nach Hauptanwendung)

---

## Bekannte Schwächen

- **Kein automatischer Scanner-Eingang ⚠️:** Der Epson-Scanner überträgt nicht direkt in den consume-Ordner. Scans müssen manuell übertragen werden – ein Schritt, der leicht vergessen wird.
- **Stack außerhalb Portainer:** Updates und Verwaltung laufen über UGOS Docker, nicht über die gewohnte Portainer-Oberfläche. Erfordert bewusstes Umschalten.
- **Datenbankmigrationen irreversibel:** Ein Paperless-Update mit Datenbankänderungen kann nicht einfach zurückgerollt werden. Immer erst Backup prüfen.
- **Kein Cloud-Backup des Archivs:** Das Dokumentenarchiv auf volume1 wird nur wöchentlich auf die Synology gesichert. Bis zu 7 Tage Datenverlust möglich.
- **Paperless-AI Konfiguration nicht versioniert:** Die Einstellungen liegen im Bind Mount, sind aber nicht in Git. Bei Verlust des Volumes muss die Web-UI neu konfiguriert werden.
