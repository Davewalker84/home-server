# Home Assistant

Zentrale Smarthome-Plattform. Aggregiert alle Geräte, Sensoren und Integrationen.

---

## Grunddaten

| | |
|---|---|
| URL | http://192.168.188.130:8123 |
| Betrieb | Portainer Stack `homeassistant` |
| Host | UGREEN DXP4800 |

---

## Abhängige Container

Home Assistant ist auf folgende Container angewiesen, die separat in Portainer laufen:

| Container / Stack | Funktion | Typ |
|---|---|---|
| `mosquitto` | MQTT-Broker (HCPBridge, IoT-Geräte) | Portainer Stack |
| `matter-server` | Matter-Protokoll-Bridge (Wibutler) | Portainer Stack |
| `eufy-security-ws` | Lokale Eufy-Kamera-Anbindung | Portainer Container |
| `go2rtc` | Kamera-Stream-Relay | Portainer Container |

Fällt einer dieser Container aus, verliert HA die jeweilige Integration – der Rest läuft unabhängig weiter.

---

## Integrationen

### Matter (Wibutler Pro 2nd Gen)

**Typ:** Matter over LAN  
**Vermittlung:** `matter-server` Container

```
Home Assistant
    └── matter-server (Container)
            └── Matter-Protokoll (LAN)
                    └── Wibutler Pro 2nd Gen (Matter Bridge)
                            ├── Lichter (via Eltako-Relais)
                            ├── Wandschalter (via Eltako-Relais)
                            └── Sensoren (Temperatur, Feuchte)
```

Der `matter-server` läuft als eigenständiger Portainer Stack und stellt die Matter-Protokoll-Implementierung bereit. Home Assistant verbindet sich intern damit.

> **Hinweis:** Die Heizungssteuerung des Wibutlers ist **nicht via Matter verfügbar** und daher nicht in Home Assistant eingebunden.

---

### OCPP – Huawei Smart Charger (22 kW)

**Typ:** HACS-Integration  
**Protokoll:** OCPP (Open Charge Point Protocol)  
**Fahrzeug:** VW ID.7

```
Home Assistant (OCPP HACS-Integration)
    └── OCPP-Protokoll (LAN)
            └── Huawei Smart Charger 22 kW
                    └── VW ID.7
```

Die Wallbox ist vollständig lokal eingebunden – kein Hersteller-Cloud-Account erforderlich. Über HA sind Ladevorgänge steuer- und protokollierbar.

> **Bekannte Schwäche:** Die OCPP-Verbindung kann sich gelegentlich trennen. Workaround: HACS-Integration oder HA-Container neu starten.

---

### Eufy E340 Kamera (Garage)

**Typ:** Lokale Integration (ohne Eufy-Cloud)  
**Pipeline:** eufy-security-ws → go2rtc → Home Assistant

```
Eufy E340
    └── WLAN → Garage-Repeater → LAN
                    └── eufy-security-ws (Container, lokale API)
                            └── go2rtc (Stream-Transkodierung)
                                    └── Home Assistant (Kamera-Entität, Live-Stream)
```

`eufy-security-ws` stellt die lokale Verbindung zur Kamera her und umgeht die Eufy-Cloud. `go2rtc` transkodiert den RTSP-Stream in ein HA-kompatibles Format.

> **Bekannte Schwäche:** Eufy-Firmware-Updates können die lokale API von `eufy-security-ws` brechen. Nach jedem Kamera-Firmware-Update den Container-Status und den Live-Stream in HA prüfen.

---

### MQTT – Hörmann Garagentor & IoT-Geräte

**Typ:** Portainer Stack `mosquitto`  
**Broker:** Eclipse Mosquitto  
**Port:** 1883 (MQTT), 9001 (WebSocket)

```
Home Assistant (MQTT-Integration)
    └── mosquitto (MQTT-Broker, Portainer Stack)
            └── HCPBridge (Hörmann ProMatic 4)
            └── künftige MQTT-Geräte (Sensoren, ESP32, etc.)
```

Mosquitto verwaltet alle MQTT-Verbindungen. Die HCPBridge publiziert Tor-Zustände (offen/geschlossen, Position) und empfängt Befehle (öffnen/schließen/stopp). Home Assistant abonniert diese Meldungen via MQTT Auto-Discovery.

> **Hinweis:** Mosquitto ist **notwendig** für HCPBridge. Andere HA-Integrationen (Matter, OCPP, Eufy) sind unabhängig davon.

Details: Siehe [mosquitto.md](mosquitto.md) und [Hardware/garagentor.md](../Hardware/garagentor.md).

---

### Wyoming – Spracherkennung / TTS

**Typ:** Portainer Stack `wyoming`  
**Status:** Testbetrieb – noch nicht aktiv in HA integriert

| Container | Funktion |
|---|---|
| `wyoming-faster-whisper` | Lokale Spracherkennung (Speech-to-Text) |
| `wyoming-piper` | Lokale Sprachausgabe (Text-to-Speech) |

Wyoming wird als lokale Alternative zu Cloud-basierten Sprachdiensten getestet. Keine aktive HA-Integration vorhanden.

---

## HACS (Home Assistant Community Store)

HACS ist installiert und wird für die OCPP-Wallbox-Integration genutzt.

| Integration | Zweck |
|---|---|
| OCPP | Huawei Smart Charger Anbindung |

---

## Daten & Storage

Home Assistant speichert seine Konfiguration und Datenbank im Portainer-Stack-Volume auf **volume2** (SSD) des UGREEN. Die Daten werden über den wöchentlichen Rsync auf die Synology gesichert.

---

## Neustart & Wartung

**Container-Neustart über Portainer:**
1. Portainer öffnen → https://192.168.188.130:9444
2. Stacks → `homeassistant` → Container auswählen → Restart

**Reihenfolge bei manuellem Neustart aller abhängigen Services:**
1. `matter-server` starten
2. `eufy-security-ws` starten
3. `go2rtc` starten
4. `homeassistant` starten

> HA verbindet sich beim Start mit den abhängigen Containern. Startet HA bevor `matter-server` bereit ist, kann die Matter-Integration fehlschlagen und muss in HA manuell neu geladen werden (Einstellungen → Geräte & Dienste → Matter → Neu laden).

---

## Bekannte Schwächen

- **Kein externer Zugriff ohne WireGuard:** HA ist ausschließlich im Heimnetz erreichbar. Remote-Zugriff nur über WireGuard VPN (FritzBox).
- **Heizung nicht integriert ⚠️:** Die Wibutler-Heizungssteuerung ist nicht via Matter verfügbar und damit blind für HA.
- **Kein HA-Backup außerhalb des NAS:** Fällt der UGREEN aus, ist HA nicht erreichbar. Kein Cloud-Backup der HA-Konfiguration.
