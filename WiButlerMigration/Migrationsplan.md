# Wibutler-Migration – Eltako/EnOcean + Zigbee direkt in Home Assistant

Ablösung des **Wibutler Pro 2nd Gen** (Matter Bridge) durch eine direkte Anbindung der Eltako-Serie-14-Aktoren und der Zigbee-Geräte an Home Assistant.

→ Zielarchitektur: [Zielarchitektur.mmd](Zielarchitektur.mmd)

---

## Ausgangslage

```
Home Assistant → matter-server → Wibutler (Matter Bridge) → Eltako Serie 14 / EnOcean / Zigbee
```

**Probleme:**

- **Single Point of Failure ⚠️:** Fällt der Wibutler aus, verliert HA Licht, Rollläden, Markise und Sensoren.
- **Heizung nicht in HA ⚠️:** Die 3× F4HK14 (Evenes-Stellantriebe an den Heizkreisverteilern je Stockwerk) sind nicht über Matter erreichbar.
- **Kein Cover-Status über Matter:** Deshalb gibt es den Workaround `cover_status_refresh_matter` in `automations.yml` (Delay 65 s + `update_entity`).
- **Proprietär:** Die Geräte sind an den Wibutler gebunden.

## Ziel

- HA spricht **direkt** mit dem Eltako-Bus (über den vorhandenen **FAM14 per USB**) und mit Zigbee (über **Zigbee2MQTT + SLZB-06**).
- Die **Heizung** wird als `climate`-Entitäten in HA verfügbar.
- Die Migration läuft **schrittweise parallel**, der Wibutler bleibt bis zum Schluss als Fallback aktiv.
- Die **Entity-IDs bleiben gleich**, Dashboards und Automationen müssen nicht angepasst werden.

---

## Bestand

| Bereich | Geräte | Anbindung heute |
|---|---|---|
| Busmodul | Eltako **FAM14** | Sicherungskasten, Funk ↔ RS485-Bus |
| Licht / Schalten | FSR14, FUD14 | Wibutler per Funk über FAM14 |
| Rollläden / Jalousie / Markise | FSB14 | Wibutler per Funk über FAM14 |
| Heizung | **3× F4HK14** → Evenes-Stellantriebe (EG/OG/DG) | Nur Wibutler, **nicht in HA** |
| Raumfühler | Eltako **FFT55B** (Temp/Feuchte, EEP A5-04-02) | Wibutler → Matter → `sensor.raumtemperatur_*` |
| Wandtaster | EnOcean-Funktaster | **Direkt in die Aktoren eingelernt**, unabhängig vom Wibutler |
| Zigbee | Leuchtmittel/Lampen, Sensoren | Am Wibutler angelernt |

**Rahmenbedingungen:**

- HA läuft als Docker-Container (Portainer) auf dem UGREEN. Add-ons gibt es nicht, zusätzliche Dienste laufen als eigene Stacks.
- Der UGREEN steht **direkt neben dem Verteiler (< 5 m)**, der FAM14 kann also per USB angeschlossen werden.
- Mosquitto ist bereits vorhanden (HCPBridge, Hichi).
- LAN am Verteiler vorhanden.

---

## Zielarchitektur

```
                         ┌── MQTT ── Mosquitto ── Zigbee2MQTT (Portainer) ── TCP ── SLZB-06 (LAN) ── Zigbee-Geräte
Home Assistant (Docker) ─┤
                         └── Eltako-Integration (HACS) ── USB ── FAM14 ── RS485-Bus ── FSR14 / FSB14 / FUD14 / 3× F4HK14
                                                                   ▲                                         │
                                          FFT55B, Taster ── Funk ──┘                          Evenes-Stellantriebe
```

### Komponenten

