# Änderungen

## 2.1.1 · 13. September 2026

- Fehlzuordnungen bei Halo-OVAs, unterschiedlichen absoluten Yakari-Folgennummern und E00-Extras verhindert.
- Episoden benötigen zusätzliche Dateinummerierung und konsistente Titel; Jellyfin-Nummern allein reichen nicht mehr.
- Plex-Optimierungen von Episoden werden nicht als Löschkandidaten vorgeschlagen.
- Episodentreffer nicht mehr pauschal als starke Metadaten-Treffer eingestuft.
- Regressionstests anhand der gemeldeten Muster und Schutz gegen das Löschen alter Fehlkandidaten ergänzt.

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
