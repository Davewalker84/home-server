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

### Hichi IR-Lesekopf – Energiezähler (MQTT)

**Typ:** MQTT-Integration (native HA, kein HACS)  
**Protokoll:** MQTT via Mosquitto, anonym  
**Geräte:** 2× Hichi WiFi IR-Lesekopf V2 (Tasmota 14.6.0.2, ESP32C3)

```
Home Assistant (MQTT-Integration)
    └── mosquitto (MQTT-Broker)
            ├── hichi_1646 (IP 192.168.188.145) → Zähler 1646 Allgemein/Hauptstrom
            └── hichi_1634 (IP 192.168.188.146) → Zähler 1634 Heizung
```

Die Konfiguration liegt in `configuration.yaml` unter dem `mqtt: sensor:` Block.

#### Sensoren

| Entität | Beschreibung | Einheit |
|---|---|---|
| `sensor.hichi_1646_verbrauch_gesamt` | Zählerstand Netzbezug (Haushalt) | kWh |
| `sensor.hichi_1646_einspeisung_gesamt` | Zählerstand Einspeisung | kWh |
| `sensor.hichi_1646_wirkleistung` | Aktuelle Wirkleistung (Haushalt) | W |
| `sensor.hichi_1646_spannung_l1/l2/l3` | Spannung pro Phase | V |
| `sensor.hichi_1646_strom_l1/l2/l3` | Strom pro Phase | A |
| `sensor.hichi_1646_frequenz` | Netzfrequenz | Hz |
| `sensor.hichi_1634_verbrauch_gesamt` | Zählerstand Netzbezug (Heizung) | kWh |
| `sensor.hichi_1634_wirkleistung` | Aktuelle Wirkleistung (Heizung) | W |
| *(analog L1–L3, Frequenz für 1634)* | | |

> **Hinweis:** Phasendaten (Spannung, Strom, Leistung, Frequenz) zeigen 0, bis der NetzeBW-PIN am Zähler aktiviert ist. Bezug (`E_in`) und Einspeisung (`E_out`) funktionieren ohne PIN.

> **Wallbox:** Die Huawei SCharger-22KT hängt physisch am Zähler 1646. Ihr Verbrauch ist bereits in `sensor.hichi_1646_verbrauch_gesamt` enthalten.

Details: Siehe [Hardware/hichi.md](../Hardware/hichi.md)

---

### Smart Meter Gateway (EMH / NetzeBW HAN)

> ⚠️ **Nicht mehr im Dashboard.** Das SMGW ist weiterhin physisch angeschlossen und konfiguriert, wird aber nicht mehr aktiv genutzt. Die Energiedaten kommen jetzt von den Hichi IR-Leseköpfen, da die HAN-Schnittstelle nicht zuverlässig funktioniert.

**Typ:** Native REST-Integration (kein HACS)  
**Protokoll:** HTTPS mit HTTP Digest Auth  
**Endpunkt:** `https://[2003:de:9f37:1c00:215:3bff:fee4:1f5c]/json/realtimedata`

Details: Siehe [Hardware/smartmeter.md](../Hardware/smartmeter.md)

---

### MELCloud Home – Mitsubishi Electric Klimaanlage

**Typ:** HACS Custom Integration (Andrew-Blake / melcloudhome)  
**Protokoll:** MELCloud Cloud-API (Internet)  
**System:** Multi-Split · 1 Außengerät (MXZ-2F53VF4) · 2 Innengeräte

```
Home Assistant (MELCloud Home HACS)
    └── MELCloud Cloud-API (Internet)
            └── MXZ-2F53VF4 (Außengerät)
                    ├── MSZ-AY20VGKP → climate.melcloudhome_1b7f_0270_climate (Wohnzimmer)
                    └── MSZ-AY35VGKP → climate.melcloudhome_d64c_5427_climate (Büro)
```

#### Nachlüften-Automatisierung

Nach ≥ 30 Minuten Betrieb in heat/cool/dry/auto schaltet HA beim Ausschalten automatisch in `fan_only` (10 Minuten), damit Kondenswasser aus dem Innengerät trocknet. Steuerung über:

| Helfer | Funktion |
|---|---|
| `input_boolean.nachluften_wohnzimmer_aktiv` | Sperrt AUS-Button während Nachlüften aktiv |
| `input_boolean.nachluften_buro_aktiv` | Sperrt AUS-Button während Nachlüften aktiv |
| `timer.nachluften_wohnzimmer` | 10-Minuten-Timer, danach automatisch AUS |
| `timer.nachluften_buro` | 10-Minuten-Timer, danach automatisch AUS |

Push-Benachrichtigung an beide Bewohner beim Start des Nachlüftens.

> **Bekannte Schwäche:** Die Steuerung ist cloud-abhängig. Bei Ausfall von Internet oder MELCloud ist keine HA-Steuerung möglich. Das Gerät läuft weiter und ist per Fernbedienung bedienbar.

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
| MELCloud Home | Mitsubishi Electric Klimaanlage (Andrew-Blake) |

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
