from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
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
    skipped_items: int = 0
    operation_lock: Lock = field(default_factory=Lock, repr=False)
    base_url: str | None = None
    api_key: str | None = None
    verify_ssl: bool = True
    include_item_types: list[str] | None = None
    custom_sequences: list[str] | None = None


class ScanCapacityError(RuntimeError):
    pass


class ScanStore:
    def __init__(self, max_scans: int = 100, ttl_seconds: int = 7200):
        self.max_scans = max_scans
        self.ttl = timedelta(seconds=ttl_seconds)
        self._lock = Lock()
        self._scans: dict[str, ScanSession] = {}

    def _prune(self) -> None:
        cutoff = datetime.now(timezone.utc) - self.ttl
        for key, value in list(self._scans.items()):
            if value.created_at < cutoff and not value.operation_lock.locked():
                self._scans.pop(key)

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
        skipped_items: int = 0,
    ) -> ScanSession:
        session = ScanSession(
            scan_id=str(uuid4()),
            created_at=datetime.now(timezone.utc),
            source=source,
            groups=groups,
            total_items=total_items,
            skipped_items=skipped_items,
            base_url=base_url,
            api_key=api_key,
            verify_ssl=verify_ssl,
            include_item_types=include_item_types,
            custom_sequences=custom_sequences,
        )
        with self._lock:
            self._prune()
            if len(self._scans) >= self.max_scans:
                oldest = next(
                    (
                        key
                        for key, value in self._scans.items()
                        if not value.operation_lock.locked()
                    ),
                    None,
                )
                if oldest is None:
                    raise ScanCapacityError(
                        "All scan slots are busy; try again after a delete finishes"
                    )
                self._scans.pop(oldest)
            self._scans[session.scan_id] = session
        return session

    def get(self, scan_id: str) -> ScanSession | None:
        with self._lock:
            self._prune()
            return self._scans.get(scan_id)

    def update_scan_result(
        self,
        scan_id: str,
        groups: list[DuplicateGroup],
        total_items: int,
        skipped_items: int = 0,
    ) -> None:
        with self._lock:
            session = self._scans.get(scan_id)
            if not session:
                return
            session.groups = groups
            session.total_items = total_items
            session.skipped_items = skipped_items

    def remove_items(self, scan_id: str, deleted_ids: list[str]) -> None:
        with self._lock:
            session = self._scans.get(scan_id)
            if not session:
                return
            deleted = set(deleted_ids)
            remaining = []
            for group in session.groups:
                group.items = [item for item in group.items if item.id not in deleted]
                group.delete_candidates = [
                    item_id for item_id in group.delete_candidates if item_id not in deleted
                ]
                group.reclaimable_bytes = sum(
                    item.size for item in group.items if item.id in group.delete_candidates
                )
                if group.delete_candidates:
                    remaining.append(group)
            session.groups = remaining
            session.total_items = max(0, session.total_items - len(deleted))
