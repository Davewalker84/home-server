# Backup-Strategie

Dokumentation der aktuellen Backup-Lösung, Schwächen und Empfehlungen.

---

## Übersicht

| | |
|---|---|
| Backup-Ziel | Synology DS218J (192.168.188.135) |
| Methode | Rsync (UGOS integriert) |
| Zeitplan | Wöchentlich, Montag, ~1 Stunde |
| Umfang | Vollständig (alle Volumes) |
| Betrieb Synology | Nur während Backup aktiv, danach automatisch aus |

---

## Synology DS218J

| | |
|---|---|
| Modell | Synology DS218J |
| IP | 192.168.188.135 |
| DSM | http://192.168.188.135:5000 |
| Anschluss | LAN via Switch |
| Betrieb | Wöchentlich für ~1 Stunde, dann automatisch aus |

Die Synology ist ausschließlich als Backup-Empfänger im Einsatz. Sie läuft nicht 24/7 – UGOS startet sie per Wake-on-LAN zum Backup-Zeitpunkt und fährt sie danach wieder herunter. Das spart Strom und reduziert Verschleiß.

---

## Was wird gesichert

Der Rsync-Job sichert alle Daten vom UGREEN vollständig auf die Synology:

| Quelle (UGREEN) | Inhalt |
|---|---|
| volume1 | Filme, Musik, Fotos, paperless-data |
| volume2 | Docker-Containerdaten, Paperless-Stack |

Die Macs sichern sich zusätzlich regelmäßig per **Time Machine** auf das UGREEN. Die Time-Machine-Freigabe liegt damit auch im wöchentlichen Rsync auf die Synology.

