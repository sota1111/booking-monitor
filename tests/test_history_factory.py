"""Tests for get_history() backend selection (SOT-1167).

In sample-data mode the sample seeder writes only to the local ``logs/*.jsonl``
files, so the dashboard must read from the local ``History`` even when
``GOOGLE_CLOUD_PROJECT`` is set (deployed). Otherwise the seeded sample data is
written locally but read from Firestore and never appears.
"""

import booking_monitor.firestore_history as firestore_history
from booking_monitor.history import History
from booking_monitor.services import history_factory


def test_sample_mode_returns_local_history_even_with_gcp(monkeypatch):
    """Sample mode must use local History regardless of GOOGLE_CLOUD_PROJECT."""
    monkeypatch.setenv("SEED_SAMPLE_DATA", "true")
    monkeypatch.setenv("GOOGLE_CLOUD_PROJECT", "some-project")

    # Make the Firestore branch fail loudly if it is ever taken in sample mode.
    monkeypatch.setattr(
        firestore_history,
        "FirestoreHistory",
        lambda *a, **k: pytest_fail_marker(),
    )

    history = history_factory.get_history()
    assert isinstance(history, History)


def test_non_sample_mode_with_gcp_prefers_firestore(monkeypatch):
    """Without sample mode, GOOGLE_CLOUD_PROJECT still selects Firestore."""
    monkeypatch.delenv("SEED_SAMPLE_DATA", raising=False)
    monkeypatch.setenv("GOOGLE_CLOUD_PROJECT", "some-project")

    sentinel = object()
    monkeypatch.setattr(firestore_history, "FirestoreHistory", lambda *a, **k: sentinel)
    assert history_factory.get_history() is sentinel


def test_non_sample_mode_without_gcp_uses_local(monkeypatch):
    """Without sample mode and without GCP, local History is used."""
    monkeypatch.delenv("SEED_SAMPLE_DATA", raising=False)
    monkeypatch.delenv("GOOGLE_CLOUD_PROJECT", raising=False)
    assert isinstance(history_factory.get_history(), History)


def pytest_fail_marker():
    raise AssertionError("FirestoreHistory must not be used in sample mode")
