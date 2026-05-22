# Jellyfin

Lokaler Medienserver für Filme, Serien und Musik.

---

## Grunddaten

| | |
|---|---|
| URL | http://192.168.188.130:8096 |
| Betrieb | Portainer Stack `jellyfin` |
| Host | UGREEN DXP4800 |

---

## Medienbibliothek

| Kategorie | Pfad auf NAS | Volume |
|---|---|---|
| Filme & Serien | `/volume1/Filme` | HDD RAID5 |
| Musik | `/volume1/Music` | HDD RAID5 |

Beide Bibliotheken liegen auf volume1 (HDD RAID5) und sind damit durch RAID5 gegen einzelne Festplattenausfälle geschützt sowie im wöchentlichen Rsync-Backup auf der Synology enthalten.

---

## Zugriff

| Zugriff | Verfügbar |
|---|---|
| Heimnetz (LAN / WLAN) | ✅ direkt über http://192.168.188.130:8096 |
| Remote (außerhalb) | ✅ via WireGuard VPN → dann lokale URL |
| Direkter Internet-Zugriff | ❌ nicht konfiguriert |

Jellyfin ist ausschließlich lokal erreichbar. Remote-Zugriff erfolgt wie bei allen anderen Services über WireGuard VPN auf der FritzBox.

---

## Hardware-Beschleunigung (Transcoding)

Der Intel N100 unterstützt Hardware-Transcoding via **Intel Quick Sync**. Ob dies in der Jellyfin-Konfiguration aktiv ist, sollte unter Einstellungen → Wiedergabe → Transkodierung geprüft werden.

> **Empfehlung:** Hardware-Transcoding aktivieren falls noch nicht geschehen – reduziert CPU-Last beim gleichzeitigen Streaming deutlich, besonders bei 4K-Inhalten.

---

## Wartung & Updates

**Container-Update über Portainer:**
1. Portainer öffnen → https://192.168.188.130:9444
2. Stacks → `jellyfin` → Image aktualisieren → Stack neu deployen

Jellyfin-Updates sind in der Regel unkritisch. Die Mediendaten auf volume1 werden nicht berührt – nur die Jellyfin-Datenbank (Metadaten, Cover, Wiedergabefortschritt) liegt im Container-Volume auf volume2.

---

## Bekannte Schwächen

- **Metadaten nicht in RAID:** Die Jellyfin-Datenbank (Metadaten, Wiedergabefortschritt, Cover) liegt im Container-Volume auf volume2 (SSD, kein RAID). Bei SSD-Ausfall müssen Metadaten neu gescannt werden – die Mediendateien selbst auf volume1 sind nicht betroffen.
- **Kein Hardware-Transcoding verifiziert:** Quick Sync ist auf dem N100 verfügbar, aber nicht dokumentiert ob es aktiv ist.
