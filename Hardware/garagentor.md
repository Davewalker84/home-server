# Hörmann ProMatic 4 – Garagentor mit HCPBridge

Elektrisches Sektionaltor mit integrierter Steuerung (ProMatic 4). Nachgerüstet mit RS485-Bridge für lokale MQTT-Anbindung an Home Assistant.

---

## Hardware

| | |
|---|---|
| **Tor** | Hörmann ProMatic 4 (Sektionaltor) |
| **Controller** | HCPBridge RS485-Bridge (Tynet, ESP32-S3) |
| **Bus-Protokoll** | Hörmann HCP2 (RJ12-Verbindung) |
| **Stromversorgung** | 24V über RJ12-Bus (kein USB-C nötig) |
| **Netzwerk** | WLAN (Fritz Repeater Garage) |
| **Integration** | MQTT → Home Assistant |

---

## Stromversorgung

Die HCPBridge wird **direkt vom Garagentorantrieb über den RJ12-Bus mit 24V versorgt**. Ein interner Step-Down-Regler wandelt auf 3,3V um.

| Szenario | USB-C | RJ12 | Ergebnis |
|---|---|---|---|
| Erstkonfiguration | ✅ angesteckt | ❌ nicht angesteckt | Web-UI auf 192.168.4.1 (Hotspot-Modus) |
| Betrieb im Tor | ❌ NICHT angesteckt | ✅ angesteckt | Strom vom Bus, Kabel-Decke bleibt sauber |

**Wichtig:** USB-C und RJ12 dürfen nie gleichzeitig angeschlossen sein (Anleitung des Herstellers).

---

## Konfiguration

### 1. Erstkonfiguration (USB-C, zu Hause)

1. HCPBridge mit USB-C an den Rechner anschließen
2. WLAN „HCPBRIDGE" verbinden (Standard-Passwort: `tynet.eu`)
3. Browser → http://192.168.4.1 öffnen
4. Basic Configuration ausfüllen:
   - **WIFI SSID:** Name deines Heimnetzwerks (z.B. FritzBox-David)
   - **WIFI Password:** WLAN-Passwort
   - **WIFI AP Password:** Passwort für den Hotspot (optional ändern, Standard `tynet.eu`)
   - **MQTT Server:** IP deines HA-Servers (z.B. 192.168.188.130)
   - **MQTT Port:** 1883
   - **MQTT User:** mqttuser
   - **MQTT Password:** Dein Mosquitto-Passwort
   - **Web UI Password:** Passwort für Zugriff auf die Web-UI (optional)
5. „Save & Restart" klicken → die Bridge verbindet sich mit deinem Heimnetz

### 2. Montage im Tor

1. USB-C abstecken ✅
2. RJ12-Kabel vom PCB in den **BUS-Port** des ProMatic 4 stecken
3. Die Platine sitzt **direkt unter der Motorhaube** des Antriebs

### 3. Bus-Scan (ProMatic 4)

1. **DIP-Schalter unten am Antrieb** einmal kurz umlegen (rein, dann wieder raus)
   - Der DIP-Schalter ist im Inneren der Motorhaube sichtbar (blauer Pfeil in der Tynet-Anleitung)
2. **Erfolg erkannt an:**
   - 3V3-LED auf der Platine leuchtet
   - RS485-Modul blinkt schnell

Nach erfolgreichen Bus-Scan erscheint das Garagentor automatisch in Home Assistant via MQTT Auto-Discovery als `cover.garagentor`.

---

## Home Assistant Integration

Die HCPBridge emuliert den Standard-Hörmann UAP1-HCP-Adapter und sendet alle Tor-Zustände per MQTT.

### MQTT-Entities

| Entity | Type | Beschreibung |
|---|---|---|
| `cover.garagentor` | Cover (open/close/stop) | Tor-Position und Steuerung |
| `binary_sensor.garagentor_status` | Binary Sensor | Tor offen/geschlossen |
| `sensor.garagentor_position` | Sensor (%) | Aktuelle Tor-Position |
| `light.garagentor_light` | Light (optional) | Beleuchtung (wenn eingebunden) |

### Web-Zugriff nach der Montage

Nach dem Bus-Scan die HCPBridge über dein Heimnetz erreichbar unter:

```
http://HCPBRIDGE.local
```

oder über die IP-Adresse (nachschlagen in der FritzBox unter Heimnetz → Netzwerk).

**Empfohlung:** Statische IP in der FritzBox vergeben:
- FritzBox → Heimnetz → Netzwerk → Gerät anklicken → „Diesem Netzwerkgerät immer die gleiche IPv4-Adresse zuweisen"

---

## Troubleshooting

### Error 04 beim Öffnen/Schließen

**Ursache:** Schwaches WLAN-Signal zwischen HCPBridge und Repeater/FritzBox.

**Lösungen:**
- Sicherung Garage raus und wieder rein damit MPC Bridge wieder sendet, vorher checken ob erreichbar im Heimnetz
- Fritz Repeater näher ans Tor rücken oder zusätzlichen Repeater einbauen
- Tynet-Firmware zu ESPHome-Firmware wechseln (bessere WLAN-Stabilität)
- MQTT-Broker-Netzwerklatenz prüfen (Mosquitto-Container-Logs)

### Web-UI nicht erreichbar über 192.168.4.1

**Ursache:** Zu diesem Zeitpunkt ist die Bridge noch nicht mit deinem Heimnetz verbunden (nur im Hotspot-Modus erreichbar).

**Lösung:** 
- Mit dem WLAN „HCPBRIDGE" verbinden
- Browser → http://192.168.4.1
- WLAN-Daten eintragen und speichern

### Bridge verbindet sich nicht mit MQTT

**Ursache:** Falsche MQTT-Credentials oder Mosquitto läuft nicht.

**Prüfen:**
- Mosquitto-Container läuft: `docker ps | grep mosquitto` in der Shell
- MQTT-Credentials korrekt: User + Passwort in der Web-UI (192.168.4.1)
- Mosquitto-Logs: Portainer → mosquitto-Container → Logs

---

## Sicherheit & Best Practice

### MQTT-Authentifizierung

Die HCPBridge kommuniziert nur mit Mosquitto, nicht direkt mit Home Assistant. **Richtlinien:**

- ✅ Dedizierter MQTT-Benutzer (`mqttuser`) für HCPBridge — nicht den HA-Admin-Account verwenden
- ✅ Starkes MQTT-Passwort setzen (min. 16 Zeichen, Sonderzeichen)
- ✅ Web-UI-Passwort setzen (schützt die 192.168.4.1-Config vor Änderungen)
- ✅ MQTT-Broker läuft lokal im Heimnetz (nicht exponiert nach außen)

### Firmware-Updates

Die HCPBridge erhält regelmäßig Updates für WLAN-Stabilität und neue Features.

- **Update-Weg:** Tynet Web Flasher unter https://tynet.eu/flasher (Arduino- oder ESPHome-Firmware)
- **Vor Update:** Rechne mit ~5 Min. Downtime des Tors
- **Nach Update:** Bus-Scan erneut durchführen (meist nicht nötig, kann aber sicherheitshalber wiederholt werden)

---

## Links

- **Tynet Shop:** https://shop.tynet.eu/rs485-bridge-diy-hoermann-mqtt-adapter-esp32-s3
- **Offizielle Dokumentation (Wiki):** https://github.com/Tysonpower/HCPBridgeMqtt_tynet/wiki
- **Firmware & Flasher:** https://tynet.eu/flasher
- **Support:** support@tynet.eu
