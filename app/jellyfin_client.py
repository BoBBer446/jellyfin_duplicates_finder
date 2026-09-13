from __future__ import annotations

import ipaddress
import logging
import os
import time
from typing import Any
from urllib.parse import urlsplit, urlunsplit

import requests
import urllib3

logger = logging.getLogger("jellydup.client")


class JellyfinApiError(RuntimeError):
    """Raised when Jellyfin cannot be reached or returns an error."""


class JellyfinClient:
    def __init__(self, base_url: str, api_key: str, timeout: int = 30, verify_ssl: bool = True):
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.verify_ssl = verify_ssl
        self.headers = {"Authorization": f'MediaBrowser Token="{api_key}"'}
        if not self.verify_ssl:
            urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

    def _apply_jellyfin_home_override(
        self,
        url: str,
        kwargs: dict[str, Any],
    ) -> tuple[str, dict[str, Any]]:
        parsed = urlsplit(url)
        hostname = (parsed.hostname or "").lower()
        if hostname != "jellyfin.home":
            return url, kwargs

        override_ip = os.getenv("JELLYFIN_HOME_IP", "").strip()
        override_port_raw = os.getenv("JELLYFIN_HOME_PORT", "").strip()
        if not override_ip:
            return url, kwargs

        try:
            ipaddress.ip_address(override_ip)
        except ValueError:
            return url, kwargs

        default_port = 443 if parsed.scheme == "https" else 80
        source_port = parsed.port or default_port
        target_port = source_port
        if override_port_raw:
            try:
                target_port = int(override_port_raw)
            except ValueError:
                target_port = source_port

        if target_port == default_port and parsed.port is None:
            netloc = override_ip
        else:
            netloc = f"{override_ip}:{target_port}"

        host_header = "jellyfin.home"
        if parsed.port is not None:
            host_header = f"{host_header}:{parsed.port}"

        next_kwargs = dict(kwargs)
        headers = dict(next_kwargs.get("headers", {}) or {})
        headers.setdefault("Host", host_header)
        next_kwargs["headers"] = headers

        rewritten_url = urlunsplit(
            (parsed.scheme, netloc, parsed.path, parsed.query, parsed.fragment)
        )
        return rewritten_url, next_kwargs

    def _request(
        self, method: str, url: str, allow_not_found: bool = False, **kwargs: Any
    ) -> requests.Response:
        request_url, request_kwargs = self._apply_jellyfin_home_override(url, kwargs)
        attempts = 3 if method == "GET" else 1
        for attempt in range(attempts):
            try:
                response = requests.request(
                    method,
                    request_url,
                    timeout=self.timeout,
                    verify=self.verify_ssl,
                    **request_kwargs,
                )
                logger.debug("Jellyfin %s %s -> %s", method, request_url, response.status_code)
                if response.status_code == 404 and allow_not_found:
                    return response
                if response.status_code in (429, 502, 503, 504) and attempt + 1 < attempts:
                    retry_after = response.headers.get("Retry-After", "")
                    delay = (
                        min(float(retry_after), 5) if retry_after.isdigit() else 0.5 * (2**attempt)
                    )
                    response.close()
                    time.sleep(delay)
                    continue
                response.raise_for_status()
                return response
            except (requests.ConnectionError, requests.Timeout):
                if attempt + 1 == attempts:
                    raise
                time.sleep(0.5 * (2**attempt))
        raise JellyfinApiError("Jellyfin request did not complete")

    def get_all_media_items(self, include_item_types: list[str]) -> list[dict[str, Any]]:
        include_types = ",".join(include_item_types)
        url = f"{self.base_url}/Items"
        limit = 200
        start_index = 0
        all_items: list[dict[str, Any]] = []
        seen_ids: set[str] = set()

        while True:
            params = {
                "IncludeItemTypes": include_types,
                "Recursive": "true",
                "Fields": "Path,MediaSources,MediaStreams,SortName,ProviderIds",
                "SortBy": "SortName,DateCreated",
                "SortOrder": "Ascending",
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
                    f"{exc}. "
                    "If jellyfin.home fails in docker, set JELLYFIN_HOME_IP in .env "
                    "(for example JELLYFIN_HOME_IP=192.168.1.194) and restart compose."
                ) from exc

            try:
                payload = response.json()
            except ValueError as exc:
                raise JellyfinApiError("Jellyfin returned invalid JSON") from exc
            if not isinstance(payload, dict):
                raise JellyfinApiError("Jellyfin returned an invalid item page")
            page_items = payload.get("Items")
            if not isinstance(page_items, list):
                raise JellyfinApiError("Unexpected Jellyfin response format: 'Items' is not a list")

            if any(not isinstance(item, dict) or not item.get("Id") for item in page_items):
                raise JellyfinApiError("Jellyfin returned items without valid IDs")
            new_items = [item for item in page_items if str(item["Id"]) not in seen_ids]
            if page_items and not new_items:
                raise JellyfinApiError("Jellyfin pagination repeated a page; scan stopped")
            for item in new_items:
                if str(item["Id"]) not in seen_ids:
                    seen_ids.add(str(item["Id"]))
                    all_items.append(item)
            if start_index + len(page_items) > 1_000_000:
                raise JellyfinApiError("Scan exceeds the limit of one million items")
            total_record_count = payload.get("TotalRecordCount")
            if not page_items:
                if isinstance(total_record_count, int) and len(all_items) < total_record_count:
                    raise JellyfinApiError(
                        "Jellyfin returned an incomplete scan; run the scan again"
                    )
                break
            if isinstance(total_record_count, int) and len(all_items) >= total_record_count:
                break

            start_index += len(page_items)

        return all_items

    def delete_item(self, item_id: str) -> None:
        url = f"{self.base_url}/Items/{item_id}"
        try:
            response = self._request("DELETE", url, headers=self.headers)
            logger.info(
                "Delete request sent for item %s -> HTTP %s",
                item_id,
                response.status_code,
            )
            if response.status_code not in (200, 202, 204):
                raise JellyfinApiError(
                    f"Delete for item '{item_id}' failed with status {response.status_code}"
                )
        except requests.RequestException as exc:
            raise JellyfinApiError(f"Delete request failed for '{item_id}': {exc}") from exc

    def item_exists(self, item_id: str) -> bool:
        url = f"{self.base_url}/Items/{item_id}"
        try:
            response = self._request("GET", url, headers=self.headers, allow_not_found=True)
        except requests.RequestException as exc:
            raise JellyfinApiError(f"Item existence check failed for '{item_id}': {exc}") from exc

        if response.status_code == 404:
            return False
        if response.status_code >= 400:
            raise JellyfinApiError(
                f"Item existence check failed for '{item_id}' with status {response.status_code}"
            )
        return True

    def wait_until_item_removed(
        self, item_id: str, attempts: int = 4, delay_seconds: float = 0.5
    ) -> bool:
        for _ in range(attempts):
            if not self.item_exists(item_id):
                return True
            time.sleep(delay_seconds)
        return False

    def refresh_library(self) -> None:
        url = f"{self.base_url}/Library/Refresh"
        try:
            response = self._request("POST", url, headers=self.headers)
            logger.info("Triggered Jellyfin library refresh -> HTTP %s", response.status_code)
        except requests.RequestException as exc:
            raise JellyfinApiError(f"Library refresh request failed: {exc}") from exc
