
# Jellyfin Duplikate Finder

Dieses Skript durchsucht deine Jellyfin Medienbibliothek nach Duplikaten von Filmen oder Serien und gibt die gefundenen Duplikate aus. Optional bietet es die Möglichkeit, alle gefundenen Duplikate (außer der jeweils größten Datei) zu löschen.

## Funktionen

- Durchsucht die Jellyfin Medienbibliothek nach Duplikaten basierend auf dem Titel.
- Zeigt die gefundenen Duplikate mit ID, Pfad, Größe und Auflösung an.
- Optionales Löschen aller Duplikate außer der Datei mit der größten Dateigröße.

## Voraussetzungen

- Python 3
- `requests` Bibliothek in Python (kann über `pip install requests` installiert werden)
- Zugriff auf einen Jellyfin Server und einen gültigen API-Schlüssel

## Einrichtung

Um das Skript zu verwenden, muss zunächst sichergestellt werden, dass Python 3 und die `requests` Bibliothek installiert sind.

Das Skript erfordert die Angabe der Basis-URL deines Jellyfin-Servers sowie eines gültigen API-Schlüssels. Diese Informationen müssen im Skript eingetragen werden:

```python
base_url = "http://dein_jellyfin_server:8096"
api_key = "dein_api_schlüssel"
```

Ersetze `http://dein_jellyfin_server:8096` mit der URL deines Jellyfin-Servers und `dein_api_schlüssel` mit deinem tatsächlichen API-Schlüssel.

## Benutzung

1. Starte das Skript in einem Terminal oder einer Kommandozeile:

    ```bash
    python3 jellyfin_duplicates_finder.py
    ```

2. Folge den Anweisungen im Skript. Du wirst aufgefordert, den Typ der Medien einzugeben, nach denen gesucht werden soll (Movie/Series).

3. Das Skript zeigt alle gefundenen Duplikate an. Wenn Duplikate gefunden wurden, kannst du wählen, ob du alle Duplikate (außer dem größten) löschen möchtest.

## Wichtige Hinweise

- Stelle sicher, dass du die richtige Basis-URL und den richtigen API-Schlüssel für deinen Jellyfin-Server verwendest.
- Das Löschen von Dateien kann nicht rückgängig gemacht werden. Sei daher vorsichtig beim Bestätigen der Löschung.
- Das Skript arbeitet rekursiv durch alle angegebenen Medientypen und kann bei großen Bibliotheken einige Zeit in Anspruch nehmen.

## Lizenz

Dieses Skript ist unter MIT lizenziert.