| Quelle (Time Machine → UGREEN) | Inhalt |
|---|---|
| Mac Mini M4 (192.168.188.151) | macOS, Home-Ordner inkl. `~/docker/` (Compose-Datei, `.env`, SearXNG- und mcpo-Config), Ollama-Modelle – **Docker-Volumes nur eingeschränkt**, siehe [Bekannte Schwächen](#bekannte-schwächen) |
| MacBook Pro | macOS, Home-Ordner |

---

## Backup-Zeitplan

```
Montag
    └── UGOS startet Synology (Wake-on-LAN)
            └── Rsync: UGREEN → Synology (~1 Stunde)
                    └── Synology fährt automatisch herunter
```

Maximaler Datenverlust bei einem Ausfall direkt vor dem nächsten Backup: **7 Tage**.

---

## Was das Backup schützt gegen

| Szenario | Geschützt? |
|---|---|
| Einzelne HDD in UGREEN fällt aus | ✅ RAID5 fängt das ab – kein Backup nötig |
| Kompletter UGREEN-Ausfall | ✅ Synology hat letzten Stand (max. 7 Tage alt) |
| Versehentlich gelöschte Datei | ✅ solange Backup neuer als Löschzeitpunkt |
| Ransomware / Dateikorruption | ⚠️ nur wenn Synology beim Angriff offline war |
| Hausbrand / Diebstahl beider Geräte | ❌ kein Schutz – beide Geräte im selben Raum |
| Gleichzeitiger Ausfall von 2+ HDDs | ❌ RAID5 schützt nur gegen eine HDD |

---

## Bekannte Schwächen

**Kein Cloud-Backup ⚠️**
Die Synology ist das einzige Backup-Ziel. Bei gleichzeitigem Verlust beider NAS (Hausbrand, Einbruch, Wasserschaden) gibt es keinen weiteren Restore-Pfad. Besonders kritisch für das Paperless-Dokumentenarchiv – dort liegen unwiederbringliche Originaldokumente.

**Wöchentlicher Rhythmus**
Bis zu 7 Tage Datenverlust möglich. Für Medien (Filme, Musik) akzeptabel. Für aktiv genutzte Daten (Paperless, HA-Konfiguration) ist das ein relevantes Risiko.

**Keine Test-Restores dokumentiert**
Ein Backup ist nur so gut wie sein letzter erfolgreicher Restore-Test. Bisher wurde kein Test-Restore durchgeführt und dokumentiert.

**Portainer Stack-Definitionen nicht gesichert**
Die docker-compose-Definitionen der Portainer-Stacks existieren nur in der Portainer-Datenbank auf volume2. Sie werden zwar mit volume2 gesichert, aber nicht separat als lesbare Dateien im Git-Repo versioniert.

**Docker-Volumes auf dem Mac Mini (OrbStack) – Risiko akzeptiert**
OrbStack legt alle Docker-Volumes in einer einzigen virtuellen Festplatte ab (`~/.orbstack/data/data.img`, bis 8 TB). Time Machine sichert diese Datei zwar, laut OrbStack schlägt die Wiederherstellung solcher Images aber oft fehl ([Issue #2046](https://github.com/orbstack/orbstack/issues/2046), [FAQ](https://orbstack.dev/docs/faq)). Betroffen ist vor allem das Volume `open-webui-data`: Chatverläufe, Benutzerkonten, Modelle, Tools und Valves (API-Keys).
Das Risiko ist **bewusst akzeptiert**, weil sich der AI-Stack vollständig aus dem Repo wieder aufbauen lässt (siehe [Restore Mac Mini](#restore-mac-mini--ai-stack)). Verloren gingen nur Chatverläufe und Konten; die API-Keys lassen sich in den jeweiligen Dashboards neu erzeugen. Bind-Mounts im Home-Ordner (`~/docker/searxng`, `~/docker/mcpo`, `.env`) sind normale Dateien und werden von Time Machine zuverlässig gesichert.

---

## Empfehlungen

| Priorität | Maßnahme |
|---|---|
| Hoch | Cloud-Backup für Paperless-Archiv einrichten (z.B. Backblaze B2 via Rclone, verschlüsselt) |
| Hoch | Test-Restore durchführen und Ergebnis dokumentieren |
| Mittel | Portainer Stack-Definitionen exportieren und ins Git-Repo einchecken |
| Mittel | Backup-Frequenz für kritische Daten erhöhen (z.B. täglich für paperless-data) |
| Niedrig | Backup-Benachrichtigung einrichten (E-Mail oder HA-Notification bei Fehler) |

---

## Restore-Vorgehen (dokumentiert)

Im Falle eines vollständigen UGREEN-Ausfalls:

1. Neuen UGREEN (oder Ersatzgerät) aufsetzen
2. UGOS installieren und Netzwerkzugang sicherstellen
3. Synology starten → http://192.168.188.135:5000
4. Rsync in umgekehrter Richtung: Synology → neuer UGREEN
5. Docker-Dienste neu starten:
   - UGOS Docker: Paperless-NGX Stack starten
   - Portainer starten
   - In Portainer: alle Stacks neu deployen (Stack-Definitionen aus Git oder Portainer-Backup)
6. IP-Reservierung in FritzBox prüfen (MAC-Adresse neues Gerät → 192.168.188.130)
7. Alle Services testen (DNS, HA, Paperless, Jellyfin)

> **Hinweis:** Ohne exportierte Portainer Stack-Definitionen müssen alle Stacks manuell neu konfiguriert werden. Das ist der stärkste Grund, Stack-Definitionen im Git-Repo zu versionieren.

### Restore Mac Mini / AI-Stack

1. Mac Mini aus Time Machine wiederherstellen (oder neu aufsetzen). Ollama und LaunchAgent laut [Hardware/mac-mini-m4.md](../Hardware/mac-mini-m4.md).
2. OrbStack installieren. Falls `open-webui-data` nicht wiederherstellbar ist, mit leerem Volume starten.
3. `~/docker/ai-stack/docker-compose.yml`, `.env`, `~/docker/searxng/settings.yml` und `~/docker/mcpo/config.json` aus Time Machine zurückholen oder laut [ContainerStack/Readme/ai-stack.md](../ContainerStack/Readme/ai-stack.md) und [HolidayAgent/README.md](../HolidayAgent/README.md) neu anlegen → `docker compose up -d`.
4. Bei leerem Volume in Open WebUI neu einrichten: Admin-Konto, Websuche, Paperless-Tool (ai-stack.md) sowie Urlaubsplaner-Schritte 2–6 (Claude-Verbindung, Tool + Valves, Modell, Familien-Accounts) laut [HolidayAgent/README.md](../HolidayAgent/README.md).
