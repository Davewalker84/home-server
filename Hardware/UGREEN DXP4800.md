# UGREEN DXP4800

Hauptserver des Heimnetzes. Läuft 24/7 und hostet alle aktiven Dienste.

---

## Hardware

| Komponente | Details |
|---|---|
| Modell | UGREEN DXP4800 |
| CPU | Intel N100 (4 Kerne, bis 3,4 GHz, effizient) |
| RAM | 8 GB |
| Laufwerk-Schächte | 4× HDD/SSD (3,5" / 2,5") |
| Betriebssystem | UGOS |
| IP-Adresse | 192.168.188.130 (DHCP-Reservierung in FritzBox) |

---

## Weboberflächen auf diesem Gerät

| Dienst | URL |
|---|---|
| UGOS (NAS-UI) | https://192.168.188.130:9443 |
| Portainer | https://192.168.188.130:9444 |
| Home Assistant | http://192.168.188.130:8123 |
| Paperless-NGX | http://192.168.188.130:8000 |
| AdGuard Home | http://192.168.188.130:8080 |
| Jellyfin | http://192.168.188.130:8096 |

---

## Storage-Layout

### Volumes

| Volume | Typ | RAID | Größe | Zweck |
|---|---|---|---|---|
| volume1 | HDD | RAID5 | 10,8 TB | Alle Nutzdaten (Medien, Dokumente, Fotos) |
| volume2 | SSD | — | 256 GB | Docker-Laufzeitdaten und Container-Konfigurationen |

**RAID5 auf volume1** schützt gegen den physischen Ausfall genau einer HDD. Bei zwei gleichzeitigen Ausfällen gehen alle Daten verloren – das Backup auf der Synology ist daher essenziell.

**volume2 (SSD) ohne RAID** – bewusste Entscheidung: Die SSD enthält Container-Laufzeitdaten, die im Fehlerfall aus den Portainer-Stack-Definitionen wiederhergestellt werden können. Kritische Applikationsdaten liegen immer auf volume1.

### Verzeichnisstruktur (wichtige Pfade)

```
/volume1/                         ← HDD RAID5
├── Filme/                        ← Jellyfin Medienbibliothek (Filme & Serien)
├── Music/                        ← Jellyfin Musikbibliothek
├── paperless-data/               ← Paperless-NGX Dokumentenarchiv
└── [Fotos]                       ← UGOS Foto App Bibliothek

/volume2/                         ← SSD
└── docker/
    └── paperless-ngx/            ← Paperless Stack: Container-Daten & consume-Ordner
```

---

## Container-Management

Auf dem UGREEN laufen Container auf zwei parallelen Wegen. Das ist historisch gewachsen und bleibt bewusst so bestehen, solange beide Stacks stabil laufen.

### UGOS Docker (direkt)

Container, die über die UGOS-eigene Docker-App verwaltet werden. UGOS startet diese automatisch beim Systemstart.

| Container / Stack | Beschreibung |
|---|---|
| Portainer | Container-Management-UI |
| paperless-ngx | Dokumenten-Stack (5 Container, siehe unten) |
| UGOS Foto App | Systemintegriertes Foto-Backup |

### Portainer (Stack-basiert)

Neuere Dienste werden ausschließlich über Portainer als Stacks verwaltet. Stacks sind `docker-compose`-Definitionen und lassen sich direkt in Portainer bearbeiten.

**Stacks:**

| Stack | Enthält |
|---|---|
| `homeassistant` | Home Assistant |
| `matter-server` | matter-server (Matter-Protokoll-Bridge) |
| `ad_guard_home` | AdGuard Home |
| `jellyfin` | Jellyfin |
| `wyoming` | wyoming-faster-whisper, wyoming-piper (Testbetrieb) |

**Einzelne Container (kein Stack):**

| Container | Beschreibung |
|---|---|
| `eufy-security-ws` | Lokale Eufy-Kamera-Anbindung |
| `go2rtc` | Stream-Relay für Home Assistant |

---

## Paperless-NGX Stack (Detail)

Der Paperless-Stack läuft unter UGOS Docker und besteht aus fünf Containern:

| Container | Image | Funktion |
|---|---|---|
| paperless-ngx | `ghcr.io/paperless-ngx/paperless-ngx:2.14.7` | Hauptanwendung |
| paperless-ngx-db | `postgres:17.4` | Datenbank |
| paperless-ngx-redis | `redis:7.4.2` | Task Queue / Cache |
| paperless-ngx-gotenberg | `docker.io/gotenberg/gotenberg:8` | Dokument-Konvertierung |
| paperless-ngx-tika | `docker.io/apache/tika:2.9.2.1` | Textextraktion (OCR-Vorbereitung) |

Externe IP: `172.19.0.x` (internes Docker-Netz), erreichbar von außen über Port `8000`.

---

## Netzwerk-Konfiguration

Die IP `192.168.188.130` ist in der FritzBox per DHCP-Reservierung (MAC-Adresse) fest vergeben. Sie ist damit effektiv statisch, ohne dass eine statische IP im Gerät selbst konfiguriert ist. Vorteil: Bei einem NAS-Reset oder UGOS-Neuinstallation bleibt die IP automatisch erhalten, solange die MAC-Adresse gleich bleibt.

---

## Wichtige Hinweise

- **RAM-Engpass möglich:** 8 GB werden durch alle laufenden Container (HA, Paperless-Stack, Jellyfin, AdGuard, go2rtc, eufy-security-ws, Wyoming) unter Last beansprucht. Wyoming (Whisper) ist ressourcenintensiv – deshalb noch im Testbetrieb ohne aktive Nutzung.
- **Kein USV-Schutz ⚠️:** Ein plötzlicher Stromausfall kann laufende Container, offene Datenbank-Transaktionen (Paperless postgres) und im schlimmsten Fall das RAID beschädigen. Bekannte Schwachstelle – USV nachrüsten.
- **UGOS-Updates:** UGOS-Systemupdates können Docker-Container kurz unterbrechen. Updates daher zu Nebenzeiten einspielen und danach Container-Status in Portainer prüfen.
