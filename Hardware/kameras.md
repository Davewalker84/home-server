# Kameras

Lokale Kameraeinbindung ohne Cloud-Abhängigkeit.

---

## Übersicht

| Kamera | Modell | Standort | Speicher |
|---|---|---|---|
| Garage | Eufy E340 | Außen, fest montiert | Interne SSD (Kamera) |

---

## Architektur

Die Eufy E340 wird vollständig lokal eingebunden – die Eufy-Cloud wird nicht genutzt. Drei Container bilden die Pipeline von der Kamera bis zu Home Assistant:

```
Eufy E340 (Garage)
    └── WLAN → Garage-Repeater → Switch → LAN
                    │
                    ▼
        eufy-security-ws (Container)
        lokale WebSocket-Verbindung zur Kamera,
        umgeht Eufy-Cloud
                    │
                    ▼
             go2rtc (Container)
        RTSP-Stream-Transkodierung in
        HA-kompatibles Format
                    │
                    ▼
        Home Assistant
        Kamera-Entität mit Live-Stream
```

---

## Container

### eufy-security-ws

| | |
|---|---|
| Betrieb | Portainer Container (kein Stack) |
| Funktion | Lokale Eufy-API – stellt WebSocket-Verbindung zur Kamera her |
| Abhängigkeit | Netzwerkzugang zur Kamera (via Repeater) |

`eufy-security-ws` ist ein Open-Source-Projekt, das die lokale Eufy-API implementiert. Es authentifiziert sich einmalig gegen Eufy und kommuniziert danach lokal mit der Kamera – ohne Cloud-Durchleitung.

> **Wichtig:** Für die initiale Einrichtung und nach bestimmten Updates ist einmalig eine Internetverbindung zur Eufy-Authentifizierung notwendig. Im Dauerbetrieb läuft alles lokal.

### go2rtc

| | |
|---|---|
| Betrieb | Portainer Container (kein Stack) |
| Funktion | Stream-Relay und Transkodierung |
| Abhängigkeit | eufy-security-ws muss laufen |

`go2rtc` empfängt den Stream von `eufy-security-ws` und stellt ihn in einem Format bereit, das Home Assistant als Kamera-Entität einbinden kann (RTSP / WebRTC).

---

## Netzwerkpfad der Kamera

```
Eufy E340
    └── WLAN (2,4 GHz)
            └── Repeater Garage
                    └── Switch (LAN)
                            └── UGREEN NAS (eufy-security-ws)
```

Der Garage-Repeater ist ein kritisches Glied in dieser Kette. Fällt er aus, verliert die Kamera die Netzwerkverbindung – unabhängig vom NAS-Status.

---

## Aufzeichnung & Speicher

| Speicherort | Details |
|---|---|
| Interne Kamera-SSD | Lokale Aufzeichnung direkt auf der Eufy E340 |
| NAS | Keine Aufzeichnung auf dem NAS |

Aufnahmen werden auf der internen SSD der Kamera gespeichert. Es gibt keine Kopie auf dem NAS oder in einer Cloud.

> **Bekannte Schwäche ⚠️:** Bei Diebstahl der Kamera sind alle Aufnahmen verloren. Eine NAS-Aufzeichnung via Home Assistant (Frigate oder HA-native Aufzeichnung) wäre eine mögliche Verbesserung.

---

## Wartung

**Nach einem Eufy-Firmware-Update:**
1. Live-Stream in Home Assistant prüfen
2. Falls kein Stream: `eufy-security-ws` Container in Portainer neu starten
3. Falls weiterhin kein Stream: `go2rtc` Container neu starten
4. Logs von `eufy-security-ws` in Portainer prüfen – API-Änderungen durch Eufy werden dort sichtbar

**Neustart-Reihenfolge:**
1. `eufy-security-ws` starten und warten bis Verbindung zur Kamera besteht
2. `go2rtc` starten
3. Kamera-Entität in Home Assistant prüfen

**Container-Neustart über Portainer:**
1. Portainer öffnen → https://192.168.188.130:9444
2. Container → `eufy-security-ws` oder `go2rtc` → Restart

---

## Bekannte Schwächen

- **Eufy-Firmware-Updates können Integration brechen ⚠️:** Eufy ändert die lokale API gelegentlich mit Firmware-Updates. Nach jedem Kamera-Update Stream prüfen.
- **Repeater als Single Point of Failure:** Kein Netzwerk am Repeater = keine Kamera, kein Stream.
- **Aufnahmen nicht NAS-gesichert:** Interne Kamera-SSD ist der einzige Speicherort. Kein Backup der Aufnahmen.
- **Keine Bewegungserkennung in HA dokumentiert:** Ob Bewegungsereignisse der Eufy E340 in Home Assistant als Trigger verfügbar sind, ist nicht dokumentiert und sollte geprüft werden.
