from __future__ import annotations

import json

import pytest
import requests

from app.jellyfin_client import JellyfinClient


@pytest.mark.parametrize("operation", ["scan", "delete", "exists", "refresh"])
def test_requests_use_mediabrowser_authorization(monkeypatch, operation):
    calls = []

    def request(method, url, **kwargs):
        prepared = requests.Request(
            method, url, headers=kwargs["headers"], params=kwargs.get("params")
        ).prepare()
        calls.append(prepared)
        response = requests.Response()
        response.status_code = 401
        if prepared.headers.get("Authorization") == 'MediaBrowser Token="test-api-key"':
            response.status_code = 204 if method == "DELETE" else 200
        response._content = json.dumps(
            {
                "Items": [{"Id": str(len(calls))}],
                "TotalRecordCount": 2,
            }
        ).encode()
        return response

    monkeypatch.setattr(requests, "request", request)
    client = JellyfinClient("https://jellyfin.example", "test-api-key")

    if operation == "scan":
        assert client.get_all_media_items(["Movie"]) == [{"Id": "1"}, {"Id": "2"}]
        assert len(calls) == 2
        assert all(call.method == "GET" for call in calls)
        assert "StartIndex=0" in calls[0].url
        assert "StartIndex=1" in calls[1].url
    elif operation == "delete":
        client.delete_item("duplicate-1")
        assert len(calls) == 1
        assert calls[0].method == "DELETE"
        assert calls[0].url.endswith("/Items/duplicate-1")

    elif operation == "exists":
        assert client.item_exists("item-1") is True
        assert len(calls) == 1
        assert calls[0].method == "GET"
        assert calls[0].url.endswith("/Items/item-1")
    else:
        client.refresh_library()
        assert len(calls) == 1
        assert calls[0].method == "POST"
        assert calls[0].url.endswith("/Library/Refresh")

    for call in calls:
        assert "X-Emby-Token" not in call.headers
        assert "test-api-key" not in call.url


def test_repeated_page_fails_instead_of_looping(monkeypatch):
    from app.jellyfin_client import JellyfinApiError

    calls = []

    def request(*args, **kwargs):
        calls.append(args)
        response = requests.Response()
        response.status_code = 200
        response._content = b'{"Items":[{"Id":"a"}],"TotalRecordCount":3}'
        return response

    monkeypatch.setattr(requests, "request", request)
    with pytest.raises(JellyfinApiError, match="repeated"):
        JellyfinClient("https://example.com", "key").get_all_media_items(["Movie"])
    assert len(calls) == 2


@pytest.mark.parametrize("body", [b"not json", b"[]", b'{"Items":[null]}', b'{"Items":{}}'])
def test_invalid_payload_is_reported(monkeypatch, body):
    from app.jellyfin_client import JellyfinApiError

    response = requests.Response()
    response.status_code = 200
    response._content = body
    monkeypatch.setattr(requests, "request", lambda *a, **kw: response)
    with pytest.raises(JellyfinApiError):
        JellyfinClient("https://example.com", "key").get_all_media_items(["Movie"])


@pytest.mark.parametrize("method,count", [("GET", 3), ("DELETE", 1), ("POST", 1)])
def test_only_reads_are_retried(monkeypatch, method, count):
    import app.jellyfin_client as module

    calls = []

    def request(*args, **kwargs):
        calls.append(args)
        response = requests.Response()
        response.status_code = 503
        response._content = b""
        response._content_consumed = True
        return response

    monkeypatch.setattr(requests, "request", request)
    monkeypatch.setattr(module.time, "sleep", lambda _: None)
    with pytest.raises(requests.HTTPError):
        JellyfinClient("https://example.com", "key")._request(
            method, "https://example.com", headers={}
        )
    assert len(calls) == count


def test_not_found_check_returns_false(monkeypatch):
    response = requests.Response()
    response.status_code = 404
    monkeypatch.setattr(requests, "request", lambda *a, **kw: response)
    assert not JellyfinClient("https://example.com", "key").item_exists("gone")


def test_scan_uses_supported_jellyfin_query_fields(monkeypatch):
    def request(method, url, **kwargs):
        params = kwargs["params"]
        assert set(params["Fields"].split(",")) == {
            "Path",
            "MediaSources",
            "MediaStreams",
            "SortName",
            "ProviderIds",
        }
        assert params["SortBy"] == "SortName,DateCreated"
        response = requests.Response()
        response.status_code = 200
        response._content = b'{"Items":[],"TotalRecordCount":0}'
        return response

    monkeypatch.setattr(requests, "request", request)
    assert JellyfinClient("https://example.com", "key").get_all_media_items(["Movie"]) == []


@pytest.mark.parametrize("body", [b"{}", b'{"Items":[],"TotalRecordCount":2}'])
def test_missing_or_incomplete_pages_are_reported(monkeypatch, body):
    from app.jellyfin_client import JellyfinApiError

    response = requests.Response()
    response.status_code = 200
    response._content = body
    monkeypatch.setattr(requests, "request", lambda *a, **kw: response)
    with pytest.raises(JellyfinApiError):
        JellyfinClient("https://example.com", "key").get_all_media_items(["Movie"])
