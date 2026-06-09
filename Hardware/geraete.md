# Geräte & Sensoren

Dokumentation aller physischen Geräte, die ins Heimnetz oder Home Assistant eingebunden sind.

---

## Wibutler Pro 2nd Gen

**Anschluss:** LAN direkt an FritzBox  
**Funktion:** Smarthome-Zentrale und Matter Bridge

Der Wibutler ist die physische Zentrale aller Smarthome-Geräte im Haus. Er verbindet Lichter, Schalter und Sensoren über sein internes Protokoll und präsentiert sie nach außen als **Matter Bridge**.

### Eingebundene Geräte

| Kategorie | Beschreibung |
|---|---|
| Lichter | Alle schaltbaren Leuchten im Haus |
| Schalter | Wandschalter (über Wibutler gesteuert) |
| Sensoren | Temperatur und Feuchte (alle Räume) |

### Integration mit Home Assistant

Home Assistant kommuniziert ausschließlich über das **Matter-Protokoll** mit dem Wibutler – vermittelt über den `matter-server` Container:

```
Home Assistant → matter-server → Wibutler Pro (Matter Bridge) → Geräte
```

Der Wibutler läuft eigenständig und behält seine Konfiguration auch wenn Home Assistant oder der NAS nicht erreichbar sind. Automatisierungen, die nur im Wibutler definiert sind, laufen weiter. HA-Automationen hingegen setzen einen laufenden NAS voraus.

### Bekannte Schwächen

- **Single Point of Failure ⚠️:** Fällt der Wibutler aus, verliert Home Assistant die Kontrolle über alle Lichter, Schalter und Sensoren. Es gibt keinen Fallback.
- **Proprietäres internes Protokoll:** Die Geräte sind an den Wibutler gebunden. Ein Austausch des Wibutlers würde eine Neu-Einrichtung aller Geräte erfordern.

---

## Huawei Wallbox iCharger s22 (22 kW)

**Protokoll:** OCPP (Open Charge Point Protocol)  
**Integration:** HACS-Integration direkt in Home Assistant  
**Fahrzeug:** VW ID.7

Die Wallbox ist vollständig lokal eingebunden – kein Huawei-Cloud-Account, kein Hersteller-Backend. Home Assistant kommuniziert direkt mit der Wallbox über OCPP.

### Integration

```
Home Assistant (OCPP HACS) → Wallbox → VW ID.7
```

Über Home Assistant sind Ladevorgänge steuerbar und protokollierbar (Ladestand, Leistung, Energie).

### Bekannte Schwächen

- **OCPP-Verbindung verliert sich gelegentlich:** Bei Verbindungsabbrüchen ist ein Neustart der HACS-Integration oder des HA-Containers notwendig.

---

## Eufy E340 (Außenkamera Garage)

**Montage:** Fest an der Garage  
**Verbindung:** WLAN über Repeater (am Switch in der Garage)  
**Integration:** Lokal, ohne Eufy-Cloud

Die Kamera wird vollständig lokal eingebunden. Der Eufy-Cloud-Dienst wird nicht genutzt.

### Integrations-Pipeline

```
Eufy E340 (Kamera)
    └── WLAN → Garage-Repeater → Switch → LAN
                    └── eufy-security-ws (Container)
                            └── go2rtc (Stream-Relay)
                                    └── Home Assistant (Kamera-Entität)
```

**eufy-security-ws** stellt eine lokale WebSocket-Verbindung zur Kamera her und umgeht die Eufy-Cloud. **go2rtc** transkodiert den RTSP-Stream in ein Format, das Home Assistant als Live-Bild und Bewegungserkennung einbinden kann.

### Bekannte Schwächen

- **Repeater als Schwachstelle:** Fällt der Garage-Repeater aus, verliert die Kamera die Netzwerkverbindung und ist weder lokal noch remote erreichbar.
- **eufy-security-ws Kompatibilität:** Updates der Eufy-Firmware können die lokale API brechen und die Integration unterbrechen. Nach Eufy-Firmware-Updates Container-Status prüfen.
- **Kein Speicher auf dem NAS:** Kameraaufnahmen werden nicht lokal gespeichert – nur Live-Stream in Home Assistant.

---

## Epson WF-3825 (Drucker / Scanner)

**Funktion:** Tintenstrahl-Multifunktionsgerät  
**Einbindung:** Netzwerkdrucker und Scanner für Paperless-NGX

Der Epson dient primär als Dokumentenscanner für Paperless-NGX. Scans werden manuell in den consume-Ordner auf dem NAS übertragen.

### Scan-Workflow

```
Epson WF-3825 (Scanner)
    └── Scan → manueller Upload / App
                    └── Paperless-NGX consume-Ordner
                            └── Automatische Verarbeitung (OCR, Klassifizierung)
```

