# Netzwerk

Dokumentation der physischen und logischen Netzwerkinfrastruktur.

---

## Übersicht

| Gerät | Modell | IP | Funktion |
|---|---|---|---|
| Router | FritzBox 7530 AX | 192.168.188.1 | Router, DHCP, DNS-Relay, WireGuard |
| Switch 1 | 8-Port unmanaged | — | LAN-Verteilung EG / OG |
| Switch 2 | 8-Port unmanaged | — | LAN-Verteilung EG / OG |

---

## FritzBox 7530 AX

**Weboberfläche:** http://192.168.188.1

Die FritzBox ist der zentrale Netzwerkknoten. Sie übernimmt:

- **DSL-Einwahl** via PPPoE (Internetzugang)
- **DHCP-Server** für das gesamte Heimnetz (`192.168.188.0/24`)
- **DNS-Relay** → leitet alle Anfragen an AdGuard Home weiter (`192.168.188.130`)
- **WireGuard-Server** für Remote-Zugriff von außen
- **WLAN-Accesspoint** (Haupt-AP)

### DHCP-Reservierungen

Geräte mit fester IP werden über MAC-Adressen-Reservierung im FritzBox-DHCP verwaltet – keine statischen IPs auf den Geräten selbst.

| Gerät | IP |
|---|---|
| UGREEN DXP4800 | 192.168.188.130 |
| Synology DS218J | 192.168.188.135 |

### DNS-Konfiguration

Die FritzBox ist so konfiguriert, dass sie **AdGuard Home** (`192.168.188.130`) als einzigen DNS-Server an alle DHCP-Clients ausliefert. Die FritzBox selbst leitet ihre eigenen DNS-Anfragen ebenfalls an AdGuard Home weiter.

```
Gerät im Netz
    └── DNS-Anfrage → 192.168.188.130 (AdGuard Home)
                          └── Upstream-DNS → Internet
```

---

## WireGuard (Remote-Zugriff)

WireGuard läuft als nativer FritzBox-Dienst. Es ist der **einzige Weg**, von außen auf das Heimnetz zuzugreifen. Kein Service ist direkt aus dem Internet erreichbar.

### Funktionsweise

```
Smartphone (außerhalb)
    └── WireGuard-Tunnel → FritzBox (WireGuard-Server)
                               └── Heimnetz 192.168.188.0/24
                                       ├── Home Assistant :8123
                                       ├── UGOS App (Fotos)
                                       └── alle anderen Services
```

Nach dem Verbindungsaufbau verhält sich das Smartphone wie ein lokales Gerät – alle Services sind über ihre normalen lokalen URLs erreichbar.

### Nutzung

- **HA App** (Home Assistant) unterwegs
- **UGOS App** für Foto-Backup von unterwegs

> Ein früher betriebener WireGuard-Docker-Container in Portainer wurde abgelöst und entfernt. Der FritzBox-native WireGuard benötigt keinen extra Container.

---

## Switches

Zwei 8-Port-Switches (unmanaged) verteilen das LAN im Haus. Da sie unmanaged sind, gibt es keine VLAN-Konfiguration – alle Geräte befinden sich im gleichen Broadcast-Domain.

### Angeschlossene Geräte

| Gerät | Anmerkung |
|---|---|
| UGREEN DXP4800 | Hauptserver |
| Synology DS218J | Backup-NAS |
| LAN-Dosen (alle Räume) | Wanddosen für kabelgebundene Geräte |
| Buderus Lüftungsanlage | Gebäudetechnik |
| Repeater Garage | WLAN-Versorgung Garage → Eufy E340 Kamera |
| Smart Meter Gateway (EMH) | HAN-Schnittstelle, IPv6-only, kein DHCP/IPv4 |

> Der **Wibutler Pro** ist direkt an der FritzBox angeschlossen, nicht über die Switches.

### Bekannte Schwächen

- **Keine VLANs ⚠️:** IoT-Geräte (Buderus, Wallbox, Wibutler) befinden sich im selben Netz wie Server und Clients. Eine Kompromittierung eines IoT-Geräts hätte direkten Zugriff auf alle anderen Geräte. Akzeptiertes Risiko bei aktuellem Aufwand.
- **Keine redundante Uplink-Verkabelung:** Fällt ein Switch aus, sind alle daran hängenden Geräte offline.

### Smart Meter Gateway – IPv6-Sonderfall

Das EMH SMGW (NetzeBW HAN) nutzt ausschließlich IPv6 und erhält vom FritzBox-DHCP keine IPv4-Adresse. Im Heimnetz und im Browser ist es über den Hostnamen `eemh0015438871` erreichbar. Home Assistant läuft jedoch in einem Docker-Container, der den Hostnamen nicht über AdGuard Home / FritzBox auflösen kann.

**Workaround:** Die IPv6-Adresse `2003:de:9f37:1c00:215:3bff:fee4:1f5c` wird direkt in `smgw_sensor.yaml` als Endpunkt eingetragen.

---

## AdGuard Home

**Weboberfläche:** http://192.168.188.130:8080

AdGuard Home läuft als Portainer Stack auf dem UGREEN und ist der **primäre DNS-Server** für alle Geräte im Heimnetz.

### Funktion

- Netzwerkweite Werbeblockierung (DNS-basiert, ohne Browsererweiterungen)
- DNS-Logging für alle Anfragen im Netz (hilfreich zur Fehlersuche)
- Upstream-DNS: Standardkonfiguration

### Abhängigkeit

AdGuard Home ist ein **kritischer Dienst**: Fällt der Container aus, schlägt die DNS-Auflösung für alle Geräte im Netz fehl und das Internet ist faktisch nicht mehr nutzbar. Die FritzBox hat keinen Fallback-DNS konfiguriert.

> **Empfehlung:** In der FritzBox einen sekundären DNS-Server (z.B. `1.1.1.1`) als Fallback eintragen, der greift wenn AdGuard Home nicht erreichbar ist.
