# Smart Meter Gateway (EMH / NetzeBW HAN)

Dokumentation des Smart Meter Gateways (SMGW) von NetzeBW, eingebunden über die lokale HAN-Schnittstelle.

---

## Grunddaten

| | |
|---|---|
| Hersteller | EMH Metering |
| Hostname | `eemh0015438871` |
| MAC-Adresse | `00:15:3B:E4:1F:5C` |
| IPv6-Adresse | `2003:de:9f37:1c00:215:3bff:fee4:1f5c` |
| Meter-ID | `1apa0116011646` |
| Netzbetreiber | NetzeBW |
| Schnittstelle | HAN (Home Area Network) |

---

## Physische Anbindung

Das SMGW ist über ein LAN-Kabel an einen der beiden 8-Port-Switches im Heimnetz angeschlossen. Die Verbindung nutzt die **HAN-Schnittstelle** des Gateways – der physische Anschluss am Gerät ist ein RJ45-Port.

```
Smart Meter Gateway (HAN-Port)
    └── LAN-Kabel → Switch → Heimnetz
```

Das SMGW nutzt ausschließlich IPv6. Eine IPv4-Adresse wird vom FritzBox-DHCP nicht vergeben.

---

## API / Datenzugriff

| | |
|---|---|
| Endpunkt | `https://[2003:de:9f37:1c00:215:3bff:fee4:1f5c]/json/realtimedata` |
| Authentifizierung | HTTP Digest Auth |
| Benutzername | `0286509356008798278976` (User-ID aus dem Brief) |
| Passwort | Persönliches Passwort aus NetzeBW-Brief |
| TLS | Selbstsigniertes Zertifikat (`verify_ssl: false`) |
| Empfohlenes Intervall | 15 Minuten (NetzeBW-Empfehlung – zu häufiges Polling kann SMGW sperren) |

### DNS-Sonderfall

Der Hostname `eemh0015438871` wird von AdGuard Home / FritzBox im Heimnetz aufgelöst, jedoch **nicht** aus dem Home Assistant Docker-Container heraus. Die IPv6-Adresse muss daher direkt (hardcodiert) als Endpunkt verwendet werden.

---

## OBIS-Datenpunkte

Das Gateway liefert alle 13 Messwerte in einem JSON-Array. Jeder Eintrag enthält `logical_name`, `value`, `scaler` und `unit`. Der tatsächliche Wert ergibt sich aus `value × 10^scaler`.

| OBIS-Code | Bezeichnung | Einheit | Scaler | HA-Sensor |
|---|---|---|---|---|
| `0100010800ff` | Wirkenergie Bezug gesamt | Wh → kWh | -3 | `sensor.smartmeter_bezug_gesamt` |
| `0100020800ff` | Wirkenergie Einspeisung gesamt | Wh → kWh | -3 | `sensor.smartmeter_einspeisung_gesamt` |
| `01000e0700ff` | Netzfrequenz | Hz | -2 | `sensor.smartmeter_netzfrequenz` |
| `0100100700ff` | Wirkleistung gesamt | W | -3 | `sensor.smartmeter_wirkleistung` |
| `0100200700ff` | Spannung L1 | V | -2 | `sensor.smartmeter_spannung_l1` |
| `0100340700ff` | Spannung L2 | V | -2 | `sensor.smartmeter_spannung_l2` |
| `0100480700ff` | Spannung L3 | V | -2 | `sensor.smartmeter_spannung_l3` |
| `01001f0700ff` | Strom L1 | A | -2 | `sensor.smartmeter_strom_l1` |
| `0100330700ff` | Strom L2 | A | -2 | `sensor.smartmeter_strom_l2` |
| `0100470700ff` | Strom L3 | A | -2 | `sensor.smartmeter_strom_l3` |
| `0100510704ff` | Phasenwinkel L1 | ° | -1 | (kein HA-Sensor) |
| `010051070fff` | Phasenwinkel L2 | ° | -1 | (kein HA-Sensor) |
| `010051071aff` | Phasenwinkel L3 | ° | -1 | (kein HA-Sensor) |

> Die Einspeisung (`0100020800ff`) ist mit PV-Anlage relevant. Aktuell zeigt sie den minimalen Initialwert von ~0,22 kWh.

---

## Home Assistant Integration

Die Einbindung erfolgt über die native **REST-Integration** von Home Assistant (kein HACS nötig).

**Konfiguration:** `smgw_sensor.yaml`, eingebunden in `configuration.yaml` via:
```yaml
rest: !include smgw_sensor.yaml
```

Die Jinja2-Templates greifen den Meter-Key dynamisch ab (zukunftssicher für Gerätewechsel):
```yaml
{% set meter_id = value_json.meter | list | first %}
{% set values = value_json.meter[meter_id]['values'] %}
{% set v = values | selectattr('logical_name', 'search', '<OBIS>') | first %}
{{ (v.value | float * (10 ** v.scaler)) | round(1) }}
```

Für das **Energy Dashboard** in HA relevant:
- Netzbezug: `sensor.smartmeter_bezug_gesamt`
- Netzeinspeisung (nach PV-Installation): `sensor.smartmeter_einspeisung_gesamt`

---

## Bekannte Schwächen

- **Hardcodierte IPv6-Adresse:** Falls das SMGW eine neue IPv6-Adresse bekommt (z.B. nach Austausch durch NetzeBW), muss die Adresse in `smgw_sensor.yaml` manuell aktualisiert werden.
- **15-Minuten-Grenze:** NetzeBW empfiehlt kein kürzeres Polling-Intervall. Ein zu aggressives `scan_interval` kann das SMGW in einen Sperrzustand versetzen.
- **Kein Echtzeit-Monitoring:** Bei 15-Minuten-Auflösung sind Lastspitzen zwischen zwei Abfragen unsichtbar.
- **HAN parallel zu CLS:** Der HAN-Lesezugriff und ein möglicher CLS-Kanal (§14a EnWG – steuerbare Verbrauchseinrichtungen) laufen unabhängig. Eine spätere PV-Anlage oder Wallbox-Steuerung durch den Netzbetreiber über CLS beeinträchtigt den lokalen Lesezugriff nicht.
