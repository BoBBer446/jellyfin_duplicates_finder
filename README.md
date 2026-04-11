# Jellyfin Duplicate Finder (Webservice + Docker)

Dieses Projekt ist jetzt ein Docker-faehiger Webservice mit Web-Interface und API, um doppelte Filme (oder andere Jellyfin-Typen) zu finden und gezielt zu loeschen.

## Features

- Web-Interface unter `http://localhost:8000/`
- REST API mit `FastAPI`
- Scan direkt gegen Jellyfin (`base_url` + `api_key`)
- Scan via JSON-Datei-Upload (`multipart/form-data`)
- Duplikat-Logik mit:
  - Titel/Jahr-Normalisierung
  - Sequenz-Erkennung (`CD1`, `Part1`, `Teil1`, ...)
  - Qualitaets-Ranking (behalte beste Datei nach Aufloesung + Groesse)
- Loeschen per API mit `dry_run`-Sicherheitsmodus
- Docker und Docker Compose Support

## Projektstruktur

```text
app/
  main.py               # FastAPI Endpunkte
  jellyfin_client.py    # Jellyfin API Zugriff
  duplicate_finder.py   # Duplikat-Logik
  static/index.html     # Web-Interface
  store.py              # In-Memory Scan Sessions
  models.py             # Request/Response Modelle
Dockerfile
docker-compose.yml
requirements.txt
jellyfin_duplicates_finder.py   # Optionales CLI Tool
```

## Schnellstart mit Docker

```bash
docker compose up --build -d
```

Service ist danach erreichbar unter:

- Web-UI: `http://localhost:8000`
- API Root: `http://localhost:8000`
- Healthcheck: `http://localhost:8000/health`
- Swagger UI: `http://localhost:8000/docs`

## Web-Interface Nutzung

1. Oeffne `http://localhost:8000`.
2. Trage Jellyfin URL und API Key ein.
3. Waehle `Movie` (oder zusaetzlich `Series`) und klicke auf `Jellyfin scannen`.
4. Das Tool markiert alle Loeschkandidaten automatisch, die beste Datei pro Gruppe bleibt als `KEEP`.
5. Optional:
   - mit `Suche in Ergebnissen` filtern
   - mit `Alle markieren` / `Auswahl leeren` anpassen
   - mit `Dry Run` pruefen, was geloescht werden wuerde
6. Mit `Auswahl loeschen` werden nur die markierten Duplikate geloescht.

## API Nutzung

### 1) Direkt gegen Jellyfin scannen

```bash
curl -X POST "http://localhost:8000/api/v1/scans/jellyfin" \
  -H "Content-Type: application/json" \
  -d '{
    "base_url": "http://DEIN-JELLYFIN:8096",
    "api_key": "DEIN_API_KEY",
    "include_item_types": ["Movie"],
    "custom_sequences": ["CD1","CD2","Part1","Part2"]
  }'
```

Antwort enthaelt unter anderem:

- `scan_id`
- `summary`
- `groups` (inkl. `keep_item_id` und `delete_candidates`)

### 2) JSON-Datei hochladen und daraus Duplikate berechnen

Die Datei kann entweder:

- ein Jellyfin-Items-Objekt sein: `{"Items":[...]}`
- oder direkt ein Array: `[...]`

```bash
curl -X POST "http://localhost:8000/api/v1/scans/file" \
  -F "file=@items.json" \
  -F "custom_sequences=CD1,CD2,Part1,Part2"
```

Hinweis: Loeschen ist nur fuer Scans moeglich, die direkt gegen Jellyfin erstellt wurden, da nur dort gueltige API-Credentials vorhanden sind.

### 3) Ergebnis eines Scans abrufen

```bash
curl "http://localhost:8000/api/v1/scans/<SCAN_ID>"
```

### 4) Loeschen testen (`dry_run`)

```bash
curl -X POST "http://localhost:8000/api/v1/scans/<SCAN_ID>/delete" \
  -H "Content-Type: application/json" \
  -d '{
    "dry_run": true
  }'
```

### 5) Duplikate wirklich loeschen

```bash
curl -X POST "http://localhost:8000/api/v1/scans/<SCAN_ID>/delete" \
  -H "Content-Type: application/json" \
  -d '{
    "dry_run": false
  }'
```

Optional nur bestimmte IDs loeschen:

```json
{
  "dry_run": false,
  "item_ids": ["ID1", "ID2"]
}
```

## Lokaler Start ohne Docker

```bash
pip install -r requirements.txt
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

## Optional: CLI Nutzung

```bash
python jellyfin_duplicates_finder.py \
  --base-url "http://DEIN-JELLYFIN:8096" \
  --api-key "DEIN_API_KEY" \
  --types "Movie" \
  --json
```

## Repo aktualisieren, committen, pushen

Wenn dein lokales Verzeichnis noch **kein** Git-Repo ist, zuerst klonen:

```bash
git clone https://github.com/BoBBer446/jellyfin_duplicates_finder.git
cd jellyfin_duplicates_finder
```

Dann deine Aenderungen ins Repo uebernehmen und pushen:

```bash
git add .
git commit -m "feat: convert duplicate finder to dockerized web API"
git push origin main
```

Wenn du auf einem Feature-Branch arbeiten willst:

```bash
git checkout -b codex/webservice-api
git add .
git commit -m "feat: add fastapi service, duplicate scan API and docker setup"
git push -u origin codex/webservice-api
```
