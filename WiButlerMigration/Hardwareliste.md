# Hardware-Liste – Wibutler-Migration

Was für die Migration beschafft werden muss (→ [Migrationsplan.md](Migrationsplan.md)).

> **Kurzfassung:** Für den EnOcean/Eltako-Teil ist **keine neue Eltako-Hardware** nötig, es wird der vorhandene FAM14 genutzt. Zu kaufen sind nur Kabel, der Zigbee-Koordinator und dessen Stromversorgung.

> Die Preise sind grobe Richtwerte und vor dem Kauf zu prüfen.

---

## 1. Pflicht – EnOcean / Eltako (FAM14 ↔ NAS)

| # | Artikel | Spezifikation | Menge | Preis (ca.) | Hinweis |
|---|---|---|---|---|---|
| 1 | **USB-Kabel USB-A auf Mini-USB (Mini-B)** | USB 2.0, **geschirmt, mit Ferritkern**, Länge nach Abstand NAS ↔ Verteiler (1,5–3 m, **max. 5 m**) | 1 | 5–10 € | Der FAM14 hat vorne eine **Mini-USB-Buchse**. Das Kabel bleibt dauerhaft zwischen FAM14 und dem USB-A-Port des UGREEN DXP4800. Möglichst kurz halten und nicht parallel zu 230-V-Leitungen im Verteiler führen. |
| 2 | **Zweites USB-A auf Mini-USB-Kabel** | USB 2.0, 1–2 m | 1 | 5 € | Für Laptop/PCT14 beim Einlernen. So muss das Dauerkabel nicht aus dem Verteiler gezogen werden, es wird nur am Stecker getauscht. Optional, aber praktisch. |
| 3 | Kabeldurchführung / Kantenschutz | Bürstenleiste oder Kantenschutz für die Verteilertür | 1 | 2–5 € | Nur falls das Kabel sonst nicht sauber aus dem Verteiler geführt werden kann. |

> ⚠️ **Sicherheit:** Die Mini-USB-Buchse liegt an der **Frontseite** des FAM14 und ist bei geöffneter Verteilertür ohne Abnehmen der Abdeckung zugänglich. **Abdeckungen im Verteiler nur durch eine Elektrofachkraft öffnen.**

> **Kein USB-Hub und keine USB-Verlängerung dazwischen.** Beides ist eine häufige Ursache für Verbindungsabbrüche an seriellen Gateways.

---

## 2. Pflicht – Zigbee

| # | Artikel | Spezifikation | Menge | Preis (ca.) | Hinweis |
|---|---|---|---|---|---|
| 4 | **SMLIGHT SLZB-06M** (Empfehlung) *oder* SLZB-06 | Zigbee-Koordinator mit **Ethernet + PoE (802.3af)** | 1 | 40–60 € | 06M: Silabs EFR32MG21 → Z2M `adapter: ember`. 06: TI CC2652P → `adapter: zstack`. Beide funktionieren mit Zigbee2MQTT über TCP (Port 6638). |
| 5 | **PoE-Injektor 802.3af** (Gigabit reicht auch 10/100) | z.B. TP-Link TL-POE150S o.ä. | 1 | 15–25 € | Die vorhandenen Switches haben kein PoE. **Alternative:** Den SLZB-06 per USB-C-Netzteil (5 V, ≥ 1 A) versorgen. Dann entfällt der Injektor, es braucht aber eine Steckdose am Aufstellort. |
| 6 | **LAN-Patchkabel Cat6** | Länge je nach Aufstellort | 1–2 | 3–8 € | Zwei Kabel bei Nutzung des PoE-Injektors: Switch → Injektor → SLZB. |

**Aufstellort SLZB-06:** zentral im Haus, **nicht** im Metallverteiler und nicht direkt neben der FritzBox oder dem NAS (Abstand ≥ 1 m zu WLAN/USB-3-Geräten).

---

## 3. Pflicht – Werkzeug / Software

| # | Artikel | Hinweis |
|---|---|---|
| 7 | **Windows-PC oder -Laptop** | **PCT14** (Eltako, kostenlos) läuft nur unter Windows. Ein Leihgerät genügt. Windows in einer VM auf dem Mac ist wegen des USB-Seriell-Treibers (FTDI) auf ARM-Windows unsicher, ein echtes Windows-Gerät ist zuverlässiger. |
| 8 | **Eltako PCT14** | Kostenloser Download bei Eltako (QR-Code liegt dem FAM14 bei). |
| 9 | **eo_man** (EnOcean Device Manager) | Kostenlos (Python, GitHub grimmpp/enocean-device-manager). Läuft auch auf dem Mac. |

---

## 4. Optional – nur bei Bedarf

| # | Artikel | Wann nötig | Preis (ca.) |
|---|---|---|---|
| 10 | **Eltako FGW14-USB** + Bus-Querverbinder | Nur wenn HA durch den Bus-Traffic des FAM14 träge wird oder Telegramme verliert. Braucht 1 TE Platz auf der Hutschiene und den Einbau durch eine Elektrofachkraft. | Eltako-Preis prüfen |
| 11 | **Zigbee-Router** (z.B. Zigbee-Zwischenstecker) | Wenn in der Z2M-Netzwerkkarte Sensoren mit schwacher LQI auftauchen, etwa in der Garage oder im DG. | 10–20 € / Stück |
| 12 | **PioTek MGW LAN** (EnOcean LAN-Gateway) | Nur als Ausweichlösung, falls UGOS den FAM14 per USB nicht erkennt (Blocker-Check Phase 1.1). | Hersteller-Preis prüfen |

---

## 5. Nicht nötig

| Artikel | Warum nicht |
|---|---|
| Neue Eltako-Aktoren | FSR14, FSB14, FUD14 und F4HK14 bleiben unverändert. |
| Neue Raumfühler / Taster | Die FFT55B und die EnOcean-Taster werden weiterverwendet. |
| EnOcean-USB-Stick (USB300, FAM-USB) | Der FAM14 übernimmt die Rolle des Gateways. Nur nötig, falls später **dezentrale** Funkaktoren dazukommen. |
| Neue Zigbee-Geräte | Die vorhandenen Leuchtmittel und Sensoren werden neu gepairt. |

---

## Checkliste Einkauf

- [ ] USB-A → Mini-USB, geschirmt, Ferrit, passende Länge (Dauerverbindung FAM14 ↔ NAS)
- [ ] USB-A → Mini-USB, 1–2 m (Laptop / PCT14)
- [ ] SMLIGHT SLZB-06M (oder SLZB-06)
- [ ] PoE-Injektor 802.3af **oder** USB-C-Netzteil 5 V / ≥ 1 A
- [ ] Cat6-Patchkabel (1–2 Stück)
- [ ] Windows-Laptop organisiert
- [ ] *(optional)* Kabeldurchführung für die Verteilertür

**Pflicht-Summe grob: ca. 70–110 €**, ohne optionale Posten.
