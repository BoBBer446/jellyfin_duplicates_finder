from __future__ import annotations

from typing import Any

import requests
import urllib3


class JellyfinApiError(RuntimeError):
    """Raised when Jellyfin cannot be reached or returns an error."""


class JellyfinClient:
    def __init__(self, base_url: str, api_key: str, timeout: int = 30, verify_ssl: bool = True):
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.verify_ssl = verify_ssl
        self.headers = {"X-Emby-Token": api_key}
        if not self.verify_ssl:
            urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

    def get_all_media_items(self, include_item_types: list[str]) -> list[dict[str, Any]]:
        include_types = ",".join(include_item_types)
        url = f"{self.base_url}/Items"
        limit = 200
        start_index = 0
        all_items: list[dict[str, Any]] = []

        while True:
            params = {
                "IncludeItemTypes": include_types,
                "Recursive": "true",
                "Fields": "Path,MediaSources,SortName,ProductionYear",
                "Limit": str(limit),
                "StartIndex": str(start_index),
            }

            try:
                response = requests.get(
                    url,
                    headers=self.headers,
                    params=params,
                    timeout=self.timeout,
                    verify=self.verify_ssl,
                )
                response.raise_for_status()
            except requests.RequestException as exc:
                raise JellyfinApiError(f"Jellyfin scan failed: {exc}") from exc

            payload = response.json()
            page_items = payload.get("Items", [])
            if not isinstance(page_items, list):
                raise JellyfinApiError("Unexpected Jellyfin response format: 'Items' is not a list")

            all_items.extend(page_items)
            total_record_count = payload.get("TotalRecordCount")
            if not page_items:
                break
            if isinstance(total_record_count, int) and len(all_items) >= total_record_count:
                break

            start_index += len(page_items)

        return all_items

    def delete_item(self, item_id: str) -> None:
        url = f"{self.base_url}/Items/{item_id}"
        try:
            response = requests.delete(
                url,
                headers=self.headers,
                timeout=self.timeout,
                verify=self.verify_ssl,
            )
            if response.status_code not in (200, 202, 204):
                raise JellyfinApiError(
                    f"Delete for item '{item_id}' failed with status {response.status_code}"
                )
        except requests.RequestException as exc:
            raise JellyfinApiError(f"Delete request failed for '{item_id}': {exc}") from exc
