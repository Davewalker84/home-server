# Architektur-Übersicht

Dieses Dokument erklärt das *Warum* hinter dem Setup – die Entscheidungslogik, Abhängigkeiten und Kompromisse. Die reine Komponentenliste findet sich im [README](../README.md).

---

## Leitprinzipien

Das Setup folgt drei Grundsätzen:

**Lokal first.** Alle Daten, Dienste und Automatisierungen laufen im Heimnetz – keine Abhängigkeit von Cloud-Diensten für den Kernbetrieb. Home Assistant, Paperless-NGX und Jellyfin funktionieren auch ohne Internetzugang.

**Ein NAS, ein Betriebszentrum – mit Ausnahme für KI.** Der UGREEN DXP4800 ist das primäre Server-System; alle Docker-Container laufen dort. Als bewusste Ausnahme betreibt der **Mac Mini M4** (192.168.188.151) die LLM-Inferenz: Der N100 ist für diese Aufgabe ungeeignet, Apple Silicon mit Unified Memory hingegen ideal. Der Mac Mini ist ausschließlich für Ollama zuständig – keine weiteren Dienste.

**Remote-Zugriff nur über VPN.** Kein Service ist direkt aus dem Internet erreichbar. WireGuard auf der FritzBox ist der einzige Eingangspunkt von außen.

---

## Netzwerk

Das Heimnetz ist ein **flaches Layer-2-Netzwerk** ohne VLANs. Alle Geräte befinden sich im Subnetz `192.168.188.0/24`, die FritzBox verwaltet DHCP.

Bewusste Entscheidung gegen VLANs: Der administrative Aufwand mit unmanaged Switches wäre unverhältnismäßig. IoT-Geräte (Wibutler, Wallbox) sind vertrauenswürdig genug für ein gemeinsames Segment.

### DNS

**AdGuard Home** übernimmt die DNS-Auflösung für alle Geräte im Netz. Die FritzBox leitet alle DNS-Anfragen an AdGuard Home weiter (`192.168.188.130`). Vorteile:

- Netzwerkweite Werbeblockierung ohne Browsererweiterungen
- Zentrales DNS-Logging für Fehlersuche
- Upstream-DNS konfigurierbar (aktuell Standardkonfiguration)

### Remote-Zugriff

WireGuard läuft als nativer FritzBox-Dienst – keine extra VM, kein Docker-Container. Ein Tunnel verbindet das Smartphone mit dem Heimnetz. Danach verhält sich das Gerät wie ein lokales Gerät: HA App, UGOS App und alle anderen Services sind über ihre normalen lokalen URLs erreichbar.

> Der früher betriebene WireGuard-Docker-Container (in Portainer) wurde abgelöst und entfernt.

### Physische Topologie

```
Internet
    │ (PPPoE)
FritzBox 7530 AX  ──── Wibutler Pro 2nd Gen
    │
2× Switch 8-Port (unmanaged)
    ├── UGREEN DXP4800
    ├── Synology DS218J
    ├── LAN-Dosen (alle Räume)
    ├── Buderus Lüftungsanlage
    └── Repeater Garage → Eufy E340
```

Der Wibutler ist direkt an der FritzBox, nicht über die Switches – bewusste Trennung, da er eine eigene Funktion als Smart-Home-Bridge hat und kein normaler LAN-Client ist.

---

## Server-Schicht

### UGREEN DXP4800 (Hauptsystem)

Intel N100 (4 Kerne, effizient), 8 GB RAM. Ausreichend für alle laufenden Dienste bei geringem Stromverbrauch. Als NAS-Betriebssystem läuft **UGOS**.

#### Storage-Layout

| Volume | Medium | RAID | Größe | Verwendung |
|---|---|---|---|---|
| volume1 | HDD | RAID5 | 10,8 TB | Nutzdaten (Medien, Dokumente, Fotos) |
| volume2 | SSD | keins | 256 GB | Docker-Laufzeitdaten |

RAID5 auf volume1 schützt gegen den Ausfall einer einzelnen HDD. Die SSD (volume2) ist kein RAID – sie enthält Container-Konfigurationen und Laufzeitdaten, die bei Ausfall aus Portainer/UGOS neu aufgebaut werden können. Kritische Applikationsdaten (z.B. Paperless-Dokumentenarchiv) liegen auf volume1.

