# Heimserver-Dokumentation

Zentrale Dokumentation meines Heimnetz- und Server-Setups.  
Ziel: Nachvollziehbarkeit, schnelle Fehlersuche und sicherer Wiederaufbau.

---

## Architektur-Übersicht

```mermaid
flowchart TB

    subgraph EXTERN["Extern (außerhalb Heimnetz)"]
        PHONE["Smartphone / Tablet\nHA App · UGOS App"]
    end

    subgraph HEIMNETZ["Heimnetzwerk · 192.168.188.0/24"]
        FB["FritzBox 7530 AX\nRouter · DHCP · WireGuard-Server\nDSL-Einwahl via PPPoE"]
        AGH["AdGuard Home\nDNS primär"]
        WB["Wibutler Pro 2nd Gen\nMatter Bridge"]

        subgraph SWITCHES["2× Switch 8-Port (unmanaged)"]
            SW_DEV["LAN-Dosen (alle Räume)\nBuderus Lüftungsanlage\nGarage-Repeater\nSynology · UGREEN"]
        end
    end

    subgraph NAS["UGREEN DXP4800 · N100 · 8 GB RAM · 192.168.188.130"]
        subgraph UGOS["UGOS Docker"]
            PT["Portainer :9444"]
            PL["Paperless-NGX :8000\npostgres · redis · gotenberg · tika"]
            PHOTO["UGOS Foto App\nFoto-Backup Familie"]
        end
        subgraph PSTACK["Portainer · Stacks"]
            HA["Home Assistant :8123"]
            MS["matter-server"]
            JF["Jellyfin :8096"]
            WY["Wyoming (Test)\nWhisper · Piper"]
        end
        subgraph PCONT["Portainer · Container"]
            EUFY["eufy-security-ws"]
            GO2["go2rtc"]
        end
        subgraph STORE["Storage"]
            V1["volume1 · HDD RAID5 · 10,8 TB\nFilme · Musik · paperless-data · Fotos"]
            V2["volume2 · SSD · 256 GB\nDocker-Daten"]
        end
    end

    subgraph GERAETE["Geräte & Sensoren"]
        LIGHTS["Lichter · Schalter"]
        SENS["Sensoren\nTemp · Feuchte"]
        WALLBOX["Huawei Wallbox 22 kW\nOCPP"]
        ID7["VW ID.7"]
        CAM["Eufy E340\nGarage"]
        EPSON["Epson WF-3825"]
        SMGW["Smart Meter Gateway\nEMH · NetzeBW HAN\nIPv6 · Digest Auth"]
        KLIMA["Mitsubishi Electric\nMXZ-2F53VF4 (Multi-Split)\nMSZ-AY20VGKP Wohnzimmer\nMSZ-AY35VGKP Büro"]
    end

    subgraph BACKUP["Backup"]
        SYN["Synology DS218J · 192.168.188.135\nRsync · Montag · 1h"]
    end

    PHONE -. "WireGuard VPN\n(HA App / UGOS App)" .-> FB
    FB -->|DNS| AGH
    FB -->|LAN direkt| WB
    FB --> SWITCHES
    SWITCHES --> NAS
    SWITCHES --> SYN

    PT -->|verwaltet| PSTACK
    PT -->|verwaltet| PCONT

    HA -->|Matter Protocol| MS
    MS -->|Matter| WB
    WB --> LIGHTS
    WB --> SENS
    HA -->|OCPP via HACS| WALLBOX
    WALLBOX --- ID7
    CAM -->|RTSP via Repeater| EUFY
    EUFY --> GO2
    GO2 -->|Stream| HA
    EPSON -->|Scan| PL
    SMGW -->|REST Digest / HAN| HA
    HA <-->|MELCloud API (HACS)| KLIMA

    PL <--> V1
    PL <--> V2
    JF --> V1
    PHOTO --> V1
```

---

## Quick Reference – Services

| Service | URL | Läuft auf | Verwaltet via |
|---|---|---|---|
| UGOS (NAS-UI) | https://192.168.188.130:9443 | UGREEN DXP4800 | UGOS |
| Portainer | https://192.168.188.130:9444 | UGREEN DXP4800 | UGOS Docker |
| Home Assistant | http://192.168.188.130:8123 | UGREEN DXP4800 | Portainer Stack |
| Paperless-NGX | http://192.168.188.130:8000 | UGREEN DXP4800 | UGOS Docker |
| AdGuard Home | http://192.168.188.130:8080 | UGREEN DXP4800 | Portainer Stack |
| Jellyfin | http://192.168.188.130:8096 | UGREEN DXP4800 | Portainer Stack |
| Synology DSM | http://192.168.188.135:5000 | Synology DS218J | — |
| FritzBox | http://192.168.188.1 | FritzBox 7530 AX | — |

> Alle Services sind **ausschließlich im Heimnetz** erreichbar.  
> Remote-Zugriff erfolgt ausnahmslos über **WireGuard VPN** (konfiguriert auf der FritzBox).

---

## Quick Reference – Netzwerk

| Gerät | IP | IP-Vergabe |
|---|---|---|
| FritzBox 7530 AX | 192.168.188.1 | statisch (Router) |
| UGREEN DXP4800 | 192.168.188.130 | DHCP-Reservierung (FritzBox) |
| Synology DS218J | 192.168.188.135 | DHCP-Reservierung (FritzBox) |
| Wibutler Pro 2nd Gen | — | DHCP (direkt an FritzBox) |
| Smart Meter Gateway (EMH) | `2003:de:9f37:1c00:215:3bff:fee4:1f5c` | IPv6-only, kein DHCP/IPv4 |

---

## Quick Reference – Storage (UGREEN)

| Volume | Typ | Größe | Inhalt |
|---|---|---|---|
| volume1 | HDD RAID5 | 10,8 TB | Filme, Musik, Fotos, paperless-data |
| volume2 | SSD (kein RAID) | 256 GB | Docker-Containerdaten, Paperless-Stack |

Paperless-NGX Pfade:
- Container & consume: `/volume2/docker/paperless-ngx`
- Dokumentendaten: `/volume1/paperless-data`

---

## Dokumentationsstruktur

```
homeserver-docs/
├── README.md                           ← diese Datei
├── architecture/
│   ├── overview.md                     ← Architektur in Prosa
│   └── system-architecture.mermaid     ← Diagramm-Quelldatei
├── hardware/
│   ├── ugreen-dxp4800.md
│   ├── network.md
│   └── geraete.md
├── services/
│   ├── home-assistant.md
│   ├── paperless-ngx.md
│   ├── adguard-home.md
│   ├── portainer.md
│   ├── jellyfin.md
│   └── kameras.md
├── backup/
│   └── strategie.md
└── guides/
    ├── neuen-service-hinzufuegen.md
    └── wireguard-remote.md
```

---

## Wichtige Hinweise

- **Kein Cloud-Backup** – die Synology DS218J ist das einzige Backup-Ziel. Bei Totalausfall beider NAS gibt es keinen weiteren Restore-Pfad.
- **Wibutler ist Single Point of Failure** für alle Smarthome-Geräte. Fällt er aus, ist die Matter-Bridge unterbrochen und Home Assistant verliert die Kontrolle über Lichter und Sensoren.
- **Wyoming (Whisper + Piper)** läuft als Testumgebung ohne aktive HA-Integration.
- **Ollama** ist installiert aber inaktiv – kein Modell in produktivem Einsatz.
