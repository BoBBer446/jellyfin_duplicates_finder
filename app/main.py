from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse

from app.duplicate_finder import find_duplicate_groups
from app.jellyfin_client import JellyfinApiError, JellyfinClient
from app.models import DeleteRequest, DeleteResult, JellyfinScanRequest, ScanResult
from app.store import ScanStore

app = FastAPI(
    title="Jellyfin Duplicate Finder API",
    version="2.0.0",
    description="Scan Jellyfin media, find duplicates, and remove duplicate items by API.",
)
scan_store = ScanStore()
STATIC_DIR = Path(__file__).parent / "static"


def _build_scan_result(scan_id: str) -> ScanResult:
    session = scan_store.get(scan_id)
    if not session:
        raise HTTPException(status_code=404, detail="scan_id not found")

    duplicate_items_to_delete = sum(len(group.delete_candidates) for group in session.groups)
    return ScanResult(
        scan_id=session.scan_id,
        created_at=session.created_at,
        source=session.source,
        summary={
            "total_items": session.total_items,
            "duplicate_groups": len(session.groups),
            "duplicate_items_to_delete": duplicate_items_to_delete,
        },
        groups=session.groups,
    )


def _extract_items(payload: Any) -> list[dict[str, Any]]:
    if isinstance(payload, dict) and isinstance(payload.get("Items"), list):
        return payload["Items"]
    if isinstance(payload, list):
        return payload
    raise HTTPException(
        status_code=400,
        detail="JSON must be either {\"Items\": [...]} or a list of items",
    )


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/")
def root() -> FileResponse:
    return FileResponse(STATIC_DIR / "index.html")


@app.post("/api/v1/scans/jellyfin", response_model=ScanResult)
def scan_jellyfin(request: JellyfinScanRequest) -> ScanResult:
    client = JellyfinClient(
        str(request.base_url),
        request.api_key,
        verify_ssl=request.verify_ssl,
    )
    try:
        items = client.get_all_media_items(request.include_item_types)
    except JellyfinApiError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    groups, summary = find_duplicate_groups(items, request.custom_sequences)
    session = scan_store.create(
        source="jellyfin",
        groups=groups,
        total_items=summary.total_items,
        base_url=str(request.base_url),
        api_key=request.api_key,
        verify_ssl=request.verify_ssl,
    )
    return _build_scan_result(session.scan_id)


@app.post("/api/v1/scans/file", response_model=ScanResult)
async def scan_file(
    file: UploadFile = File(...),
    custom_sequences: str | None = Form(default=None),
) -> ScanResult:
    if not file.filename:
        raise HTTPException(status_code=400, detail="Missing file name")

    try:
        raw_payload = json.loads((await file.read()).decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise HTTPException(status_code=400, detail=f"Invalid JSON file: {exc}") from exc

    items = _extract_items(raw_payload)
    sequences = None
    if custom_sequences:
        sequences = [entry.strip() for entry in custom_sequences.split(",") if entry.strip()]

    groups, summary = find_duplicate_groups(items, sequences)
    session = scan_store.create(source="file", groups=groups, total_items=summary.total_items)
    return _build_scan_result(session.scan_id)


@app.get("/api/v1/scans/{scan_id}", response_model=ScanResult)
def get_scan(scan_id: str) -> ScanResult:
    return _build_scan_result(scan_id)


@app.post("/api/v1/scans/{scan_id}/delete", response_model=DeleteResult)
def delete_duplicates(scan_id: str, request: DeleteRequest) -> DeleteResult:
    session = scan_store.get(scan_id)
    if not session:
        raise HTTPException(status_code=404, detail="scan_id not found")

    if session.source != "jellyfin" or not session.base_url or not session.api_key:
        raise HTTPException(
            status_code=400,
            detail="Delete is only available for scans created from Jellyfin API credentials.",
        )

    all_candidates = {
        item_id for group in session.groups for item_id in group.delete_candidates
    }
    requested_ids = sorted(all_candidates if request.item_ids is None else set(request.item_ids))
    invalid_ids = [item_id for item_id in requested_ids if item_id not in all_candidates]
    if invalid_ids:
        raise HTTPException(
            status_code=400,
            detail=f"Unknown item IDs for this scan: {', '.join(invalid_ids)}",
        )

    if request.dry_run:
        return DeleteResult(
            scan_id=scan_id,
            dry_run=True,
            requested_ids=requested_ids,
            deleted_ids=[],
            failed_ids={},
        )

    client = JellyfinClient(
        session.base_url,
        session.api_key,
        verify_ssl=session.verify_ssl,
    )
    deleted_ids: list[str] = []
    failed_ids: dict[str, str] = {}

    for item_id in requested_ids:
        try:
            client.delete_item(item_id)
            deleted_ids.append(item_id)
        except JellyfinApiError as exc:
            failed_ids[item_id] = str(exc)

    return DeleteResult(
        scan_id=scan_id,
        dry_run=False,
        requested_ids=requested_ids,
        deleted_ids=deleted_ids,
        failed_ids=failed_ids,
    )