#### Container-Verwaltung: zwei parallele Wege

Auf dem UGREEN laufen Container auf zwei Arten:

**UGOS Docker** (direkt, ohne Portainer):
- Portainer selbst
- Paperless-NGX Stack (wurde vor Einführung von Portainer aufgesetzt)
- UGOS Foto App (systemintegriert)

**Portainer** (für alle neueren Dienste):
- Home Assistant, matter-server, Jellyfin, AdGuard Home
- Wyoming (Whisper + Piper, Testbetrieb)
- eufy-security-ws, go2rtc

Portainer bietet Stack-Management via `docker-compose`-Dateien, einfacheres Update-Management und eine bessere Übersicht. Paperless-NGX wurde bewusst nicht migriert, da der bestehende UGOS-Stack stabil läuft.

### Mac Mini M4 (KI-Server)

Apple M4, 24 GB Unified Memory, 24/7 Headless-Betrieb. Das Unified Memory teilen sich CPU und GPU – effizient für LLM-Inferenz, da Modellgewichte nicht zwischen CPU- und GPU-RAM hin- und herkopiert werden müssen.

**Rolle:** Dedizierter Ollama-Inferenz-Server. Alle KI-Anfragen im Heimnetz laufen hier auf.

```
Open Web UI (NAS, :3001)  →  Ollama :11434 (Mac Mini M4)
VS Code / Continue        →  Ollama :11434 (Mac Mini M4)
Paperless-AI (geplant)    →  Ollama :11434 (Mac Mini M4)
```

**Modelle und RAM-Planung (24 GB):**

| Modell | Größe (Q4) | Use-Case |
|---|---|---|
| qwen3:14b | ~8 GB | Familien-Chat, Dokument-RAG |
| qwen3:8b | ~5 GB | Schnelle Fragen, Paperless-AI |
| qwen2.5-coder:14b | ~8 GB | Coding (VS Code / Continue) |
| nomic-embed-text | ~0,3 GB | Embeddings (RAG) |

Ollama entlädt Modelle nach 5 Minuten Inaktivität (`OLLAMA_KEEP_ALIVE=5m`). Zwei große 14B-Modelle werden nie gleichzeitig geladen.

Details: Siehe [Hardware/mac-mini-m4.md](../Hardware/mac-mini-m4.md)

---

## Smarthome-Schicht

### Wibutler Pro 2nd Gen → Matter → Home Assistant

Der Wibutler ist die physische Smarthome-Zentrale: Er verbindet alle Lichter, Schalter und Sensoren (Temperatur, Feuchte) im Haus über sein proprietäres Protokoll. Nach außen präsentiert er sich als **Matter Bridge**.

Home Assistant kommuniziert ausschließlich über das **Matter-Protokoll** mit dem Wibutler – vermittelt über den `matter-server` Container. Diese Entkopplung hat einen wichtigen Vorteil: Sollte der Wibutler eines Tages ausgetauscht werden, müsste nur die Matter-Bridge-Seite angepasst werden, nicht die gesamte HA-Konfiguration.

```
Home Assistant → matter-server → Wibutler (Matter Bridge) → Geräte
```

### Mitsubishi Electric Klimaanlage (MELCloud Home)

Home Assistant steuert das Multi-Split-System (Außengerät MXZ-2F53VF4, Innengeräte in Wohnzimmer und Büro) über die **MELCloud Home HACS-Integration** von Andrew-Blake. Die Kommunikation läuft über die Mitsubishi MELCloud Cloud-API – als einzige Smarthome-Integration im Setup ist dies **nicht lokal**.

```
Home Assistant (MELCloud Home HACS)
    └── MELCloud Cloud-API (Internet)
            └── Mitsubishi Electric MXZ-2F53VF4
                    ├── MSZ-AY20VGKP (Wohnzimmer)
                    └── MSZ-AY35VGKP (Büro)
```

> **Bewusster Kompromiss:** Eine lokale Steuerung wäre mit Mitsubishi CN105-Adapter möglich, wurde aber zugunsten der einfacheren Cloud-Integration nicht umgesetzt.

---

### Huawei Wallbox (OCPP)

Die Wallbox kommuniziert direkt mit Home Assistant über das **OCPP-Protokoll** (Open Charge Point Protocol) via HACS-Integration. Kein Zwischensystem, kein Cloud-Account des Herstellers notwendig.

