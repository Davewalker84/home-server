# Neuen Service hinzufügen

Schritt-für-Schritt-Anleitung zum Aufsetzen eines neuen Docker-Dienstes auf dem UGREEN über Portainer.

---

## Vorüberlegung

Vor dem Aufsetzen eines neuen Dienstes folgende Fragen klären:

| Frage | Warum wichtig |
|---|---|
| Welchen Port benötigt der Dienst? | Konflikte mit bestehenden Services prüfen |
| Braucht der Dienst persistente Daten? | Volume-Pfad auf volume1 oder volume2 festlegen |
| Ist der Dienst kritisch oder experimentell? | Entscheidet ob Dokumentation vor Go-Live nötig |
| Hat der Dienst externe Abhängigkeiten? | Z.B. andere Container, Netzwerkzugang |

### Belegte Ports (Stand aktuell)

| Port | Dienst |
|---|---|
| 53 | AdGuard Home (DNS) |
| 8000 | Paperless-NGX |
| 8080 | AdGuard Home (Web-UI) |
| 8096 | Jellyfin |
| 8123 | Home Assistant |
| 9443 | UGOS Web-UI |
| 9444 | Portainer |

---

## Schritt 1 – Stack-Datei vorbereiten

Neue Dienste werden immer als **Portainer Stack** angelegt, auch wenn nur ein Container läuft.

Beispiel `docker-compose.yml` als Vorlage:

```yaml
version: "3.8"

services:
  dienstname:
    image: image/name:version        # immer konkrete Version, kein :latest
    container_name: dienstname
    restart: unless-stopped
    ports:
      - "HOSTPORT:CONTAINERPORT"
    volumes:
      - /volume2/docker/dienstname:/config          # Laufzeitdaten → SSD
      - /volume1/dienstname-data:/data              # Nutzdaten → HDD RAID5
    environment:
      - TZ=Europe/Berlin
```

**Konventionen:**

- **Kein `:latest`** – immer eine konkrete Image-Version eintragen. So ist nachvollziehbar welche Version läuft und Updates sind bewusste Entscheidungen.
- **`restart: unless-stopped`** – Dienst startet automatisch nach NAS-Neustart, außer er wurde manuell gestoppt.
- **Timezone** – immer `TZ=Europe/Berlin` setzen, sonst stimmen Logs und Zeitpläne nicht.
- **Volumes explizit** – keine anonymen Docker Volumes. Pfade immer auf NAS-Verzeichnisse mappen.

---

## Schritt 2 – Volume-Verzeichnisse anlegen

Vor dem ersten Start des Containers die Verzeichnisse auf dem NAS anlegen:

```
/volume2/docker/dienstname/     ← Container-Konfiguration und Laufzeitdaten (SSD)
/volume1/dienstname-data/       ← Nutzdaten, falls vorhanden (HDD RAID5)
```

Dies kann über die UGOS Dateimanager-Oberfläche oder per SSH erfolgen.

---

## Schritt 3 – Stack in Portainer anlegen

1. Portainer öffnen → https://192.168.188.130:9444
2. Linkes Menü → **Stacks** → **+ Add stack**
3. Name eingeben (Kleinbuchstaben, Unterstriche: z.B. `neuer_dienst`)
4. **Web editor** wählen → docker-compose Inhalt einfügen
5. **Deploy the stack** klicken

Portainer zieht das Image und startet den Container. Status im Dashboard prüfen: Container muss auf **running** wechseln.

---

## Schritt 4 – Service testen

1. Im Browser die Service-URL aufrufen: `http://192.168.188.130:PORT`
2. Logs in Portainer prüfen: Container → Logs
3. Falls der Container direkt abstürzt: Logs lesen, häufige Ursachen:
   - Volume-Verzeichnis existiert nicht → Schritt 2 wiederholen
   - Port bereits belegt → anderen Port wählen
   - Fehlende Umgebungsvariablen → docker-compose prüfen

---

## Schritt 5 – Dokumentieren

Bevor der neue Dienst als "fertig" gilt:

- [ ] Eintrag in der Port-Tabelle in dieser Datei ergänzen
- [ ] Quick Reference Tabelle im [README](../README.md) ergänzen
- [ ] Neue Datei unter `services/dienstname.md` anlegen (nach dem Schema der anderen Service-Dokumente)
- [ ] docker-compose Definition aus Portainer kopieren und in `services/dienstname.md` einfügen
- [ ] Änderungen ins Git-Repo committen

---

## Checkliste Neuer Service

```
[ ] Port-Konflikt geprüft
[ ] docker-compose mit konkreter Image-Version erstellt
[ ] Volume-Verzeichnisse auf NAS angelegt
[ ] Stack in Portainer deployed
[ ] Service im Browser getestet
[ ] Logs geprüft, keine Fehler
[ ] README aktualisiert
[ ] Service-Dokument angelegt
[ ] Git-Repo aktualisiert
```

---

## Dienst wieder entfernen

1. Portainer → Stacks → Stack auswählen → **Delete this stack**
2. Volumes auf dem NAS manuell löschen (Portainer löscht keine Host-Volumes):
   - `/volume2/docker/dienstname/` löschen
   - `/volume1/dienstname-data/` löschen (falls vorhanden)
3. Port-Tabelle und README aktualisieren
4. Service-Dokument aus `services/` entfernen
5. Git-Repo committen
