from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from typing import Any

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse

from app.duplicate_finder import find_duplicate_groups
from app.jellyfin_client import JellyfinApiError, JellyfinClient
from app.models import DeleteRequest, DeleteResult, JellyfinScanRequest, ScanResult
from app.store import ScanStore

LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()
logging.getLogger("jellydup").setLevel(LOG_LEVEL)
logger = logging.getLogger("jellydup.api")

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
    logger.info(
        "Starting scan: base_url=%s types=%s verify_ssl=%s",
        request.base_url,
        request.include_item_types,
        request.verify_ssl,
    )
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
        include_item_types=request.include_item_types,
        custom_sequences=request.custom_sequences,
    )
    logger.info(
        "Scan completed: scan_id=%s total_items=%s groups=%s delete_candidates=%s",
        session.scan_id,
        summary.total_items,
        summary.duplicate_groups,
        summary.duplicate_items_to_delete,
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
    id_to_path = {
        item.id: item.path
        for group in session.groups
        for item in group.items
        if item.id in all_candidates
    }
    requested_ids = sorted(all_candidates if request.item_ids is None else set(request.item_ids))
    invalid_ids = [item_id for item_id in requested_ids if item_id not in all_candidates]
    if invalid_ids:
        raise HTTPException(
            status_code=400,
            detail=f"Unknown item IDs for this scan: {', '.join(invalid_ids)}",
        )

    if request.dry_run:
        logger.info("Dry-run delete: scan_id=%s count=%s", scan_id, len(requested_ids))
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
    still_present_after_delete: list[str] = []

    logger.info("Delete started: scan_id=%s requested_ids=%s", scan_id, len(requested_ids))

    for item_id in requested_ids:
        logger.info("Deleting item: id=%s path=%s", item_id, id_to_path.get(item_id, "unknown"))
        try:
            client.delete_item(item_id)
            removed = client.wait_until_item_removed(item_id, attempts=3, delay_seconds=0.5)
            if removed:
                deleted_ids.append(item_id)
                logger.info("Delete verified: id=%s", item_id)
            else:
                still_present_after_delete.append(item_id)
                logger.warning("Delete not yet reflected: id=%s", item_id)
        except JellyfinApiError as exc:
            failed_ids[item_id] = str(exc)
            logger.error("Delete failed: id=%s error=%s", item_id, exc)

    if still_present_after_delete:
        logger.warning(
            "Items still present after first delete pass; triggering library refresh. count=%s",
            len(still_present_after_delete),
        )
        try:
            client.refresh_library()
        except JellyfinApiError as exc:
            logger.error("Library refresh failed after delete: %s", exc)

        for item_id in still_present_after_delete:
            try:
                removed = client.wait_until_item_removed(item_id, attempts=8, delay_seconds=1.0)
                if removed:
                    deleted_ids.append(item_id)
                    logger.info("Delete verified after refresh: id=%s", item_id)
                else:
                    failed_ids[item_id] = (
                        "Delete request was accepted but item still exists after refresh. "
                        "Likely Jellyfin filesystem permission/mount issue."
                    )
                    logger.error("Delete still not applied after refresh: id=%s", item_id)
            except JellyfinApiError as exc:
                failed_ids[item_id] = str(exc)
                logger.error("Delete recheck failed: id=%s error=%s", item_id, exc)

    if session.include_item_types:
        try:
            updated_items = client.get_all_media_items(session.include_item_types)
            updated_groups, updated_summary = find_duplicate_groups(
                updated_items, session.custom_sequences
            )
            scan_store.update_scan_result(scan_id, updated_groups, updated_summary.total_items)
            logger.info(
                "Post-delete scan refresh complete: scan_id=%s total_items=%s groups=%s",
                scan_id,
                updated_summary.total_items,
                updated_summary.duplicate_groups,
            )
        except JellyfinApiError:
            # Keep delete result useful even if post-delete refresh fails.
            logger.exception("Post-delete scan refresh failed: scan_id=%s", scan_id)

    return DeleteResult(
        scan_id=scan_id,
        dry_run=False,
        requested_ids=requested_ids,
        deleted_ids=deleted_ids,
        failed_ids=failed_ids,
    )