### Hichi IR-Lesekopf – Energiezähler

Zwei Hichi WiFi IR-Leseköpfe (Tasmota, ESP32C3) lesen die Stromzähler per Infrarot aus und senden die Daten via MQTT an Mosquitto. Home Assistant empfängt die Werte über native MQTT-Sensoren.

```
Home Assistant (MQTT-Sensoren, configuration.yaml)
    └── mosquitto (MQTT-Broker)
            ├── hichi_1646 (192.168.188.145) → Zähler 1646 Allgemein/Hauptstrom
            └── hichi_1634 (192.168.188.146) → Zähler 1634 Heizung
```

Der Vorteil gegenüber der SMGW HAN-Schnittstelle: Echtzeit-Updates (statt 15-Minuten-Polling), einfache Tasmota-Konfiguration, keine IPv6-Problematik.

> **Phasendaten (PIN):** Spannung, Strom und Leistung auf L1–L3 sind erst nach PIN-Aktivierung am Zähler verfügbar (PIN kommt per Post von NetzeBW).

Details: Siehe [Hardware/hichi.md](../Hardware/hichi.md)

---

### Smart Meter Gateway (EMH / NetzeBW HAN)

> ⚠️ **Nicht mehr aktiv.** Das SMGW ist physisch angeschlossen, wird aber nicht mehr genutzt (HAN-Schnittstelle nicht zuverlässig). Energiedaten kommen von den Hichi IR-Leseköpfen.

Details: Siehe [Hardware/smartmeter.md](../Hardware/smartmeter.md)

---

### Eufy E340 Kamera (Garage)

Da die Eufy-Cloud-Integration datenschutztechnisch ungünstig ist, läuft die Einbindung vollständig lokal:

```
Eufy E340 → eufy-security-ws → go2rtc → Home Assistant
```

`eufy-security-ws` stellt eine lokale WebSocket-Verbindung zur Kamera her. `go2rtc` transkodiert den Stream in ein Format, das Home Assistant als Kamera-Entität einbinden kann. Der Garage-Repeater (am Switch) stellt dabei die WLAN-Verbindung zur Kamera sicher.

---

## Medien & Daten

**Jellyfin** verwaltet die Medienbibliothek (Filme, Serien, Musik) auf volume1. Zugriff ausschließlich im Heimnetz oder via WireGuard.

**Paperless-NGX** ist das zentrale Dokumentenarchiv. Dokumente werden über drei Wege eingespielt: Paperless-App, Smartphone-Scan oder Epson WF-3825. Der Epson-Scanner überträgt Scans manuell in den consume-Ordner auf volume2.

**UGOS Foto App** dient als familienweites Foto- und Video-Backup für alle Mobilgeräte. Die Synchronisation läuft im Heimnetz automatisch und bei Bedarf auch remote über WireGuard.

---

## Backup

Die **Synology DS218J** ist das einzige Backup-Ziel. Sie läuft einmal wöchentlich (Montag, ~1 Stunde) und wird per Rsync aus UGOS heraus bespielt. Nach dem Backup schaltet sie sich wieder ab.

**Bekannte Schwächen dieser Strategie:**

- Kein Cloud-Backup: Bei gleichzeitigem Ausfall beider NAS (z.B. Hausbrand, Diebstahl) gibt es keinen weiteren Restore-Pfad.
- Wöchentliches Backup: Bis zu 7 Tage Datenverlust möglich.
- Kein Test-Restore bisher dokumentiert.

Empfehlung für die Zukunft: Kritische Daten (Paperless-Archiv) zusätzlich verschlüsselt in eine Cloud sichern (z.B. Backblaze B2 via Rclone).

---

## Dienste im Testbetrieb / inaktiv

| Dienst | Status | Hinweis |
|---|---|---|
| Wyoming (Whisper + Piper) | Test | Spracherkennung und TTS für HA – noch keine aktive Integration |
| Ollama | Aktiv (Mac Mini M4) | Läuft auf 192.168.188.151:11434 – qwen3:14b, qwen3:8b, qwen2.5-coder:14b, nomic-embed-text |
| Open Web UI | Aktiv (NAS :3001) | Familien-Chat, Web-Suche via SearXNG, Dokument-RAG |
| SearXNG | Aktiv (NAS, intern) | Anonyme Websuche für Open Web UI – kein direkter Zugriff von außen |
