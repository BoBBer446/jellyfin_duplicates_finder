from __future__ import annotations

import ipaddress
import socket
from typing import Any
from urllib.parse import urlsplit, urlunsplit

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

    def _request(self, method: str, url: str, **kwargs: Any) -> requests.Response:
        try:
            response = requests.request(
                method,
                url,
                timeout=self.timeout,
                verify=self.verify_ssl,
                **kwargs,
            )
            response.raise_for_status()
            return response
        except requests.RequestException as exc:
            response = self._retry_with_ipv4_if_needed(method, url, exc, **kwargs)
            if response is not None:
                return response
            raise

    def _retry_with_ipv4_if_needed(
        self,
        method: str,
        url: str,
        original_error: requests.RequestException,
        **kwargs: Any,
    ) -> requests.Response | None:
        if "Network is unreachable" not in str(original_error):
            return None

        parsed = urlsplit(url)
        hostname = parsed.hostname
        if not hostname:
            return None

        try:
            ipaddress.ip_address(hostname)
            return None
        except ValueError:
            pass

        port = parsed.port or (443 if parsed.scheme == "https" else 80)
        try:
            infos = socket.getaddrinfo(hostname, port, socket.AF_INET, socket.SOCK_STREAM)
        except OSError:
            return None
        if not infos:
            return None

        ipv4 = infos[0][4][0]
        if parsed.port is None and (
            (parsed.scheme == "https" and port == 443)
            or (parsed.scheme == "http" and port == 80)
        ):
            netloc = ipv4
            host_header = hostname
        else:
            netloc = f"{ipv4}:{port}"
            host_header = f"{hostname}:{port}"

        fallback_url = urlunsplit((parsed.scheme, netloc, parsed.path, parsed.query, parsed.fragment))
        headers = dict(kwargs.pop("headers", {}) or {})
        headers.setdefault("Host", host_header)

        response = requests.request(
            method,
            fallback_url,
            headers=headers,
            timeout=self.timeout,
            verify=self.verify_ssl,
            **kwargs,
        )
        response.raise_for_status()
        return response

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
                response = self._request(
                    "GET",
                    url,
                    headers=self.headers,
                    params=params,
                )
            except requests.RequestException as exc:
                raise JellyfinApiError(
                    "Jellyfin scan failed: "
                    f"{exc}. If you use docker + local DNS, set JELLYFIN_HOME_IP in .env."
                ) from exc

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
            response = self._request("DELETE", url, headers=self.headers)
            if response.status_code not in (200, 202, 204):
                raise JellyfinApiError(
                    f"Delete for item '{item_id}' failed with status {response.status_code}"
                )
        except requests.RequestException as exc:
            raise JellyfinApiError(f"Delete request failed for '{item_id}': {exc}") from exc
