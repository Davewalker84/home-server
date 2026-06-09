# Hichi IR-Lesekopf (Energiezähler)

Dokumentation der zwei Hichi WiFi IR-Leseköpfe für die Stromzähler von NetzeBW.

---

## Zähler & Geräte

| Zähler-ID | Bezeichnung | Zählerstand (ca.) | Hichi IP | MQTT Topic |
|---|---|---|---|---|
| 1APA011601**1646** | Allgemein (Hauptstrom) | ~12.560 kWh | 192.168.188.**145** | `hichi_1646` |
| 1APA011601**1634** | Heizung | ~7.718 kWh | 192.168.188.**146** | `hichi_1634` |

**Zählermodell:** Apator APDX+ 3.HZ.GRID.D.060.4.T.N (3-phasig, 230/400V, 60A, Polen 2022)  
**Lesekopf:** Hichi WiFi IR-Lesekopf V2  
**Firmware:** Tasmota 14.6.0.2 (tasmota32, ESP32C3)  
**WLAN:** Feste IP-Adressen per DHCP-Reservierung vergeben  
**IR-Montage:** Lesekopf muss 180° gedreht montiert werden

---

## Netzwerk / MQTT

| Feld | Hichi 1646 (Allgemein) | Hichi 1634 (Heizung) |
|---|---|---|
| IP | 192.168.188.145 | 192.168.188.146 |
| MQTT Broker | 192.168.188.130:1883 | 192.168.188.130:1883 |
| Client-ID | `hichi_1646` | `hichi_1634` |
| Topic | `hichi_1646` | `hichi_1634` |
| Full Topic | `%prefix%/%topic%/` | `%prefix%/%topic%/` |
| Authentifizierung | anonym (kein User/PW) | anonym (kein User/PW) |

MQTT-Nachrichten erscheinen auf: `tele/hichi_1646/SENSOR` bzw. `tele/hichi_1634/SENSOR`

---

## Tasmota SML-Script

Identisch für beide Geräte. Eingabe unter: **Tools → Edit Script** → „Script enable" anhaken → Save

```
>D
>B
->sensor53 r
>M 1
+1,3,s,16,9600,APDX,1
1,77070100010800ff@1000,Verbrauch,kWh,E_in,3
1,77070100020800ff@1000,Einspeisung,kWh,E_out,3
1,77070100100700ff@1,Leistung,W,Power,0
1,77070100200700ff@1,Spannung L1,V,Volt_L1,1
1,77070100340700ff@1,Spannung L2,V,Volt_L2,1
1,77070100480700ff@1,Spannung L3,V,Volt_L3,1
1,770701001f0700ff@1,Strom L1,A,Curr_L1,2
1,77070100330700ff@1,Strom L2,A,Curr_L2,2
1,77070100470700ff@1,Strom L3,A,Curr_L3,2
1,770701000e0700ff@1,Frequenz,Hz,Freq,2
1,77070100510704ff@1,Phasenwinkel L1,deg,Phase_L1,1
1,7707010051070fff@1,Phasenwinkel L2,deg,Phase_L2,1
1,7707010051071aff@1,Phasenwinkel L3,deg,Phase_L3,1
#
```

---

## MQTT JSON-Format

Topic: `tele/hichi_1646/SENSOR` (analog für `hichi_1634`)

```json
{
  "Time": "2026-06-09T19:00:00",
  "APDX": {
    "E_in": 12560.853,
    "E_out": 0.219,
    "Power": 347,
    "Volt_L1": 231.2,
    "Volt_L2": 230.8,
    "Volt_L3": 231.5,
    "Curr_L1": 1.23,
    "Curr_L2": 0.87,
    "Curr_L3": 1.05,
    "Freq": 50.01,
    "Phase_L1": -1.0,
    "Phase_L2": -1.0,
    "Phase_L3": -1.0
  }
}
```

> ⚠️ **PIN erforderlich für Phasendaten:** Leistung, Spannung, Strom und Frequenz liefern den Wert 0, bis der NetzeBW-PIN am Zähler aktiviert ist (Taster am Zähler + `InF = on`). `E_in` und `E_out` funktionieren ohne PIN.

---

## Home Assistant – MQTT-Sensoren

Konfiguration in `configuration.yaml` unter dem bestehenden `mqtt:`-Block (kein zweites `mqtt:` anlegen).

