# Jellyfin Duplicate Finder

Version 2.1.1 · Weboberfläche, REST-API und CLI zum Vergleichen von Filmen und Episoden.

Der Finder schlägt Duplikate anhand von Jellyfin-Metadaten vor. Er berechnet keine Datei-Hashes
und kann fehlende oder falsche Metadaten nicht zuverlässig ausgleichen. Die vorgeschlagene
Datei zum Behalten wird nach Auflösung, danach Dateigröße ausgewählt. Prüfe Fassungen,
Tonspuren und Untertitel vor dem Löschen selbst.

## Start mit Docker

```bash
git clone https://github.com/BoBBer446/jellyfin_duplicates_finder.git
cd jellyfin_duplicates_finder
docker compose up --build -d
```

Die Oberfläche liegt unter `http://localhost:8000`, die API-Dokumentation unter `/docs`.
`/health` meldet Status und Version. Das Image verwendet feste Abhängigkeiten aus
`requirements.lock`, läuft ohne Root-Rechte und besitzt einen Healthcheck.

Für Zugriff im eigenen LAN eine `.env` neben der Compose-Datei anlegen:

```dotenv
BIND_ADDRESS=192.168.1.194
PORT=8098
```

Standard ist `127.0.0.1:8000`. Der Dienst besitzt keine eigene Benutzeranmeldung und gehört
in ein vertrauenswürdiges Netzwerk oder hinter einen authentifizierenden Reverse Proxy.
Es werden keine Medienverzeichnisse in den Container eingebunden; Löschungen erfolgen über Jellyfin.

## Bedienung

1. Jellyfin-URL und API-Schlüssel eingeben. Filme und/oder Episoden auswählen.
2. Bibliothek scannen oder einen JSON-Export mit bis zu 50 MiB hochladen.
3. Treffergrund, Dateipfade, Auflösung und geschätzten Speichergewinn prüfen.
4. Gewünschte Kandidaten markieren. „Sichtbare markieren“ berücksichtigt nur die dargestellten Treffer.
5. Mit „Auswahl testen“ die aktuelle Bibliothek erneut prüfen, ohne Dateien zu löschen.
6. „Auswahl löschen“ verlangt eine Bestätigung und prüft danach, ob die Einträge verschwunden sind.

Datei-Scans können nicht löschen. Der JSON-Ergebnisexport enthält keine API-Schlüssel.
Scan-Sitzungen liegen im Arbeitsspeicher: maximal 100 Sitzungen, zwei Stunden Gültigkeit.
Ein Neustart verwirft sie. Laufende Löschvorgänge werden nicht durch die Bereinigung verdrängt.

## Erkennung

- TMDb-, IMDb- und TVDb-IDs erlauben Treffer bei übersetzten Titeln; widersprüchliche IDs verhindern die Gruppierung.
- Ohne gemeinsame ID müssen Titel und Erscheinungsjahr übereinstimmen. Jede Gruppe benötigt ein gemeinsames Vergleichsmerkmal.
- Episoden benötigen Serien-ID, Staffel, eine positive Episodennummer und passenden Titel. Die Dateinummerierung muss die Metadaten zusätzlich stützen (`S01E01`, `1x01`, `OVA1`, `Folge 56`). Widersprüchliche Nummern verhindern Treffer auch bei gleicher Provider-ID.
- `E00`-Sammelnummern und Episoden unter `Plex Versions` werden ausgeschlossen. Regulär nummerierte Specials wie `S00E01` bleiben vergleichbar.
- Abweichende Episodentitel werden konservativ getrennt, auch wenn es sich um Übersetzungen handeln könnte. Ohne Nummerierung im Dateinamen werden Episoden nicht vorgeschlagen. Episodentreffer bleiben manuell zu prüfende Kandidaten, keine bestätigte Inhaltsgleichheit.
- Fassungsmarker, explizite Editionen und Teil-Marker wie CD1/CD2 werden berücksichtigt.
- Bei bekannten Laufzeiten verhindert eine Differenz über dem größeren Wert aus 120 Sekunden und 3 % der kürzeren Laufzeit die Gruppierung.
- Ordner, mehrere Medienquellen, fehlende Pfade, unzureichende Metadaten und gemeinsam referenzierte Pfade werden konservativ ausgeschlossen.

Gleiche Pfadangaben werden erkannt. Hardlinks oder Symlinks mit verschiedenen Pfaden lassen sich
über diese Metadaten nicht verlässlich erkennen. Der Speichergewinn ist daher eine Schätzung.
Eigene Teil-Marker ergänzen die eingebauten Regeln; maximal 100 Marker mit jeweils 64 Zeichen.

## Jellyfin-Verbindung

Der Client verwendet `Authorization: MediaBrowser Token="…"` für Jellyfin 12 und ältere
Server, die diesen Header unterstützen. Temporäre Fehler bei GET-Anfragen werden höchstens
zweimal wiederholt; DELETE und POST werden nicht automatisch wiederholt. Ungültige Antworten
und wiederholte Seiten führen zu einer Fehlermeldung statt zu unvollständigen Ergebnissen.

Falls `jellyfin.home` im Container nicht auflösbar ist, kann `.env` die folgenden Werte enthalten:

```dotenv
JELLYFIN_HOME_IP=192.168.1.194
JELLYFIN_HOME_PORT=8096
```

Bei HTTP auf Port 8096 ist alternativ die direkte Server-IP möglich. Die TLS-Prüfung ist
standardmäßig aktiv und kann für eigene selbstsignierte Zertifikate in der Oberfläche abgeschaltet werden.

## API und CLI

```bash
curl -X POST http://localhost:8000/api/v1/scans/jellyfin \
  -H 'Content-Type: application/json' \
  -d '{"base_url":"http://jellyfin.home:8096","api_key":"DEIN_KEY","include_item_types":["Movie","Episode"]}'

python jellyfin_duplicates_finder.py \
  --base-url http://jellyfin.home:8096 --api-key DEIN_KEY --types Movie --json
```

`POST /api/v1/scans/file` erwartet einen Multipart-Dateiupload namens `file` mit einem
JSON-Array oder `{"Items":[...]}`. `GET /api/v1/scans/{scan_id}` liefert Ergebnisse.
`POST /api/v1/scans/{scan_id}/delete` akzeptiert `{"dry_run":true,"item_ids":["ID"]}`.
Ohne `item_ids` sind alle Kandidaten betroffen; `dry_run` ist standardmäßig aktiv.
Vor dem Löschen werden Kandidaten, zu behaltende Einträge und Pfade erneut geprüft.
Veränderte Ergebnisse und parallele Löschvorgänge derselben Sitzung liefern HTTP 409.

## Entwicklung unter Linux / WSL

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements-dev.txt
.venv/bin/python -m pytest -q
.venv/bin/ruff check app tests
.venv/bin/ruff format --check app tests
.venv/bin/uvicorn app.main:app --host 127.0.0.1 --port 18000
```

Optionaler Browsertest, während der lokale Server läuft:

```bash
.venv/bin/pip install playwright
.venv/bin/python -m playwright install chromium
.venv/bin/python tests/browser_smoke.py
```

Die Browserprüfung nutzt Testdaten und simulierte Jellyfin-Löschantworten. Sie löscht keine Medien.
Für Updates des Containers nach einem Git-Pull erneut `docker compose up --build -d` ausführen.
