# AdGuard Home

Netzwerkweiter DNS-Server mit Werbeblockierung. Primärer DNS für alle Geräte im Heimnetz.

---

## Grunddaten

| | |
|---|---|
| URL | http://192.168.188.130:8080 |
| Betrieb | Portainer Stack `ad_guard_home` |
| Host | UGREEN DXP4800 |
| DNS-Port | 53 |

---

## Funktion im Netzwerk

AdGuard Home ist der **einzige DNS-Server** im Heimnetz. Die FritzBox ist so konfiguriert, dass sie `192.168.188.130` als DNS-Server an alle DHCP-Clients ausliefert. Alle DNS-Anfragen laufen damit über AdGuard Home.

```
Gerät im Heimnetz
    └── DNS-Anfrage (Port 53)
            └── AdGuard Home (192.168.188.130)
                    ├── Blockliste → blockiert (Werbung, Tracker)
                    └── Upstream-DNS → Internet-Antwort
```

### Eingebundene Funktionen

| Funktion | Status |
|---|---|
| Werbe- und Tracker-Blockierung | aktiv |
| DNS-Logging (alle Anfragen) | aktiv |
| Lokale DNS-Einträge | nicht konfiguriert |
| Upstream-DNS | Standardkonfiguration |

> **Lokale DNS-Einträge** wären möglich – z.B. `homeassistant.local → 192.168.188.130` statt IP:Port-Eingabe. Aktuell nicht genutzt, alle Services werden direkt über IP:Port aufgerufen.

---

## Kritikalität

AdGuard Home ist ein **kritischer Dienst**. Fällt der Container aus, schlägt die DNS-Auflösung für alle Geräte im Netz fehl – Internet ist faktisch nicht mehr nutzbar, auch wenn die FritzBox und das LAN einwandfrei funktionieren.

**Aktueller Stand:** Kein Fallback-DNS in der FritzBox konfiguriert.

> **Empfehlung ⚠️:** In der FritzBox einen sekundären DNS-Server als Fallback eintragen (z.B. `1.1.1.1` von Cloudflare). Dieser greift automatisch wenn AdGuard Home nicht erreichbar ist und verhindert einen kompletten DNS-Ausfall.
>
> FritzBox → Internet → DNS-Rebind-Schutz → Heimnetz → Weitere DNS-Server: `1.1.1.1`

---

## Wartung & Updates

**Container-Update über Portainer:**
1. Portainer öffnen → https://192.168.188.130:9444
2. Stacks → `ad_guard_home` → Image aktualisieren → Stack neu deployen

**Beim Neustart zu beachten:**
- AdGuard Home benötigt wenige Sekunden zum Starten
- In dieser Zeit schlagen alle DNS-Anfragen im Netz fehl
- Updates daher zu Nebenzeiten durchführen (z.B. nachts)
- Nach dem Neustart: DNS-Auflösung auf einem Gerät testen (`ping 1.1.1.1` vs. `ping google.com`)

---

## Fehlersuche

**DNS funktioniert nicht (alle Geräte betroffen):**
1. AdGuard Home Container-Status in Portainer prüfen → läuft er?
2. Falls Container gestoppt: neu starten
3. Falls Container läuft aber DNS nicht antwortet: Container neu starten
4. Temporärer Workaround: DNS auf einem Gerät manuell auf `1.1.1.1` setzen

**Eine bestimmte Website wird blockiert:**
1. AdGuard Home öffnen → http://192.168.188.130:8080
2. Protokoll → betroffene Domain suchen
3. Domain in der Filterliste suchen und ggf. als Ausnahme eintragen

---

## Bekannte Schwächen

- **Kein Fallback-DNS ⚠️:** Fällt AdGuard Home aus, ist das gesamte Heimnetz ohne DNS. Ein Fallback in der FritzBox ist noch nicht konfiguriert.
- **Single Point of Failure:** Läuft als einzelner Container ohne Redundanz. Ein Container-Absturz reicht für einen netzwerkweiten DNS-Ausfall.
- **Upstream-DNS nicht dokumentiert:** Die aktuell verwendeten Upstream-DNS-Server sind nicht bekannt und sollten in AdGuard Home unter Einstellungen → DNS-Einstellungen geprüft und dokumentiert werden.
