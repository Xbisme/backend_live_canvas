"""Polish — purge_stale_uploads command (orphaned-upload edge case)."""

from datetime import timedelta
from io import StringIO
from unittest import mock

import pytest
from django.core.management import call_command
from django.utils import timezone

from apps.uploads.management.commands import purge_stale_uploads
from apps.uploads.models import UploadPurpose, UploadSlot

pytestmark = pytest.mark.django_db


def _slot(admin_user, key: str, *, age_hours: int, consumed: bool = False) -> UploadSlot:
    slot = UploadSlot.objects.create(
        key=key, purpose=UploadPurpose.VIDEO, content_type="video/mp4", created_by=admin_user
    )
    UploadSlot.objects.filter(pk=slot.pk).update(
        created_at=timezone.now() - timedelta(hours=age_hours),
        consumed_at=timezone.now() if consumed else None,
    )
    slot.refresh_from_db()
    return slot


def _run(**opts) -> str:
    out = StringIO()
    call_command("purge_stale_uploads", stdout=out, stderr=out, **opts)
    return out.getvalue()


def test_dry_run_lists_but_keeps(admin_user, monkeypatch):
    monkeypatch.setattr(purge_stale_uploads, "storage", mock.MagicMock())
    stale = _slot(admin_user, "staging/old.mp4", age_hours=48)
    _slot(admin_user, "staging/fresh.mp4", age_hours=1)
    out = _run()
    assert "staging/old.mp4" in out and "staging/fresh.mp4" not in out
    assert "1 stale" in out and "dry-run" in out
    assert UploadSlot.objects.filter(pk=stale.pk).exists()


def test_delete_removes_slot_and_object(admin_user, monkeypatch):
    st = mock.MagicMock()
    monkeypatch.setattr(purge_stale_uploads, "storage", st)
    stale = _slot(admin_user, "staging/old.mp4", age_hours=48)
    consumed = _slot(admin_user, "staging/used.mp4", age_hours=48, consumed=True)
    _run(delete=True)
    assert not UploadSlot.objects.filter(pk=stale.pk).exists()
    assert UploadSlot.objects.filter(pk=consumed.pk).exists()  # consumed slots are history
    st.delete_object.assert_called_once_with("staging/old.mp4")
