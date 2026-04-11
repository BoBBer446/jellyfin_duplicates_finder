from __future__ import annotations

import ipaddress
import os
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

        rewritten_url = urlunsplit((parsed.scheme, netloc, parsed.path, parsed.query, parsed.fragment))
        return rewritten_url, next_kwargs

    def _request(self, method: str, url: str, **kwargs: Any) -> requests.Response:
        request_url, request_kwargs = self._apply_jellyfin_home_override(url, kwargs)
        try:
            response = requests.request(
                method,
                request_url,
                timeout=self.timeout,
                verify=self.verify_ssl,
                **request_kwargs,
            )
            response.raise_for_status()
            return response
        except requests.RequestException as exc:
            response = self._retry_with_ipv4_if_needed(method, request_url, exc, **request_kwargs)
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
                    f"{exc}. "
                    "If jellyfin.home fails in docker, set JELLYFIN_HOME_IP in .env "
                    "(for example JELLYFIN_HOME_IP=192.168.1.194) and restart compose."
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
