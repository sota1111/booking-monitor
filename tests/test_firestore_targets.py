"""SOT-1300: Firestore-backed targets store + active-mode detection.

These tests never touch real GCP: the Firestore client is replaced with an
in-memory fake and FirestoreTargets is built without running __init__.
"""

from booking_monitor.config import (
    Conditions,
    DateRange,
    Target,
    TimeRange,
    target_from_dict,
    target_to_dict,
)
from booking_monitor.firestore_targets import FirestoreTargets
from booking_monitor.services.targets_store import firestore_targets_active


def _full_target() -> Target:
    return Target(
        name="店舗A",
        url="https://example.com/a",
        interval_seconds=120,
        available_keywords=["空きあり", "予約可"],
        unavailable_keywords=["満席"],
        notify=True,
        site_type="tablecheck",
        conditions=Conditions(
            adults=3,
            children_under_3=1,
            days_of_week=["土", "日"],
            time="18:00",
            date_range=DateRange(start="2026-07-01", end="2026-07-31"),
            time_range=TimeRange(start="17:00", end="20:00", step_minutes=30),
        ),
    )


def test_target_dict_round_trip():
    original = _full_target()
    restored = target_from_dict(target_to_dict(original))

    assert restored.name == original.name
    assert restored.url == original.url
    assert restored.interval_seconds == 120
    assert restored.available_keywords == ["空きあり", "予約可"]
    assert restored.notify is True
    assert restored.site_type == "tablecheck"
    assert restored.conditions.adults == 3
    assert restored.conditions.children_under_3 == 1
    assert restored.conditions.days_of_week == ["土", "日"]
    assert restored.conditions.date_range.start == "2026-07-01"
    assert restored.conditions.time_range.step_minutes == 30


# --- firestore_targets_active() env matrix -------------------------------------

def test_active_requires_project_and_not_sample(monkeypatch):
    monkeypatch.delenv("SEED_SAMPLE_DATA", raising=False)
    monkeypatch.setenv("GOOGLE_CLOUD_PROJECT", "proj-123")
    assert firestore_targets_active() is True


def test_inactive_without_project(monkeypatch):
    monkeypatch.delenv("SEED_SAMPLE_DATA", raising=False)
    monkeypatch.delenv("GOOGLE_CLOUD_PROJECT", raising=False)
    assert firestore_targets_active() is False


def test_inactive_in_sample_mode(monkeypatch):
    monkeypatch.setenv("SEED_SAMPLE_DATA", "true")
    monkeypatch.setenv("GOOGLE_CLOUD_PROJECT", "proj-123")
    assert firestore_targets_active() is False


# --- FirestoreTargets list/add against a fake client ---------------------------

class _FakeDocRef:
    def __init__(self, store, name):
        self._store = store
        self._name = name

    def set(self, data):
        self._store[self._name] = data

    def delete(self):
        self._store.pop(self._name, None)


class _FakeDoc:
    def __init__(self, data):
        self._data = data

    def to_dict(self):
        return self._data


class _FakeCollection:
    def __init__(self, store):
        self._store = store

    def document(self, name):
        return _FakeDocRef(self._store, name)

    def stream(self):
        return [_FakeDoc(v) for v in self._store.values()]


class _FakeDb:
    def __init__(self):
        self.store = {}

    def collection(self, name):
        return _FakeCollection(self.store)


def _store_with_fake_db() -> FirestoreTargets:
    # Bypass __init__ (which would need real GCP creds) and inject a fake client.
    ft = FirestoreTargets.__new__(FirestoreTargets)
    ft.db = _FakeDb()
    ft.collection_name = "monitoring_targets"
    return ft


def test_add_and_list_targets():
    ft = _store_with_fake_db()
    assert ft.list_targets() == []

    ft.add_target(_full_target())
    ft.add_target(
        Target(
            name="店舗B",
            url="https://example.com/b",
            interval_seconds=300,
            available_keywords=[],
            unavailable_keywords=[],
            notify=False,
        )
    )

    targets = ft.list_targets()
    assert [t.name for t in targets] == ["店舗A", "店舗B"]  # sorted by name
    a = next(t for t in targets if t.name == "店舗A")
    assert a.site_type == "tablecheck"
    assert a.conditions.time_range.step_minutes == 30


def test_add_target_keyed_by_name_updates_in_place():
    ft = _store_with_fake_db()
    ft.add_target(_full_target())
    updated = _full_target()
    updated.interval_seconds = 999
    ft.add_target(updated)

    targets = ft.list_targets()
    assert len(targets) == 1
    assert targets[0].interval_seconds == 999


def test_delete_target():
    ft = _store_with_fake_db()
    ft.add_target(_full_target())
    ft.delete_target("店舗A")
    assert ft.list_targets() == []