### Zähler 1646 – Allgemein (Hauptstrom)

| Entität | Beschreibung | Einheit |
|---|---|---|
| `sensor.hichi_1646_verbrauch_gesamt` | Zählerstand Netzbezug | kWh |
| `sensor.hichi_1646_einspeisung_gesamt` | Zählerstand Einspeisung | kWh |
| `sensor.hichi_1646_wirkleistung` | Aktuelle Wirkleistung | W |
| `sensor.hichi_1646_spannung_l1` | Spannung Phase L1 | V |
| `sensor.hichi_1646_spannung_l2` | Spannung Phase L2 | V |
| `sensor.hichi_1646_spannung_l3` | Spannung Phase L3 | V |
| `sensor.hichi_1646_strom_l1` | Strom Phase L1 | A |
| `sensor.hichi_1646_strom_l2` | Strom Phase L2 | A |
| `sensor.hichi_1646_strom_l3` | Strom Phase L3 | A |
| `sensor.hichi_1646_frequenz` | Netzfrequenz | Hz |

### Zähler 1634 – Heizung

| Entität | Beschreibung | Einheit |
|---|---|---|
| `sensor.hichi_1634_verbrauch_gesamt` | Zählerstand Netzbezug | kWh |
| `sensor.hichi_1634_einspeisung_gesamt` | Zählerstand Einspeisung | kWh |
| `sensor.hichi_1634_wirkleistung` | Aktuelle Wirkleistung | W |
| `sensor.hichi_1634_spannung_l1` | Spannung Phase L1 | V |
| `sensor.hichi_1634_spannung_l2` | Spannung Phase L2 | V |
| `sensor.hichi_1634_spannung_l3` | Spannung Phase L3 | V |
| `sensor.hichi_1634_strom_l1` | Strom Phase L1 | A |
| `sensor.hichi_1634_strom_l2` | Strom Phase L2 | A |
| `sensor.hichi_1634_strom_l3` | Strom Phase L3 | A |
| `sensor.hichi_1634_frequenz` | Netzfrequenz | Hz |

### Wallbox-Hinweis

Die Wallbox (Huawei SCharger-22KT) hängt physisch am Zähler 1646 (Allgemein). Ihr Verbrauch ist in `sensor.hichi_1646_verbrauch_gesamt` bereits enthalten – kein separater Zähler. Im Energie-Dashboard ist die Wallbox daher als „davon Wallbox"-Linie dargestellt, nicht als eigenständige Energiequelle addiert.

---

## Energie-Dashboard

Das Energie-Dashboard in Home Assistant nutzt ausschließlich die Hichi-Sensoren:

- **Netzbezug:** `sensor.hichi_1646_verbrauch_gesamt` (Haushalt) + `sensor.hichi_1634_verbrauch_gesamt` (Heizung)
- **Einspeisung:** `sensor.hichi_1646_einspeisung_gesamt`
- **Live-Leistung:** `sensor.hichi_1646_wirkleistung`, `sensor.hichi_1634_wirkleistung`

---

## Status & offene Schritte

- [x] Hichi-Geräte ins WLAN eingebunden (feste IPs)
- [x] MQTT-Verbindung zu Mosquitto hergestellt
- [x] Tasmota SML-Script aktiv
- [x] Zählerstand E_in wird korrekt ausgelesen
- [x] MQTT-Sensoren in `configuration.yaml` eingebunden
- [x] Energie-Dashboard auf Hichi-Entitäten umgestellt
- [ ] **PIN von NetzeBW** per Post abwarten → am Zähler aktivieren (Taster + `InF = on`)
- [ ] Nach PIN-Aktivierung: Leistung, Spannung, Strom, Frequenz prüfen

---

## Bekannte Schwächen

- **Phasendaten ohne PIN nutzlos:** Bis zur PIN-Aktivierung zeigen L1/L2/L3 den Wert 0. Der PIN wird von NetzeBW per Post zugestellt.
- **Keine Authentifizierung:** Die Hichi-Geräte verbinden sich anonym am Mosquitto-Broker (kein User/PW). Mosquitto ist ausschließlich im lokalen Heimnetz erreichbar – kein externer Zugriff auf Port 1883.
- **IR-Positionierung:** Der Lesekopf muss 180° gedreht montiert werden – bei falschem Sitz werden keine Daten gelesen.
