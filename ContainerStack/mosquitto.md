# Mosquitto – MQTT Broker

Zentraler Message-Broker für MQTT-basierte Geräteintegration. Alle MQTT-Clients im Heimnetz (HCPBridge, ESP32, Sensoren) kommunizieren über Mosquitto mit Home Assistant.

---

## Grunddaten

| | |
|---|---|
| **Image** | `eclipse-mosquitto:latest` |
| **Container** | `mosquitto` |
| **Betrieb** | Portainer Stack |
| **Ports** | 1883 (MQTT), 9001 (WebSocket) |
| **Host** | UGREEN DXP4800 |

---

## Abhängigkeiten in Home Assistant

Mosquitto ist optional, aber **notwendig für:**

- HCPBridge Garagentor (Hörmann ProMatic 4)
- Hichi IR-Lesekopf 1646 (IP 192.168.188.145) → Zähler Allgemein/Hauptstrom
- Hichi IR-Lesekopf 1634 (IP 192.168.188.146) → Zähler Heizung

Ohne Mosquitto funktionieren HCPBridge und Hichi-Energiemessung nicht. Alle anderen HA-Integrationen (Matter, OCPP, Eufy, Wyoming) laufen unabhängig davon.

---

## Stack-Konfiguration

### Docker-Compose YAML

```yaml
version: "3.8"

services:
  mosquitto:
    image: eclipse-mosquitto:latest
    container_name: mosquitto
    restart: unless-stopped
    ports:
      - "1883:1883"
      - "9001:9001"
    volumes:
      - mosquitto_config:/mosquitto/config
      - mosquitto_data:/mosquitto/data
      - mosquitto_log:/mosquitto/log
    environment:
      - TZ=Europe/Berlin

volumes:
  mosquitto_config:
  mosquitto_data:
  mosquitto_log:
```

### Konfigurationsdatei

`/mosquitto/config/mosquitto.conf`:

```
listener 1883
allow_anonymous true

listener 9883
protocol http_api
http_dir /usr/share/mosquitto/dashboard

persistence true
persistence_location /mosquitto/data/
log_dest file /mosquitto/log/mosquitto.log
log_dest stdout
```

> **Hinweis:** Anonymer Zugriff ist aktiviert (`allow_anonymous true`), da die Hichi IR-Leseköpfe (Tasmota) keine MQTT-Credentials unterstützen. Mosquitto ist ausschließlich im lokalen Heimnetz erreichbar – Port 1883 ist nicht nach außen exponiert. Port 9883 stellt ein internes HTTP-Dashboard bereit.

---

## Setup nach dem Deploy

### 1. Stack in Portainer deployen

- Portainer → Stacks → „Add Stack"
- YAML einfügen (siehe oben)
- Deploy

### 2. Konfigurationsdatei prüfen

Nach dem ersten Deploy die `mosquitto.conf` im Volume prüfen und ggf. anpassen (siehe Konfigurationsdatei oben). Container danach neu starten:

```bash
docker restart mosquitto
```

---

## Integrationen

### Home Assistant

HA muss Mosquitto als MQTT-Integration kennen, damit MQTT-Geräte Auto-Discovery nutzen können.

**Setup in HA:**
- Einstellungen → Geräte & Dienste
- Integration hinzufügen → MQTT
- Eintragen:
  - **Broker:** 192.168.188.130
  - **Port:** 1883
  - **Username/Password:** leer lassen (anonym)

Nach erfolgreicher Verbindung zeigt HA „MQTT" unter Geräte & Dienste.

### HCPBridge (Garagentor)

HCPBridge sendet Tor-Zustände per MQTT an Mosquitto. HA empfängt diese Meldungen und stellt Entities bereit.

**Konfiguration in HCPBridge Web-UI (192.168.4.1):**

| Feld | Wert |
|---|---|
| MQTT Server | 192.168.188.130 |
| MQTT Port | 1883 |
| MQTT User | leer |
| MQTT Password | leer |

