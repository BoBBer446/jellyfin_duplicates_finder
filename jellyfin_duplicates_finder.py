import requests
from collections import defaultdict

class JellyfinAPIClient:
    def __init__(self, base_url, api_key):
        self.base_url = base_url
        self.headers = {'X-Emby-Token': api_key}

    def get_all_media_items(self, item_type="Movie"):
        # Aktualisierte URL, um 'fields=Path,MediaSources' einzuschließen
        url = f"{self.base_url}/Items?IncludeItemTypes={item_type}&Recursive=true&fields=Path,MediaSources"
        response = requests.get(url, headers=self.headers)
        return response.json()

    def delete_media_item(self, item_id):
        url = f"{self.base_url}/Items/{item_id}"
        response = requests.delete(url, headers=self.headers)
        return response.status_code == 204

def find_duplicates(client, item_type="Movie"):
    items = client.get_all_media_items(item_type=item_type)
    duplicates = defaultdict(list)

    for item in items['Items']:
        # Direkter Zugriff auf 'Path' und 'MediaSources' für jedes Item
        path = item.get('Path', 'Unbekannter Pfad')
        size = sum([ms.get('Size', 0) for ms in item.get('MediaSources', [])])
        resolution = 0
        for ms in item.get('MediaSources', []):
            for stream in ms.get('MediaStreams', []):
                if stream.get('Type') == 'Video':
                    resolution = stream.get('Width', 0) * stream.get('Height', 0)
                    break

        item_details = {
            'Id': item['Id'],
            'Name': item['Name'],
            'Path': path,
            'Size': size,
            'Resolution': resolution
        }
        duplicates[item['Name']].append(item_details)

    # Sortiere die Duplikate nach Größe und Auflösung (größere zuerst)
    for name in duplicates:
        duplicates[name].sort(key=lambda x: (x['Size'], x['Resolution']), reverse=True)

    return {name: items for name, items in duplicates.items() if len(items) > 1}

def main():
    base_url = "http://url:port"
    api_key = "DEIN-API-KEY"  # Achte darauf, deinen tatsächlichen API-Schlüssel hier einzufügen
    client = JellyfinAPIClient(base_url, api_key)
    item_type = input("Suche nach Duplikaten in (Movie/Series): ").capitalize()

    if item_type not in ["Movie", "Series"]:
        print("Ungültige Auswahl. Bitte wähle 'Movie' oder 'Series'.")
        return

    print(f"Suche nach Duplikaten in: {item_type}")
    duplicates = find_duplicates(client, item_type=item_type)
    all_duplicates = {}

    if duplicates:
        all_duplicates.update(duplicates)
    else:
        print("Keine Duplikate gefunden.")

    if all_duplicates:
        for name, items in all_duplicates.items():
            print(f"Duplikat gefunden: {name}")
            for item in items:
                print(f"  ID: {item['Id']} - Path: {item['Path']} - Size: {item['Size']} Bytes - Resolution: {item['Resolution']}")

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
