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
- Beliebige künftige MQTT-Geräte (ESP32, Sensoren, Smart-Home-Gadgets)

Ohne Mosquitto funktioniert die HCPBridge nicht. Alle anderen HA-Integrationen (Matter, OCPP, Eufy, Wyoming) laufen unabhängig davon.

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
allow_anonymous false
password_file /mosquitto/config/passwd
persistence true
persistence_location /mosquitto/data/
log_dest file /mosquitto/log/mosquitto.log
log_dest stdout
```

---

## Setup nach dem Deploy

### 1. Stack in Portainer deployen

- Portainer → Stacks → „Add Stack"
- YAML einfügen (siehe oben)
- Deploy

### 2. Passwort setzen (Ersteinrichtung)

Der Standard-Benutzer ist `mqttuser`. Passwort setzen:

```bash
docker exec -it mosquitto sh
```

In der Container-Shell:

```bash
mosquitto_passwd -c /mosquitto/config/passwd mqttuser
```

Passwort zweimal eingeben (min. 16 Zeichen, mit Sonderzeichen), dann:

```bash
exit
docker restart mosquitto
```

> **Hinweis:** Falls `sh` in Portainer nicht funktioniert: Command-Feld auf `/bin/sh` ändern statt `/bin/bash`.

---

## Integrationen

### Home Assistant

HA muss Mosquitto als MQTT-Integration kennen, damit MQTT-Geräte Auto-Discovery nutzen können.

**Setup in HA:**
- Einstellungen → Geräte & Dienste
- Integration hinzufügen → MQTT
- Eintragen:
  - **Broker:** IP des Servers (z.B. 192.168.188.130)
  - **Port:** 1883
  - **Username:** mqttuser
  - **Password:** Das oben gesetzte Passwort

Nach erfolgreicher Verbindung zeigt HA „MQTT" unter Geräte & Dienste.

### HCPBridge (Garagentor)

HCPBridge sendet Tor-Zustände per MQTT an Mosquitto. HA empfängt diese Meldungen und stellt Entities bereit.

**Konfiguration in HCPBridge Web-UI (192.168.4.1):**

| Feld | Wert |
|---|---|
| MQTT Server | IP des HA-Servers (z.B. 192.168.188.130) |
| MQTT Port | 1883 |
| MQTT User | mqttuser |
| MQTT Password | Das gesetzte Passwort |

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

- ✅ `allow_anonymous false` — nur authentifizierte Clients dürfen verbinden
- ✅ Dedizierter `mqttuser` für HCPBridge (nicht Admin-Account)
- ✅ Starkes Passwort setzen (min. 16 Zeichen)

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
