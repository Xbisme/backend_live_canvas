"""US2 — bulk backfill: idempotent, resumable, provenance-preserving (FR-015/016/017)."""

import sys
import types
from io import StringIO
from unittest import mock

import pytest
from django.core.management import CommandError, call_command

from apps.uploads.management.commands import backfill_media
from apps.wallpapers.models import Wallpaper, WallpaperStatus
from apps.wallpapers.tests.factories import WallpaperFactory

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def eager_celery(settings):
    settings.CELERY_TASK_ALWAYS_EAGER = True
    settings.CELERY_TASK_EAGER_PROPAGATES = True


@pytest.fixture(autouse=True)
def fake_magic(monkeypatch):
    stub = types.SimpleNamespace(from_buffer=mock.Mock(return_value="video/mp4"))
    monkeypatch.setitem(sys.modules, "magic", stub)
    return stub


@pytest.fixture
def dataset(tmp_path):
    """A fake local dataset with one real file per seeded wallpaper we create."""
    (tmp_path / "ocean-waves").mkdir()
    (tmp_path / "ocean-waves" / "111.mp4").write_bytes(b"fake video bytes")
    (tmp_path / "ocean-waves" / "222.mp4").write_bytes(b"fake video bytes")
    return tmp_path


@pytest.fixture
def fake_pipeline(monkeypatch):
    """Mock storage in BOTH the command and the task; run ffmpeg as cheap stubs."""
    from apps.uploads import tasks as pipeline

    st = mock.MagicMock()
    from apps.uploads import storage as real

    st.new_key.side_effect = real.new_key
    for const in (
        "PRIVATE",
        "PUBLIC",
        "STAGING_PREFIX",
        "MASTERS_PREFIX",
        "THUMBS_PREFIX",
        "PREVIEWS_PREFIX",
    ):
        setattr(st, const, getattr(real, const))
    st.head_size.return_value = 5_000
    st.read_head.return_value = b"\x00" * 64
    st.download_file.side_effect = lambda key, dest, **kw: dest.write_bytes(b"src")
    st.public_url.side_effect = lambda key: f"http://cdn.test/{key}"
    monkeypatch.setattr(pipeline, "storage", st)
    monkeypatch.setattr(backfill_media, "storage", st)

    ff = mock.MagicMock()
    ff.FfmpegError = pipeline.ffmpeg.FfmpegError
    ff.probe.return_value = {"width": 2160, "height": 3840, "duration": 9.0}
    ff.normalize_master.side_effect = lambda src, dst: dst.write_bytes(b"m" * 999)
    ff.extract_thumbnail.side_effect = lambda src, dst: dst.write_bytes(b"j")
    ff.render_preview.side_effect = lambda src, dst: dst.write_bytes(b"p")
    monkeypatch.setattr(pipeline, "ffmpeg", ff)
    return st


@pytest.fixture
def fixture_mapping(monkeypatch, tmp_path):
    """Point the command at a minimal committed-fixture stand-in."""
    fixture = tmp_path / "seed.json"
    fixture.write_text(
        """{"wallpapers": [
            {"source_url": "https://pexels.com/v/111", "local_path": "ocean-waves/111.mp4"},
            {"source_url": "https://pexels.com/v/222", "local_path": "ocean-waves/222.mp4"},
            {"source_url": "https://pexels.com/v/333", "local_path": "ocean-waves/missing.mp4"}
        ]}"""
    )
    monkeypatch.setattr(backfill_media, "FIXTURE", fixture)
    return fixture


def _seeded(source_url: str, **over) -> Wallpaper:
    defaults = {
        "status": WallpaperStatus.PUBLISHED,
        "thumbnail_url": "https://images.pexels.com/x.jpeg",
        "preview_video_url": "https://videos.pexels.com/x.mp4",
        "license_type": "Pexels License",
    }
    defaults.update(over)
    return WallpaperFactory(source_url=source_url, **defaults)


def _run(**opts) -> str:
    out = StringIO()
    call_command("backfill_media", stdout=out, stderr=out, **opts)
    return out.getvalue()


