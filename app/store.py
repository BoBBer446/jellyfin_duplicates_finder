from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from threading import Lock
from typing import Literal
from uuid import uuid4

from app.models import DuplicateGroup


@dataclass
class ScanSession:
    scan_id: str
    created_at: datetime
    source: Literal["jellyfin", "file"]
    groups: list[DuplicateGroup]
    total_items: int
    base_url: str | None = None
    api_key: str | None = None
    verify_ssl: bool = True
    include_item_types: list[str] | None = None
    custom_sequences: list[str] | None = None


class ScanStore:
    def __init__(self):
        self._lock = Lock()
        self._scans: dict[str, ScanSession] = {}

    def create(
        self,
        source: Literal["jellyfin", "file"],
        groups: list[DuplicateGroup],
        total_items: int,
        base_url: str | None = None,
        api_key: str | None = None,
        verify_ssl: bool = True,
        include_item_types: list[str] | None = None,
        custom_sequences: list[str] | None = None,
    ) -> ScanSession:
        session = ScanSession(
            scan_id=str(uuid4()),
            created_at=datetime.now(timezone.utc),
            source=source,
            groups=groups,
            total_items=total_items,
            base_url=base_url,
            api_key=api_key,
            verify_ssl=verify_ssl,
            include_item_types=include_item_types,
            custom_sequences=custom_sequences,
        )
        with self._lock:
            self._scans[session.scan_id] = session
        return session

    def get(self, scan_id: str) -> ScanSession | None:
        with self._lock:
            return self._scans.get(scan_id)

    def update_scan_result(self, scan_id: str, groups: list[DuplicateGroup], total_items: int) -> None:
        with self._lock:
            session = self._scans.get(scan_id)
            if not session:
                return
            session.groups = groups
            session.total_items = total_items