| Baustein | Lösung | Begründung |
|---|---|---|
| EnOcean-Schnittstelle | **Vorhandener FAM14 per USB** (`device_type: fam14`, ESP2, 57600 Baud) | Keine Zusatzhardware. HA steuert die Aktoren über den Bus (per Kabel, nicht per Funk) und erhält den Status aller Aktoren. |
| HA-Integration | **Eltako Integration** (HACS, [grimmpp/home-assistant-eltako](https://github.com/grimmpp/home-assistant-eltako)) | Unterstützt FSR14/FSB14/FUD14, F4HK14 als `climate` (experimentell), FFT55B und Taster-Events. Funktioniert mit HA in Docker. |
| Konfig-Tools | **eo_man** (EnOcean Device Manager) + **Eltako PCT14** (Windows) | eo_man scannt den FAM14 und erzeugt die YAML. Mit PCT14 werden die HA-Sender-IDs in die Aktoren eingetragen. |
| Zigbee-Koordinator | **SMLIGHT SLZB-06 / SLZB-06M** (Ethernet, PoE) | Wird zentral im Haus platziert, **nicht** im Metallverteiler. |
| Zigbee-Software | **Zigbee2MQTT** als Portainer-Stack | Nutzt den vorhandenen Mosquitto, breite Geräteunterstützung, eigene Web-UI. |

### FAM14 vs. FGW14-USB

| | FAM14 (vorhanden) | FGW14-USB (optional) |
|---|---|---|
| Aktoren am Bus schalten | ✅ | ✅ |
| Status aller Bus-Aktoren | ✅ | ✅ |
| Funk-Telegramme (Fühler, Taster) | ✅ | über Bus/FAM14 |
| Traffic zu HA | gesamter Bus-Traffic | nur Status-Telegramme |
| Zusatzhardware | keine | FGW14-USB |

> **Entscheidung:** Start mit dem FAM14. Wenn HA durch den Bus-Traffic träge wird oder Telegramme verloren gehen, wird auf **FGW14-USB** gewechselt. Dafür ändert sich der `device_type` in der YAML, und die Sender-IDs werden neu eingelernt.

> **Hinweis:** PCT14 und eo_man nutzen dieselbe USB-Buchse am FAM14. Zum Einlernen wird das USB-Kabel kurz vom NAS zum Laptop umgesteckt. Die Eltako-Geräte sind dann für einige Minuten nicht über HA steuerbar, die Taster funktionieren aber weiter.

---

## Phase 0 – Bestandsaufnahme (ohne Eingriff)

- [ ] Im Wibutler die Geräteliste exportieren bzw. abfotografieren: alle Aktoren mit Kanal, Raum und Funktion sowie die Zigbee-Geräte mit Hersteller und Modell.
- [ ] Windows-Laptop mit **PCT14** an die USB-Buchse des FAM14 anschließen und alle Aktoren auslesen.
- [ ] **Die PCT14-Sicherung aller Aktoren speichern** (Rollback-Basis!).
- [ ] Pro Kanal die eingelernten IDs notieren: Wibutler-Sender-IDs, Taster, FFT55B.
- [ ] Mit **eo_man** eine erste `eltako.yaml` aus dem FAM14-Scan erzeugen und die **Base-ID des FAM14** notieren.
- [ ] Heizung klären: Sendet der Wibutler Soll- **und** Ist-Temperatur (EEP A5-10-06) an die F4HK14, oder ist der FFT55B direkt im F4HK14 eingelernt? Davon hängt die Teach-in-Variante in Phase 3 ab.
- [ ] Mapping-Tabelle unten ausfüllen.

### Mapping Matter-Entität → Eltako-Kanal

| HA-Entity-ID (heute, Matter) | Raum | Aktor | Kanal | Aktor-ID | Wibutler-Sender-ID | HA-Sender-ID (neu) | Status |
|---|---|---|---|---|---|---|---|
| `cover.rolladen_buro_nordseite` | Büro | FSB14 | | | | | offen |
| `cover.rolladen_buro_ostseite` | Büro | FSB14 | | | | | offen |
| `cover.rolladen_flur_og` | Flur OG | FSB14 | | | | | offen |
| `cover.rolladen_bad_og` | Bad OG | FSB14 | | | | | offen |
| `cover.jalousie_galerie_og` | Galerie OG | FSB14 | | | | | offen |
| `cover.markise_terrasse_eg` | Terrasse EG | FSB14 | | | | | offen |
| `switch.deckenlampe_ankleide` | Ankleide | FSR14 | | | | | offen |
| `light.deckenlampe_technikraum_2` | Technikraum | | | | | | offen |
| `light.deckenlampe_technikraum_3` | Technikraum | | | | | | offen |
| `light.spiegel_bad_og` | Bad OG | | | | | | offen |
| `light.spot_dusche_bad_og` | Bad OG | | | | | | offen |
| `light.wandlampe_balkon` | Balkon | | | | | | offen |
| *(Heizkreise F4HK14 #1–#3, je 4 Kanäle)* | | F4HK14 | | | | | offen |
| *(weitere aus der Wibutler-Liste)* | | | | | | | |

### Mapping Raumfühler (FFT55B)

| HA-Entity-ID (heute) | Raum | FFT55B-ID | Heizkreis (F4HK14/Kanal) |
|---|---|---|---|
| `sensor.raumtemperatur_abstellraum_temperatur` | Abstellraum | | |
| `sensor.raumtemperatur_ankleide_temperatur` | Ankleide | | |
| `sensor.raumtemperatur_bad_temperatur` | Bad | | |
| `sensor.raumtemperatur_bad_dg_temperatur` | Bad DG | | |
| `sensor.raumtemperatur_buhne_temperatur` | Bühne | | |
| `sensor.raumtemperatur_flur_temperatur` | Flur | | |
| `sensor.raumtemperatur_gast_temperatur` | Gast | | |
| `sensor.raumtemperatur_kind_temperatur` | Kind | | |
| `sensor.raumtemperatur_schlafen_temperatur` | Schlafen | | |
| `sensor.raumtemperatur_wc_temperatur` | WC | | |
| `sensor.raumtemperatur_wohnen_essen_temperatur` | Wohnen/Essen | | |
| `sensor.raumtemperatur_zimmer_temperatur` | Zimmer | | |

### Mapping Zigbee

| HA-Entity-ID (heute) | Gerät (Hersteller/Modell) | Typ | Z2M friendly_name | Status |
|---|---|---|---|---|
| | | Leuchtmittel | | offen |
| | | Sensor | | offen |

---

## Phase 1 – Infrastruktur (Wibutler läuft unverändert weiter)

### 1.1 FAM14 an den NAS anschließen

1. Den FAM14 (Mini-USB-Buchse vorne) per USB-A ↔ Mini-USB-Kabel an den UGREEN anschließen, ohne Hub und ohne Verlängerung.
2. Per SSH auf dem UGOS-Host prüfen, ob das Gerät erkannt wird:
   ```bash
   ls -l /dev/serial/by-id/
   dmesg | grep -i -E "ftdi|ttyUSB"
   ```
   > ⚠️ **Blocker-Check:** Erscheint kein Gerät, fehlt vermutlich der USB-Serial-Treiber in UGOS. Ausweichlösungen dafür: FGW14-USB (anderer Chip) oder ein EnOcean-LAN-Gateway (PioTek MGW LAN, `device_type: mgw-lan`).
3. Den HA-Stack in Portainer um das Gerät erweitern. Dabei den stabilen by-id-Pfad nutzen, nicht `ttyUSB0`:
   ```yaml
   services:
     homeassistant:
       devices:
         - /dev/serial/by-id/usb-<FAM14-ID>:/dev/ttyFAM14
   ```
4. Die Drehschalter-Stellung des FAM14 für den Gateway-Betrieb laut Eltako-Anleitung und Integrations-Doku prüfen. Der Wibutler-Betrieb über Funk muss dabei unverändert weiterlaufen.

### 1.2 Zigbee-Koordinator

1. Den SLZB-06 zentral im Haus platzieren (nicht im Verteiler), per LAN und PoE anschließen. Die Switches haben kein PoE, deshalb einen PoE-Injektor oder ein USB-C-Netzteil nutzen.
2. In der FritzBox eine DHCP-Reservierung (feste IP) vergeben.
3. In der SLZB-Web-UI: Koordinator-Firmware aktualisieren, Modus „Zigbee Coordinator (LAN)".

### 1.3 Zigbee2MQTT-Stack

Neuer Portainer-Stack `zigbee2mqtt`, Daten auf volume2:

```yaml
services:
  zigbee2mqtt:
    image: koenkk/zigbee2mqtt:latest
    container_name: zigbee2mqtt
    restart: unless-stopped
    ports:
      - "8080:8080"   # ggf. anpassen – SearXNG belegt 8080 intern (Mac Mini), Port prüfen
    volumes:
      - /volume2/docker/zigbee2mqtt:/app/data
    environment:
      - TZ=Europe/Berlin
```

Wichtige Einträge in `configuration.yaml` von Z2M:

```yaml
mqtt:
  server: mqtt://192.168.188.130:1883
serial:
  port: tcp://<SLZB-IP>:6638
  adapter: zstack          # SLZB-06 (CC2652P); SLZB-06M → ember
advanced:
  channel: 25              # nicht mit 2,4-GHz-WLAN der FritzBox überlappen
homeassistant:
  enabled: true
frontend:
  enabled: true
```

### 1.4 Eltako-Integration

1. HACS → Integration „Eltako" installieren und HA neu starten.
2. `configuration.yml` ergänzen:
   ```yaml
   eltako: !include eltako.yaml
   ```
3. Grundgerüst `eltako.yaml`, auf Basis des eo_man-Exports:
   ```yaml
   gateway:
     - id: 1
       name: FAM14 Verteiler
       device_type: fam14
       serial_path: /dev/ttyFAM14
       base_id: FF-xx-xx-00          # aus eo_man / PCT14
       devices:
         sensor: []
         light: []
         switch: []
         cover: []
         climate: []
   ```

### ✅ Abnahme Phase 1

- [ ] Die Eltako-Integration zeigt das Gateway als verbunden.
- [ ] Unter Entwicklerwerkzeuge → Ereignisse kommen Telegramme von Tastern, FFT55B und Aktor-Statusmeldungen an.
- [ ] Die Z2M-Web-UI ist erreichbar und der Koordinator verbunden.
- [ ] Der Wibutler funktioniert unverändert.

---

## Phase 2 – Sensoren und Aktoren parallel einbinden

### 2.1 FFT55B-Raumfühler (passiv, ohne Teach-in)

```yaml
sensor:
  - id: FF-xx-xx-xx
    eep: A5-04-02
    name: Raumtemperatur Wohnen/Essen
```

- [ ] Alle FFT55B eintragen und die Werte mit den bestehenden `sensor.raumtemperatur_*` (Matter) vergleichen.

### 2.2 Aktoren FSR14 / FUD14 / FSB14

1. Das USB-Kabel vom NAS zum Laptop umstecken.
2. Mit PCT14 die **HA-Sender-IDs (FAM14-Base-ID + Offset) zusätzlich** in jeden Kanal eintragen. **Die Wibutler-IDs bleiben drin**, der Wibutler steuert also weiter.
3. Das USB-Kabel zurück an den NAS stecken.
4. Die Einträge in `eltako.yaml` anlegen:
   ```yaml
   cover:
     - id: 00-00-00-0x               # FSB14-Kanal
       eep: G5-3F-7F
       name: Rolladen Büro Nordseite
       sender:
         id: FF-xx-xx-0y             # HA-Sender-ID
         eep: H5-3F-7F
       time_closes: 25
       time_opens: 25
   ```
   Fahrzeiten je Behang messen, Jalousien bis ca. 55 s.
5. Alle Geräte testen: schalten, dimmen, fahren. Den Status auch bei Bedienung **per Wandtaster** prüfen.

### 2.3 Umstellen, Raum für Raum

Pro Gerät:

1. Die alte Matter-Entität umbenennen, z.B. `cover.rolladen_buro_nordseite` → `cover.rolladen_buro_nordseite_matter`.
2. Die neue Eltako-Entität auf die **alte Entity-ID** umbenennen (Einstellungen → Geräte & Dienste → Entitäten).
3. Dashboards (`Dashboard/*.yml`) und Automationen (z.B. „Fynn Bettzeit") prüfen. Sie laufen ohne Änderung weiter.
4. Den Status in der Mapping-Tabelle auf „migriert" setzen.

---

## Phase 3 – Heizung (3× F4HK14)

> ⚠️ Der `climate`-Support für F4HK14 ist in der Integration als **experimentell** markiert. Deshalb pro Stockwerk umstellen und den Rollback-Pfad offen halten.

1. Pro Heizkreis (bis zu 12 Kanäle) einen `climate`-Eintrag anlegen:
   ```yaml
   climate:
     - id: 00-00-00-xx               # F4HK14-Kanal
       eep: A5-10-06
       name: Heizung Wohnen/Essen
       temperature_unit: "°C"
       min_target_temperature: 17
       max_target_temperature: 25
       sender:
         id: FF-xx-xx-zz             # virtueller HA-Regler
         eep: A5-10-06
   ```
2. Die HA-Regler-Sender-ID per PCT14 in **Funktionsgruppe 3** des jeweiligen F4HK14-Kanals eintragen. Den FFT55B je nach Ergebnis aus Phase 0 als Ist-Wert-Geber behalten.
3. **Pro F4HK14 komplett umstellen, nicht kanalweise gemischt.** Die Wibutler-Regler-ID aus den Kanälen entfernen, damit nicht zwei Regler gleichzeitig Sollwerte senden.
4. Mit **einem Stockwerk** beginnen und 1–2 Wochen beobachten, erst dann die übrigen F4HK14 umstellen.
5. Mit PCT14 prüfen und dokumentieren, wie sich der F4HK14 verhält, wenn der Regler ausfällt (NAS aus): Er hält den letzten Sollwert oder geht in den Notlauf.
6. Optional: Heizprofile und Nachtabsenkung als HA-Automationen, Einbindung ins Dashboard `Klimasteuerung.yml`.

---

## Phase 4 – Zigbee umziehen

Zigbee-Netze lassen sich nicht übertragen, jedes Gerät muss neu gepairt werden.

1. **Zuerst die netzbetriebenen Leuchtmittel** (Zigbee-Router), damit das Mesh steht:
   1. Das Gerät im Wibutler löschen.
   2. Das Gerät auf Werkseinstellungen zurücksetzen (bei Leuchtmitteln meist mehrfaches Ein/Aus).
   3. In Z2M „Permit join" aktivieren und das Gerät pairen.
   4. Einen `friendly_name` setzen und die Entität in HA auf die alte Entity-ID umbenennen.
2. **Danach die Batterie-Sensoren** nach dem gleichen Ablauf.
3. In der Z2M-Netzwerkkarte die LQI prüfen und bei schwachen Verbindungen die Router ergänzen oder umplatzieren.

---

## Phase 5 – Abschalten und Aufräumen

- [ ] Alle Einträge in der Mapping-Tabelle stehen auf „migriert".
- [ ] Die Matter-Integration in HA entfernen.
- [ ] Den Portainer-Stack `matter-server` stoppen und löschen.
- [ ] Den Wibutler abklemmen (**noch nicht entsorgen**, 4 Wochen als Rollback aufbewahren).
- [ ] Die Wibutler-Sender-IDs per PCT14 aus allen Aktoren entfernen (optional, erst nach der Rollback-Frist).
- [ ] Die Automation `cover_status_refresh_matter` aus `Configuration/automations.yml` löschen. Die FSB14 senden jetzt selbst ihren Status.

### Doku-Updates

**Repo `home-server`:**

- [ ] `Architecture/HomeServer.mmd`: Wibutler und matter-server entfernen. Neu: FAM14 (USB), Eltako-Bus, Heizung, SLZB-06, Zigbee2MQTT. Vorlage ist [Zielarchitektur.mmd](Zielarchitektur.mmd).
- [ ] `README.md`: Mermaid-Diagramm, IP-Tabelle (SLZB-06 neu, Wibutler raus), Schwächen.
- [ ] `Hardware/geraete.md`: Den Wibutler-Abschnitt ersetzen durch „Eltako Serie 14 / EnOcean" und „Zigbee". Die Schwächen neu bewerten.
- [ ] `ContainerStack/Readme/home-assistant.md`: Integrationen, Container-Tabelle und Neustart-Reihenfolge (zigbee2mqtt statt matter-server) anpassen, „Heizung nicht integriert" streichen.
- [ ] `Architecture/overview.md`: Smarthome-Schicht und physische Topologie.
- [ ] `Network/network.md`: SLZB-06-IP ergänzen, Wibutler entfernen.
- [ ] Neu: `ContainerStack/Readme/zigbee2mqtt.md`.
- [ ] Neu: `Hardware/eltako.md` mit der finalen Kanal-/ID-Tabelle aus Phase 0.

**Repo `HomeAssistant`:**

- [ ] `Configuration/configuration.yml`: `eltako: !include eltako.yaml`.
- [ ] Neu: `Configuration/eltako.yaml`.
- [ ] `Configuration/automations.yml`: Refresh-Automation entfernen.
- [ ] `Informations/Installed_HACS.yml`: „Eltako Integration" ergänzen.

---

## Einkaufsliste

→ Ausführliche Liste mit Spezifikationen und Kabeln: [Hardwareliste.md](Hardwareliste.md)

| Artikel | Zweck | Pflicht |
|---|---|---|
| USB-A ↔ Mini-USB-Kabel (geschirmt) FAM14 ↔ NAS | EnOcean-Schnittstelle | ✅ (ggf. vorhanden) |
| SMLIGHT SLZB-06 oder SLZB-06M | Zigbee-Koordinator (LAN/PoE) | ✅ |
| PoE-Injektor oder USB-C-Netzteil | Stromversorgung SLZB-06 | ✅ |
| Eltako PCT14 (kostenlos) + Windows-Laptop | Aktoren konfigurieren / Teach-in | ✅ |
| Eltako FGW14-USB | Entlastung, falls FAM14-Traffic stört | optional |

---

## Risiken

| Risiko | Auswirkung | Gegenmaßnahme |
|---|---|---|
| F4HK14-`climate` ist experimentell | Heizung regelt nicht wie erwartet | Pro Stockwerk umstellen, 1–2 Wochen beobachten, Wibutler-IDs erst spät entfernen |
| UGOS erkennt den FAM14 nicht (USB-Treiber) | Die FAM14-Lösung geht nicht | Blocker-Check zu Beginn von Phase 1, Ausweichlösung FGW14-USB / MGW LAN |
| FAM14-Bus-Traffic | HA wird träge | Wechsel auf FGW14-USB |
| USB-Buchse geteilt mit PCT14 | Kurze Unterbrechung beim Einlernen | Einlernen gebündelt planen, die Taster funktionieren weiter |
| Zigbee muss neu gepairt werden | Aufwand, Zugang zu jedem Gerät nötig | Zuerst die Router, dann die Sensoren, Mapping-Tabelle führen |
| **Neuer SPOF: NAS statt Wibutler** | Bei NAS-Ausfall keine HA-Steuerung | Taster funktionieren weiterhin direkt, Heizung hält Sollwert / Notlauf, Zigbee-Leuchten fallen aus |

---

## Verifikation

| Phase | Test | Erwartung |
|---|---|---|
| 1 | Taster drücken, Entwicklerwerkzeuge → Ereignisse | Eltako-Event erscheint |
| 1 | Z2M-Web-UI öffnen | Koordinator verbunden |
| 2 | Jede Entität schalten/fahren | Aktor reagiert, Status stimmt |
| 2 | Wandtaster bedienen | Der HA-Status aktualisiert sich ohne Refresh-Automation |
| 2 | Dashboards öffnen | Keine Kacheln „nicht verfügbar" |
| 3 | Sollwert in HA ändern | F4HK14-Kanal schaltet, Stellantrieb öffnet |
| 3 | Temperaturverlauf über 1–2 Wochen | Stabile Regelung ohne Überschwingen |
| 4 | Z2M-Netzwerkkarte | Alle Geräte mit guter LQI, Sensoren melden regelmäßig |
| 5 | 24 h nach Abklemmen des Wibutlers | Keine unavailable-Entitäten, Automationen laufen (Logbuch) |
