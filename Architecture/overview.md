# Architektur-Übersicht

Dieses Dokument erklärt das *Warum* hinter dem Setup – die Entscheidungslogik, Abhängigkeiten und Kompromisse. Die reine Komponentenliste findet sich im [README](../README.md).

---

## Leitprinzipien

Das Setup folgt drei Grundsätzen:

**Lokal first.** Alle Daten, Dienste und Automatisierungen laufen im Heimnetz – keine Abhängigkeit von Cloud-Diensten für den Kernbetrieb. Home Assistant, Paperless-NGX und Jellyfin funktionieren auch ohne Internetzugang.

**Ein NAS, ein Betriebszentrum.** Der UGREEN DXP4800 ist das einzige aktive Server-System. Alle Docker-Container laufen dort. Das reduziert Komplexität und Stromverbrauch im Vergleich zu mehreren spezialisierten Geräten.

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

### Smart Meter Gateway (EMH / NetzeBW HAN)

Das SMGW von NetzeBW stellt über seinen **HAN-Port** (Home Area Network) eine lokale HTTPS-API bereit. Home Assistant liest die Daten direkt per REST-Sensor mit HTTP Digest Auth – vollständig lokal, ohne Cloud, ohne TRuDI.

```
Home Assistant (REST smgw_sensor.yaml)
    └── HTTPS Digest Auth → EMH SMGW (HAN-Port, IPv6, Switch)
```

Die IPv6-Adresse des Gateways wird direkt verwendet, da Docker-Container den Hostnamen `eemh0015438871` nicht über das lokale DNS auflösen können. Das Poll-Intervall ist auf 15 Minuten gesetzt (NetzeBW-Empfehlung).

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
| Ollama | Inaktiv | Lokales LLM – kein Modell im produktiven Einsatz |