Alternativ werden Dokumente über die Paperless-App oder per Smartphone-Scan eingespielt.

---

## Hichi IR-Lesekopf (Energiezähler)

**Geräte:** 2× Hichi WiFi IR-Lesekopf V2 (Tasmota, ESP32C3)  
**Protokoll:** MQTT (anonym, kein User/PW) → Mosquitto → Home Assistant  
**IPs:** 192.168.188.145 (Zähler 1646) · 192.168.188.146 (Zähler 1634)

| Zähler | Bezeichnung | MQTT Topic |
|---|---|---|
| 1APA011601**1646** | Allgemein (Hauptstrom) | `tele/hichi_1646/SENSOR` |
| 1APA011601**1634** | Heizung | `tele/hichi_1634/SENSOR` |

Die Leseköpfe senden per Tasmota SML-Script alle Zählerdaten (Bezug, Einspeisung, Leistung, Spannung L1–L3, Strom L1–L3, Frequenz) via MQTT. Phasendaten erfordern PIN-Aktivierung am Zähler (PIN kommt per Post von NetzeBW).

→ Vollständige Dokumentation: [Hardware/hichi.md](hichi.md)

---

## Smart Meter Gateway (EMH / NetzeBW)

> ⚠️ **Nicht mehr im Dashboard.** Das SMGW ist noch physisch angeschlossen und erreichbar, wird aber nicht mehr für das Energie-Dashboard genutzt (HAN-Schnittstelle funktioniert nicht zuverlässig). Energiedaten kommen jetzt von den Hichi IR-Leseköpfen.

**Anschluss:** LAN via Switch (HAN-Schnittstelle)  
**Hostname:** `eemh0015438871` · **IPv6:** `2003:de:9f37:1c00:215:3bff:fee4:1f5c`  
**Integration:** REST-Sensor in Home Assistant (konfiguriert, aber deaktiviert)

→ Vollständige Dokumentation: [Hardware/smartmeter.md](smartmeter.md)

---

## Mitsubishi Electric Klimaanlage (Multi-Split)

**System:** 1 Außengerät + 2 Innengeräte (Multi-Split R32)  
**Integration:** MELCloud Home (HACS, Custom Integration von Andrew-Blake) via MELCloud Cloud-API

### Geräte

| Typ | Modell | Raum | HA-Entität |
|---|---|---|---|
| Innengerät | MSZ-AY20VGKP | Wohnzimmer (EG) | `climate.melcloudhome_1b7f_0270_climate` |
| Innengerät | MSZ-AY35VGKP | Büro (DG) | `climate.melcloudhome_d64c_5427_climate` |
| Außengerät | MXZ-2F53VF4 | Außen (Multi-Split) | — |

### Integrations-Pipeline

```
Home Assistant (MELCloud Home HACS)
    └── MELCloud Cloud-API (Internet)
            └── Mitsubishi Electric MXZ-2F53VF4 (Außengerät)
                    ├── MSZ-AY20VGKP (Wohnzimmer)
                    └── MSZ-AY35VGKP (Büro)
```

### Nachlüften-Automatisierung

Nach mindestens 30 Minuten Betrieb im Heiz-/Kühlmodus wird beim Ausschalten automatisch ein 10-minütiger **fan_only**-Lauf gestartet, damit Kondenswasser aus dem Innengerät trocknet. Währenddessen ist der AUS-Button im Dashboard gesperrt (`input_boolean.nachluften_*_aktiv`). Nach Ablauf schaltet sich das Gerät selbstständig aus. Beide Bewohner erhalten eine Push-Benachrichtigung.

### Bekannte Schwächen

- **Cloud-Abhängigkeit ⚠️:** Die Integration läuft über die Mitsubishi MELCloud Cloud-API. Ist das Internet oder die MELCloud nicht erreichbar, ist keine Steuerung über Home Assistant möglich. Das Gerät selbst läuft weiter und ist per Fernbedienung bedienbar.
- **Polling-Latenz:** Statusupdates kommen mit einigen Sekunden Verzögerung durch die Cloud-Kommunikation.

---

## Buderus Lüftungsanlage

**Anschluss:** LAN via Switch  
**Integration mit Home Assistant:** nicht eingebunden  
**Status:** Eigenständig, keine HA-Automatisierungen

Die Lüftungsanlage ist zwar im Netzwerk, wird aber ausschließlich über ihre eigene Steuereinheit oder App betrieben. Keine Integration in Home Assistant geplant.

---

## Synology DS218J (Backup-NAS)

→ Vollständige Dokumentation in [backup/strategie.md](../backup/strategie.md)

**IP:** 192.168.188.135  
**DSM:** http://192.168.188.135:5000  
**Betrieb:** Wöchentlich (Montag, ~1 Stunde), danach automatisch aus
