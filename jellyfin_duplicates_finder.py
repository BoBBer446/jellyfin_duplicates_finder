import requests
from collections import defaultdict
import re

# Konfigurierbare Variablen
BASE_URL = "http://192.168.178.36:8096"  # Ersetze mit der Jellyfin-Server-URL
API_KEY = "5344bee7b5114eb6b07606996e0026e4"      # Ersetze mit dem Jellyfin-API-Schlüssel
# Sequenzen um Kollektionen zu identifizieren und auszufiltern
CUSTOM_SEQUENCES = ["CD1", "CD2", "DVD1", "DVD2", "Part1", "Part2", "Teil1", "Teil2"]  # Eigene Sequenzkennzeichnungen

class JellyfinAPIClient:
    """
    Ein Client für die Interaktion mit der Jellyfin API.
    """
    def __init__(self, base_url, api_key):
        self.base_url = base_url
        self.headers = {'X-Emby-Token': api_key}

    def get_all_media_items(self, item_type="Movie"):
        """
        Ruft alle Medienelemente eines bestimmten Typs ab.
        """
        url = f"{self.base_url}/Items?IncludeItemTypes={item_type}&Recursive=true&fields=Path,MediaSources,SortName,ProductionYear"
        response = requests.get(url, headers=self.headers)
        return response.json()

    def delete_media_item(self, item_id):
        """
        Löscht ein Medienelement anhand seiner ID.
        """
        url = f"{self.base_url}/Items/{item_id}"
        response = requests.delete(url, headers=self.headers)
        return response.status_code == 204

def get_normalized_name(item):
    """
    Normalisiert den Namen eines Medienelements, indem es das Jahr entfernt.
    """
    name = item['SortName']
    year = item.get('ProductionYear')
    if year:
        name = re.sub(rf'\s*\({year}\)\s*$', '', name).strip()
    return name

def get_unique_identifier(item):
    """
    Erstellt einen einzigartigen Identifikator aus dem Namen und dem Produktionsjahr.
    """
    name = get_normalized_name(item)
    year = item.get('ProductionYear', 'Unbekanntes Jahr')
    return f"{name} ({year})"

def get_sequence_identifier(path):
    """
    Sucht nach Hinweisen auf eine Sequenz oder einen Teil eines Werkes im Dateinamen.
    Nutzt benutzerdefinierte Sequenzen aus der CUSTOM_SEQUENCES-Liste.
    """
    for seq in CUSTOM_SEQUENCES:
        pattern = rf'{seq}'
        match = re.search(pattern, path, re.IGNORECASE)
        if match:
            return match.group(0)
    return None

def find_duplicates(client, item_type="Movie"):
    """
    Sucht nach Duplikaten in der Medienbibliothek basierend auf dem Titel und dem Jahr.
    Beachtet benutzerdefinierte Sequenzkennzeichnungen, um keine falschen Duplikate zu identifizieren.
    """
    items = client.get_all_media_items(item_type=item_type)
    duplicates = defaultdict(list)
    unique_items = {}

    for item in items['Items']:
        path = item.get('Path', 'Unbekannter Pfad')
        unique_identifier = get_unique_identifier(item)
        sequence_identifier = get_sequence_identifier(path)

        # Wenn ein Sequenz-Identifikator gefunden wird, füge diesen dem eindeutigen Identifikator hinzu
        unique_key = unique_identifier
        if sequence_identifier:
            unique_key += f" - {sequence_identifier}"

        item_details = {
            'Id': item['Id'],
            'Name': item['Name'],
            'Path': path,
            'Size': sum([ms.get('Size', 0) for ms in item.get('MediaSources', [])]),
            'Resolution': next((stream.get('Width', 0) * stream.get('Height', 0) for ms in item.get('MediaSources', []) for stream in ms.get('MediaStreams', []) if stream.get('Type') == 'Video'), 0),
            'Year': item.get('ProductionYear', 'Unbekanntes Jahr')
        }

        # Wenn der einzigartige Schlüssel bereits vorhanden ist, handelt es sich um ein Duplikat
        if unique_key in unique_items and unique_items[unique_key]['Name'] == item_details['Name']:
            duplicates[unique_identifier].append(item_details)
        else:
            unique_items[unique_key] = item_details

    return duplicates

def main():
    """
    Hauptfunktion, die beim Ausführen des Skripts aufgerufen wird.
    Lässt den Benutzer den Typ der zu suchenden Medien auswählen und führt dann die Duplikatssuche durch.
    Bietet dem Benutzer die Möglichkeit, Duplikate zu löschen.
    """
    client = JellyfinAPIClient(BASE_URL, API_KEY)
    selection = input("Suche nach Duplikaten in:\n1. Movie\n2. Series\n3. Alles\nAuswahl: ")
    item_type_map = {"1": "Movie", "2": "Series", "3": "Movie,Series"}
    item_type = item_type_map.get(selection, "Movie")

    print(f"Suche nach Duplikaten in: {item_type}")
    duplicates = find_duplicates(client, item_type=item_type)
    all_duplicates = {}

    if duplicates:
        all_duplicates.update(duplicates)
    else:
        print("Keine Duplikate gefunden.")

    if all_duplicates:
        for identifier, items in all_duplicates.items():
            print(f"Duplikat gefunden: {identifier}")
            for item in items:
                print(f"  ID: {item['Id']} - Path: {item['Path']} - Size: {item['Size']} Bytes - Resolution: {item['Resolution']} - Year: {item['Year']}")

        if input("Möchtest du alle Duplikate (außer dem größten) löschen? (y/n): ").lower() == 'y':
            if input("Bist du sicher? Dies kann nicht rückgängig gemacht werden! (y/n): ").lower() == 'y':
                for items in all_duplicates.values():
                    for item in items[1:]:
                        if client.delete_media_item(item['Id']):
                            print(f"  Gelöscht: {item['Id']}")
                        else:
                            print(f"Fehler beim Löschen: {item['Id']}")

if __name__ == "__main__":
    main()