def test_backfill_processes_and_replaces_pexels_urls(dataset, fake_pipeline, fixture_mapping):
    w1 = _seeded("https://pexels.com/v/111")
    w2 = _seeded("https://pexels.com/v/222")
    out = _run(dataset_dir=str(dataset))
    assert "processed=2" in out

    for w in (w1, w2):
        w.refresh_from_db()
        assert w.master_key and w.master_key.startswith("masters/")
        assert "pexels.com" not in w.thumbnail_url
        assert "pexels.com" not in w.preview_video_url
        # Provenance untouched (FR-016).
        assert "pexels.com" in w.source_url
        assert w.license_type == "Pexels License"


def test_backfill_is_idempotent_on_rerun(dataset, fake_pipeline, fixture_mapping):
    _seeded("https://pexels.com/v/111")
    _run(dataset_dir=str(dataset))
    upload_calls_after_first = fake_pipeline.upload_file.call_count

    out = _run(dataset_dir=str(dataset))  # second run: everything already has master_key
    assert "processed=0" in out
    assert "skipped-done=1" in out
    assert fake_pipeline.upload_file.call_count == upload_calls_after_first  # no re-upload


def test_backfill_reports_and_skips_missing_files(dataset, fake_pipeline, fixture_mapping):
    _seeded("https://pexels.com/v/111")
    _seeded("https://pexels.com/v/333")  # fixture points at a file not on disk
    out = _run(dataset_dir=str(dataset))
    assert "processed=1" in out
    assert "skipped-missing=1" in out


def test_backfill_never_touches_soft_deleted(dataset, fake_pipeline, fixture_mapping):
    from django.utils import timezone

    w = _seeded("https://pexels.com/v/111", deleted_at=timezone.now())
    _run(dataset_dir=str(dataset))
    w.refresh_from_db()
    assert w.master_key is None  # not resurrected (spec edge case)


def test_backfill_dry_run_changes_nothing(dataset, fake_pipeline, fixture_mapping):
    w = _seeded("https://pexels.com/v/111")
    out = _run(dataset_dir=str(dataset), dry_run=True)
    assert "dry-run" in out
    w.refresh_from_db()
    assert w.master_key is None and "pexels.com" in w.thumbnail_url
    fake_pipeline.upload_file.assert_not_called()


def test_backfill_limit_batches_work(dataset, fake_pipeline, fixture_mapping):
    _seeded("https://pexels.com/v/111")
    _seeded("https://pexels.com/v/222")
    out = _run(dataset_dir=str(dataset), limit=1)
    assert "processed=1" in out
    assert Wallpaper.objects.filter(master_key__isnull=False).count() == 1


def test_backfill_requires_dataset_dir(fake_pipeline, fixture_mapping):
    with pytest.raises(CommandError, match="Dataset directory not found"):
        call_command("backfill_media", dataset_dir="/nonexistent/path")


def test_staged_failed_item_requeued_without_reupload(dataset, fake_pipeline, fixture_mapping):
    """Interrupted-run resume (FR-016): staged object exists → re-enqueue only, no upload."""
    w = _seeded(
        "https://pexels.com/v/111",
        status=WallpaperStatus.FAILED,
        staging_key="staging/kept.mp4",
    )
    out = _run(dataset_dir=str(dataset))
    assert "requeued=1" in out
    # Never re-uploads the staged SOURCE (the eager pipeline still uploads its artifacts).
    staging_uploads = [
        c for c in fake_pipeline.upload_file.call_args_list if c.args[1].startswith("staging/")
    ]
    assert staging_uploads == []
    w.refresh_from_db()
    assert w.status == WallpaperStatus.PUBLISHED  # eager task retried from staging


def test_staged_inflight_item_skipped_unless_requeue_stale(dataset, fake_pipeline, fixture_mapping):
    """Staged + not failed = assumed in-flight in the broker; only --requeue-stale touches it."""
    _seeded("https://pexels.com/v/111", staging_key="staging/inflight.mp4")
    out = _run(dataset_dir=str(dataset))
    assert "in-flight=1" in out and "requeued=0" in out

    out = _run(dataset_dir=str(dataset), requeue_stale=True)
    assert "requeued=1" in out
    staging_uploads = [
        c for c in fake_pipeline.upload_file.call_args_list if c.args[1].startswith("staging/")
    ]
    assert staging_uploads == []
