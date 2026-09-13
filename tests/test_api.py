import json

import pytest
from fastapi.testclient import TestClient

from app import main
from app.duplicate_finder import find_duplicate_groups
from app.jellyfin_client import JellyfinApiError
from app.store import ScanStore


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setattr(main, "scan_store", ScanStore())
    return TestClient(main.app)


def test_health_version_and_static_files(client):
    assert client.get("/health").json() == {"status": "ok", "version": "2.1.0"}
    assert client.get("/static/app.js").status_code == 200
    assert "Duplicate Finder" in client.get("/").text


@pytest.mark.parametrize("data", [[None], ["bad"], {"Items": [1]}])
def test_malformed_upload_returns_400(client, data):
    assert (
        client.post("/api/v1/scans/file", files={"file": ("a.json", json.dumps(data))}).status_code
        == 400
    )


def test_upload_and_export_do_not_expose_credentials(client):
    payload = [
        {"Id": i, "Name": "Film X", "Path": "/" + i + ".mkv", "ProductionYear": 2020}
        for i in ["a", "b"]
    ]
    result = client.post("/api/v1/scans/file", files={"file": ("a.json", json.dumps(payload))})
    assert result.status_code == 200
    assert result.json()["summary"]["duplicate_groups"] == 1
    assert "api_key" not in result.text
    scan_id = result.json()["scan_id"]
    assert (
        client.post("/api/v1/scans/" + scan_id + "/delete", json={"dry_run": False}).status_code
        == 400
    )


def setup_delete(monkeypatch):
    items = [
        {"Id": i, "Name": "Film X", "Path": "/" + i + ".mkv", "ProductionYear": 2020}
        for i in ["a", "b"]
    ]
    groups, summary = find_duplicate_groups(items)
    session = main.scan_store.create(
        source="jellyfin",
        groups=groups,
        total_items=2,
        base_url="https://example.com",
        api_key="secret",
        include_item_types=["Movie"],
    )

    class FakeClient:
        deleted = []
        available = items
        fail_refresh = False
        missing_keeper = False

        def __init__(self, *args, **kwargs):
            pass

        def get_all_media_items(self, *args):
            if self.deleted and self.fail_refresh:
                raise JellyfinApiError("offline")
            return self.available

        def item_exists(self, item_id):
            return not self.missing_keeper

        def delete_item(self, item_id):
            self.deleted.append(item_id)

        def wait_until_item_removed(self, *args, **kwargs):
            return True

    monkeypatch.setattr(main, "JellyfinClient", FakeClient)
    return session, FakeClient


def test_stale_library_blocks_delete(client, monkeypatch):
    session, fake = setup_delete(monkeypatch)
    fake.available = []
    response = client.post("/api/v1/scans/" + session.scan_id + "/delete", json={"dry_run": False})
    assert response.status_code == 409
    assert fake.deleted == []


def test_dry_run_revalidates_but_never_deletes(client, monkeypatch):
    session, fake = setup_delete(monkeypatch)
    response = client.post("/api/v1/scans/" + session.scan_id + "/delete", json={"dry_run": True})
    assert response.status_code == 200
    assert fake.deleted == []


def test_keeper_cannot_be_deleted(client, monkeypatch):
    session, fake = setup_delete(monkeypatch)
    response = client.post(
        "/api/v1/scans/" + session.scan_id + "/delete",
        json={"dry_run": False, "item_ids": [session.groups[0].keep_item_id]},
    )
    assert response.status_code == 400
    assert fake.deleted == []


def test_missing_keeper_stops_deletion(client, monkeypatch):
    session, fake = setup_delete(monkeypatch)
    fake.missing_keeper = True
    result = client.post(
        "/api/v1/scans/" + session.scan_id + "/delete", json={"dry_run": False}
    ).json()
    assert result["failed_ids"]
    assert fake.deleted == []


def test_successful_delete_is_pruned_when_rescan_fails(client, monkeypatch):
    session, fake = setup_delete(monkeypatch)
    fake.fail_refresh = True
    result = client.post(
        "/api/v1/scans/" + session.scan_id + "/delete", json={"dry_run": False}
    ).json()
    assert result["deleted_ids"] == ["b"]
    assert main.scan_store.get(session.scan_id).groups == []


def test_concurrent_delete_returns_conflict(client, monkeypatch):
    session, fake = setup_delete(monkeypatch)
    session.operation_lock.acquire()
    try:
        response = client.post(
            "/api/v1/scans/" + session.scan_id + "/delete", json={"dry_run": False}
        )
        assert response.status_code == 409
    finally:
        session.operation_lock.release()


@pytest.mark.parametrize("changed_id", ["a", "b"])
def test_changed_paths_block_deletion_even_when_ids_still_match(client, monkeypatch, changed_id):
    session, fake = setup_delete(monkeypatch)
    fake.available = [
        dict(item, Path="/changed.mkv") if item["Id"] == changed_id else item
        for item in fake.available
    ]
    response = client.post("/api/v1/scans/" + session.scan_id + "/delete", json={"dry_run": False})
    assert response.status_code == 409
    assert fake.deleted == []


def test_file_upload_rejects_excessive_markers(client):
    response = client.post(
        "/api/v1/scans/file",
        files={"file": ("a.json", "[]")},
        data={"custom_sequences": ",".join("x" + str(i) for i in range(101))},
    )
    assert response.status_code == 400
