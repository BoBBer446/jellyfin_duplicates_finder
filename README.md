# Jellyfin Duplicate Finder (Webservice + Docker)

Dieses Projekt ist jetzt ein Docker-faehiger Webservice mit Web-Interface und API, um doppelte Filme (oder andere Jellyfin-Typen) zu finden und gezielt zu loeschen.

## Features

- Web-Interface unter `http://localhost:8000/`
- REST API mit `FastAPI`
- Scan direkt gegen Jellyfin (`base_url` + `api_key`)
- Unterstuetzung fuer `https://jellyfin.home` und selbstsignierte Zertifikate (`verify_ssl=false`)
- Container-Override fuer `jellyfin.home` ueber `.env` (`JELLYFIN_HOME_IP`, optional `JELLYFIN_HOME_PORT`)
- Scan via JSON-Datei-Upload (`multipart/form-data`)
- Duplikat-Logik mit:
  - Titel/Jahr-Normalisierung
  - stark erweiterte Sequenz-Erkennung (CD/DVD/Disc/Disk/BD/VCD/Part/PT/Teil/Vol, auch `01`, `CD-01`, `Part III`, `SIDE-A`)
  - Qualitaets-Ranking (behalte beste Datei nach Aufloesung + Groesse)
- Loeschen per API mit `dry_run`-Sicherheitsmodus
- Loeschung wird verifiziert (Item muss in Jellyfin wirklich verschwinden)
- Nach dem Loeschen wird die Scan-Session automatisch frisch mit Jellyfin synchronisiert
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

Optional fuer lokale Namensaufloesung von `jellyfin.home` im Container:

1. Trage die Jellyfin-IP in `.env` ein:

```bash
JELLYFIN_HOME_IP=192.168.1.194
# optional, falls nicht 443:
# JELLYFIN_HOME_PORT=8096
```

2. Danach neu starten:

```bash
docker compose down
docker compose up --build -d
```

Wenn `jellyfin.home` im Browser funktioniert, aber im Container nicht, ist die DNS-Aufloesung im Container meist anders als auf dem Host. Dann `JELLYFIN_HOME_IP` setzen und neu starten.

Service ist danach erreichbar unter:

- Web-UI: `http://localhost:8000`
- API Root: `http://localhost:8000`
- Healthcheck: `http://localhost:8000/health`
- Swagger UI: `http://localhost:8000/docs`

## Web-Interface Nutzung

1. Oeffne `http://localhost:8000`.
2. Trage Jellyfin URL und API Key ein.
   - Beispiel URL: `https://jellyfin.home`
3. Falls dein Jellyfin ein selbstsigniertes Zertifikat nutzt:
   - Checkbox `SSL-Zertifikat pruefen` deaktivieren
4. Waehle `Movie` (oder zusaetzlich `Series`) und klicke auf `Jellyfin scannen`.
5. Das Tool markiert alle Loeschkandidaten automatisch, die beste Datei pro Gruppe bleibt als `KEEP`.
6. Optional:
   - mit `Suche in Ergebnissen` filtern
   - mit `Alle markieren` / `Auswahl leeren` anpassen
   - mit `Dry Run` pruefen, was geloescht werden wuerde
7. Mit `Auswahl loeschen` werden nur die markierten Duplikate geloescht.

## API Nutzung

### 1) Direkt gegen Jellyfin scannen

```bash
curl -X POST "http://localhost:8000/api/v1/scans/jellyfin" \
  -H "Content-Type: application/json" \
  -d '{
    "base_url": "https://jellyfin.home",
    "api_key": "DEIN_API_KEY",
    "include_item_types": ["Movie"],
    "verify_ssl": false
  }'
```

## Troubleshooting (jellyfin.home)

Fehler:

```text
Network is unreachable
oder
Connection refused (z. B. auf 192.168.65.254)
```

Loesung:

1. Jellyfin-IP ermitteln (die IP, unter der dein Browser Jellyfin erreicht).
2. `.env` neben `docker-compose.yml` erstellen/aktualisieren:

```bash
JELLYFIN_HOME_IP=DEINE_JELLYFIN_IP
# optional bei anderem Port:
# JELLYFIN_HOME_PORT=8096
```

3. Container neu starten:

```bash
docker compose down
docker compose up --build -d
```

4. In der Web-UI:
   - URL: `https://jellyfin.home`
   - bei selbstsigniertem Zertifikat `SSL-Zertifikat pruefen` deaktivieren

Wenn deine Jellyfin-Instanz nur per HTTP auf Port 8096 laeuft, nutze stattdessen:

```text
http://192.168.1.194:8096
```

Wenn die UI nach `Auswahl loeschen` frueher "Geloescht" zeigte, aber beim naechsten Scan noch Duplikate da waren:

- Das Tool prueft jetzt aktiv, ob die geloeschte Item-ID wirklich weg ist.
- Falls nicht, wird es als Fehler gemeldet (z. B. fehlende Jellyfin-Rechte oder kein Dateisystem-Zugriff).

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
