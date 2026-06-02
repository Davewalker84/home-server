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

## Smart Meter Gateway (EMH / NetzeBW)

**Anschluss:** LAN via Switch (HAN-Schnittstelle)  
**Hostname:** `eemh0015438871` · **IPv6:** `2003:de:9f37:1c00:215:3bff:fee4:1f5c`  
**Integration:** REST-Sensor in Home Assistant (Digest Auth, 15-Minuten-Intervall)

Das SMGW wird von NetzeBW betrieben und stellt über die HAN-Schnittstelle lokale Verbrauchsdaten bereit. Home Assistant liest die Daten direkt per HTTPS-API – ohne Cloud, ohne TRuDI.

Verfügbare Messwerte: Zählerstand Bezug/Einspeisung, Wirkleistung, Spannung und Strom auf allen drei Phasen, Netzfrequenz.

→ Vollständige Dokumentation: [Hardware/smartmeter.md](smartmeter.md)

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
