from datetime import timedelta

import pytest

from app.store import ScanCapacityError, ScanStore


def create(store):
    return store.create(source="file", groups=[], total_items=0)


def test_oldest_scan_is_evicted_at_capacity():
    store = ScanStore(max_scans=2)
    a, b, c = create(store), create(store), create(store)
    assert store.get(a.scan_id) is None
    assert store.get(b.scan_id) is b
    assert store.get(c.scan_id) is c


def test_expired_scan_is_removed_but_running_delete_is_preserved():
    store = ScanStore(ttl_seconds=60)
    session = create(store)
    session.created_at -= timedelta(seconds=61)
    with session.operation_lock:
        assert store.get(session.scan_id) is session
    assert store.get(session.scan_id) is None


def test_full_store_does_not_evict_active_delete():
    store = ScanStore(max_scans=1)
    session = create(store)
    with session.operation_lock:
        with pytest.raises(ScanCapacityError):
            create(store)
    assert store.get(session.scan_id) is session
