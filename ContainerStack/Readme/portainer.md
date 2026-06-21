# Portainer

Container-Management-Oberfläche für alle neueren Docker-Dienste auf dem UGREEN.

---

## Grunddaten

| | |
|---|---|
| URL | https://192.168.188.130:9444 |
| Betrieb | UGOS Docker (direkt, nicht selbst in Portainer) |
| Host | UGREEN DXP4800 |

---

## Rolle im Setup

Portainer ist die zentrale Verwaltungsoberfläche für alle Container, die nicht direkt über UGOS Docker laufen. Es verwaltet zwei Kategorien:

| Kategorie | Inhalt |
|---|---|
| **Stacks** | Dienste mit mehreren Containern oder komplexer Konfiguration (docker-compose) |
| **Einzelne Container** | Einfache Dienste ohne Stack-Kontext |

Portainer selbst läuft als Container unter **UGOS Docker** – nicht unter Portainer. Ein Portainer-Absturz lässt alle verwalteten Container weiterlaufen, nur die Verwaltungsoberfläche ist nicht mehr erreichbar.

---

## Verwaltete Stacks

| Stack-Name | Enthält | Zweck |
|---|---|---|
| `homeassistant` | Home Assistant | Smarthome-Zentrale |
| `matter-server` | matter-server | Matter-Protokoll-Bridge |
| `ad_guard_home` | AdGuard Home | DNS & Werbeblockierung |
| `jellyfin` | Jellyfin | Medienserver |
| `wyoming` | wyoming-faster-whisper, wyoming-piper | Spracherkennung (Test) |

## Verwaltete Einzelcontainer

| Container | Zweck |
|---|---|
| `eufy-security-ws` | Lokale Eufy-Kamera-Anbindung |
| `go2rtc` | Kamera-Stream-Relay für Home Assistant |

---

## Nicht in Portainer verwaltet

Folgende Container laufen unter UGOS Docker direkt und erscheinen in Portainer als eingeschränkt verwaltbar:

| Stack / Container | Grund |
|---|---|
| `paperless-ngx` (inkl. postgres, redis, gotenberg, tika) | Vor Portainer aufgesetzt, läuft stabil unter UGOS Docker |

> Portainer zeigt den Paperless-Stack mit dem Hinweis *"This stack was created outside of Portainer. Control over this stack is limited."* Das ist kein Fehler – Kontrolle erfolgt über UGOS Docker.

---

## Konventionen

Damit das Setup nachvollziehbar bleibt, gelten folgende Konventionen für neue Dienste:

1. **Neue Dienste immer als Portainer Stack** anlegen, nicht als Einzelcontainer – auch wenn nur ein Container läuft. Stacks haben eine docker-compose-Definition, die dokumentiert ist.
2. **Stack-Namen in Kleinbuchstaben mit Unterstrich** (z.B. `ad_guard_home`, nicht `AdGuardHome`).
3. **Volumes immer explizit auf NAS-Pfade mappen** – keine anonymen Docker Volumes. Pfade auf volume1 für Nutzdaten, volume2 für Container-Laufzeitdaten.
4. **Keine Container direkt aus dem Internet erreichbar** – alle Services ausschließlich im LAN, Zugriff von außen nur via WireGuard.

---

## Typische Aufgaben

### Stack neu deployen (Update)

1. Portainer → Stacks → gewünschten Stack auswählen
2. Editor öffnen → Image-Version anpassen (falls nötig)
3. *Update the stack* → Portainer zieht das neue Image und startet neu

### Container-Logs prüfen

1. Portainer → Container → gewünschten Container auswählen
2. *Logs* → Ausgabe live verfolgen oder durchsuchen

### Container neu starten

1. Portainer → Container → gewünschten Container auswählen
2. *Restart*

### Neuen Stack anlegen

→ Siehe [guides/neuen-service-hinzufuegen.md](../guides/neuen-service-hinzufuegen.md)

---

## Bekannte Schwächen

- **Stack-Definitionen nicht im Git ⚠️:** Die docker-compose-Definitionen der Stacks existieren nur in Portainer selbst. Bei einem vollständigen NAS-Ausfall oder Portainer-Datenverlust müssten alle Stacks manuell neu erstellt werden. Empfehlung: Stack-Definitionen regelmäßig aus Portainer exportieren und ins Git-Repo einchecken.
- **Portainer-Daten auf volume2 (kein RAID):** Die Portainer-Datenbank (Stack-Definitionen, Benutzer, Settings) liegt auf der SSD ohne RAID. Bei SSD-Ausfall sind alle Stack-Konfigurationen verloren.
- **Kein Portainer-Backup-Mechanismus konfiguriert:** Portainer bietet einen eingebauten Backup-Export – dieser ist noch nicht eingerichtet.