### Hichi IR-Lesekopf (Energiezähler)

Die Hichi-Geräte verbinden sich anonym mit Mosquitto und senden Zählerdaten per Tasmota-MQTT.

| Gerät | IP | MQTT Topic |
|---|---|---|
| Hichi 1646 (Haushalt) | 192.168.188.145 | `tele/hichi_1646/SENSOR` |
| Hichi 1634 (Heizung) | 192.168.188.146 | `tele/hichi_1634/SENSOR` |

Details: Siehe [Hardware/hichi.md](../Hardware/hichi.md)

---

## Troubleshooting

### Container stößt auf Permissions-Fehler

**Symptom:** Mosquitto-Logs zeigen „Permission denied" auf `/mosquitto/data/`.

**Lösung:** Volume-Berechtigungen in Portainer prüfen oder Docker Restart:

```bash
docker restart mosquitto
```

Falls der Fehler bleibt:

```bash
docker exec mosquitto chown -R mosquitto:mosquitto /mosquitto/data /mosquitto/log
```

### MQTT-Client kann sich nicht verbinden

**Symptom:** HCPBridge/Gerät zeigt „MQTT Server not reachable" oder ähnlich.

**Prüfen:**
1. Mosquitto läuft: `docker ps | grep mosquitto`
2. Port offen: `netstat -tlnp | grep 1883` (auf dem Host)
3. Firewall: FritzBox → Freigaben prüfen (sollte keine Filterung für 1883 exist)
4. Mosquitto-Logs: Portainer → mosquitto → Logs
5. MQTT-Credentials: Benutzer `mqttuser` existiert und Passwort stimmt

### Mosquitto neu booten (nach Config-Änderungen)

```bash
docker restart mosquitto
```

---

## Performance & Limits

Mosquitto ist sehr leicht und skaliert problemlos bis zu Hunderten gleichzeitiger Clients. Für ein privates Heimnetzwerk ist die Default-Konfiguration völlig ausreichend.

### Persistenz

- Alle Nachrichten werden auf `volume1` (mosquitto_data) gespeichert
- Beim Container-Restart werden alte Sessions wiederhergestellt
- Kritisch für zuverlässiges IoT-Messaging

### Speicherverbrauch

Typisch **~20–50 MB RAM** bei moderater Aktivität (10–50 aktive Clients). Bei 500+ gleichzeitigen Subscribers könnte der Speicher auf **100+ MB** steigen, aber für dieses Setup irrelevant.

---

## Sicherheit & Best Practice

### Authentifizierung

- ⚠️ `allow_anonymous true` — alle Clients im Heimnetz dürfen sich ohne Credentials verbinden
- Begründung: Hichi IR-Leseköpfe (Tasmota) unterstützen MQTT-Credentials, aber die Konfiguration wurde für maximale Kompatibilität auf anonym gestellt
- Mosquitto ist **ausschließlich lokal** erreichbar — Port 1883 nicht nach außen exponiert

### Netzwerk-Scoping

- Mosquitto ist **nur lokal im Heimnetz erreichbar** (Port 1883 nicht nach außen exponiert)
- Remote-Zugriff nur via WireGuard-VPN auf HA möglich (kein direkter MQTT-Zugriff von außen)

### Weitere MQTT-Benutzer

Falls künftig weitere Geräte mit unterschiedlichen Berechtigungen kommen:

```bash
docker exec -it mosquitto sh
mosquitto_passwd /mosquitto/config/passwd <username>
exit
docker restart mosquitto
```

Dann User mit eigenem Passwort anlegen. **Empfehlung:** Ein Benutzer pro Gerätegruppe (z.B. `hcpbridge`, `sensoren`, `gadgets`).

---

## Links

- **Mosquitto Doku:** https://mosquitto.org/
- **MQTT Spec:** https://mqtt.org/
- **Home Assistant MQTT Integration:** https://www.home-assistant.io/integrations/mqtt/
