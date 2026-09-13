# Änderungen

## 2.1.0 · 13. September 2026

- Jellyfin-Authentifizierung auf den MediaBrowser-Authorization-Header umgestellt (Issue #1).
- Metadatenvergleich mit Provider-IDs, Unicode-Titeln, Episodenidentität, Fassungen und Laufzeitprüfung.
- Gemeinsames Vergleichsmerkmal pro Gruppe; widersprüchliche IDs und unsichere Dateiverknüpfungen ausgeschlossen.
- Löschprüfung gegen aktuelle IDs und Pfade, Schutz der zu behaltenden Datei und Sperre paralleler Löschvorgänge pro Scan.
- Begrenzte Wiederholungen für Leseanfragen, kontrollierte Paginierung und begrenzte Uploads und Sitzungen.
- Neue responsive Oberfläche mit Treffergründen, Filter, Sortierung, Speicherangaben und JSON-Export.
- Manuelle Kandidatenauswahl und Bestätigung vor tatsächlichen Löschungen.
- Container ohne Root-Rechte, Healthcheck und feste Python-Abhängigkeiten.

## 2.0.0

Webservice mit FastAPI, Docker, CLI und Löschprüfung über Jellyfin.
