# WireGuard Remote-Zugriff

Anleitung und Referenz für den Remote-Zugriff ins Heimnetz via WireGuard VPN.

---

## Architektur

WireGuard läuft als nativer Dienst auf der FritzBox 7530 AX. Es ist der **einzige** Weg, von außen auf das Heimnetz zuzugreifen.

```
Smartphone / Tablet (außerhalb)
    └── WireGuard-Tunnel (verschlüsselt)
            └── FritzBox 7530 AX (WireGuard-Server)
                    └── Heimnetz 192.168.188.0/24
                            ├── Home Assistant    :8123
                            ├── UGOS App          (Fotos)
                            ├── Portainer         :9444
                            ├── Paperless-NGX     :8000
                            ├── Jellyfin          :8096
                            └── alle anderen Services
```

Nach dem Verbindungsaufbau verhält sich das Gerät wie ein lokales Gerät im Heimnetz. Alle Services sind über ihre normalen lokalen URLs erreichbar.

---

## Einrichtung auf einem neuen Gerät

WireGuard-Clients werden direkt in der FritzBox verwaltet.

### Voraussetzungen

- WireGuard App auf dem Gerät installiert ([iOS](https://apps.apple.com/app/wireguard/id1441195209) / [Android](https://play.google.com/store/apps/details?id=com.wireguard.android))
- Zugang zur FritzBox-Oberfläche: http://192.168.188.1

### Schritte

1. FritzBox öffnen → http://192.168.188.1
2. **Internet → Freigaben → VPN (WireGuard)**
3. **Verbindung hinzufügen** → Gerätename vergeben (z.B. `iPhone-David`)
4. QR-Code anzeigen lassen
5. WireGuard App auf dem Gerät öffnen → **+** → **QR-Code scannen**
6. Verbindung in der App aktivieren
7. Test: beliebige Service-URL im Browser aufrufen (z.B. http://192.168.188.130:8123)

---

## Nutzung

### Aktive Use Cases

| Anwendung | Zugriff via WireGuard |
|---|---|
| Home Assistant App | http://192.168.188.130:8123 |
| UGOS App (Foto-Backup) | UGOS App – verbindet sich automatisch mit NAS |
| Alle anderen Services | Normale lokale URL im Browser |

### Verbindung aktivieren / deaktivieren

- WireGuard App öffnen → Tunnel antippen → ein- oder ausschalten
- Die Verbindung muss manuell aktiviert werden – kein Always-on VPN konfiguriert

---

## Voraussetzungen für den Betrieb

WireGuard funktioniert nur wenn folgende Bedingungen erfüllt sind:

| Bedingung | Warum |
|---|---|
| FritzBox läuft und hat Internetzugang | WireGuard-Server muss erreichbar sein |
| FritzBox hat eine erreichbare externe IP oder DynDNS | Client muss den Server finden |
| UGREEN NAS läuft | Services müssen verfügbar sein |
| AdGuard Home läuft | DNS-Auflösung im Heimnetz funktioniert |

> **Hinweis:** Ist AdGuard Home ausgefallen, schlägt im VPN-Tunnel die DNS-Auflösung fehl. Services sind dann nur noch per direkter IP:Port erreichbar, nicht über Hostnamen.

---

## Fehlersuche

**VPN verbindet sich nicht:**
- Hat das Gerät mobiles Internet oder ein anderes WLAN? (WireGuard braucht eine Internetverbindung)
- FritzBox läuft und hat Internetverbindung? → http://192.168.188.1 von zuhause prüfen
- WireGuard-Konfiguration auf dem Gerät korrekt? → In der FritzBox neuen QR-Code generieren und neu einrichten

**VPN verbunden, aber Services nicht erreichbar:**
- UGREEN NAS läuft? → Portainer unter https://192.168.188.130:9444 aufrufen
- AdGuard Home läuft? → Direkt per IP testen: http://192.168.188.130:8123

**VPN verbunden, aber kein Internet:**
- Prüfen ob der Tunnel nur Heimnetz-Traffic oder allen Traffic umleitet (Split Tunnel vs. Full Tunnel)
- FritzBox WireGuard ist standardmäßig als Split Tunnel konfiguriert – nur 192.168.188.0/24 geht durch den Tunnel, normaler Internet-Traffic läuft direkt

---

## Sicherheitshinweise

- **Kein Service direkt im Internet erreichbar:** Alle Ports sind geschlossen. WireGuard ist der einzige Eintrittspunkt.
- **WireGuard-Konfiguration vertraulich behandeln:** Die exportierten Konfigurationsdateien oder QR-Codes gewähren vollständigen Zugang zum Heimnetz – nicht weitergeben.
- **Gerät verloren oder gestohlen:** Sofort in der FritzBox den entsprechenden WireGuard-Client deaktivieren oder löschen (Internet → Freigaben → VPN (WireGuard) → Gerät entfernen).
- **Kein geteilter Tunnel-Schlüssel:** Jedes Gerät erhält eine eigene WireGuard-Konfiguration. So kann ein einzelnes Gerät gezielt gesperrt werden.

---

## Bekannte Schwächen

- **Abhängigkeit von FritzBox-Verfügbarkeit:** Fällt die FritzBox aus, ist kein Remote-Zugriff möglich – auch kein Neustart des NAS von außen.
- **Kein Always-on VPN:** Die Verbindung muss manuell aktiviert werden. Vergisst man das, laufen Apps wie Home Assistant ins Leere.
- **DynDNS nicht dokumentiert:** Falls die externe IP der FritzBox dynamisch ist, muss DynDNS konfiguriert sein damit WireGuard den Server findet. Aktueller Stand nicht dokumentiert – in FritzBox unter Internet → Freigaben → DynDNS prüfen.
