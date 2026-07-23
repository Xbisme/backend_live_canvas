"""Object storage / CDN per-flavor config tests (spec US4: FR-008..FR-011).

dev boots on a local fallback with no credentials; prod resolves the S3 backend + CDN
from the environment and fails fast when a required value is missing. Prod is exercised
in a hermetic subprocess (as in test_prod_settings) so os.environ / .env do not leak in.
No bucket is created or written — configuration only.
"""

import json
import subprocess
import sys
from pathlib import Path

from django.core.files.storage import storages

REPO_ROOT = Path(__file__).resolve().parents[2]

_PROD_ENV = {
    "DJANGO_SETTINGS_MODULE": "config.settings.prod",
    "SECRET_KEY": "x" * 64,
    "DATABASE_URL": "postgres://u:p@localhost:5432/livecanvas",
    "ALLOWED_HOSTS": "api.example.com",
    "X_APP_KEY": "prod-app-key",
    "AWS_STORAGE_BUCKET_NAME": "livecanvas-media",
    "AWS_ACCESS_KEY_ID": "AKIA_TEST",
    "AWS_SECRET_ACCESS_KEY": "secret-test",
    "CDN_BASE_URL": "https://cdn.example.com",
}

_DUMP = (
    "import json;"
    "from django.conf import Settings;"
    "s=Settings('config.settings.prod');"
    "print(json.dumps({"
    "'default_backend': s.STORAGES['default']['BACKEND'],"
    "'cdn': s.CDN_BASE_URL,"
    "'bucket': s.AWS_STORAGE_BUCKET_NAME,"
    "}))"
)


def _run(script: str, env: dict[str, str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-c", script],
        cwd=str(REPO_ROOT),
        env={"PATH": "/usr/bin:/bin:/usr/local/bin", "PYTHONPATH": str(REPO_ROOT), **env},
        capture_output=True,
        text=True,
    )


def test_dev_uses_local_fallback_without_credentials() -> None:
    # FR-010: dev boots with no S3 creds → local filesystem storage.
    assert type(storages["default"]).__name__ == "FileSystemStorage"


def test_prod_resolves_s3_and_cdn() -> None:
    result = _run(_DUMP, _PROD_ENV)
    assert result.returncode == 0, result.stderr
    cfg = json.loads(result.stdout.strip().splitlines()[-1])
    assert cfg["default_backend"] == "storages.backends.s3.S3Storage"
    assert cfg["cdn"] == "https://cdn.example.com"
    assert cfg["bucket"] == "livecanvas-media"


def test_prod_fails_fast_without_bucket() -> None:
    env = {k: v for k, v in _PROD_ENV.items() if k != "AWS_STORAGE_BUCKET_NAME"}
    result = _run("from django.conf import Settings; Settings('config.settings.prod')", env)
    assert result.returncode != 0
    assert "ImproperlyConfigured" in result.stderr


def test_prod_fails_fast_without_cdn() -> None:
    env = {k: v for k, v in _PROD_ENV.items() if k != "CDN_BASE_URL"}
    result = _run("from django.conf import Settings; Settings('config.settings.prod')", env)
    assert result.returncode != 0
    assert "ImproperlyConfigured" in result.stderr


def test_prod_fails_fast_without_app_key() -> None:
    # FR-021: prod refuses to boot without a configured app key.
    env = {k: v for k, v in _PROD_ENV.items() if k != "X_APP_KEY"}
    result = _run("from django.conf import Settings; Settings('config.settings.prod')", env)
    assert result.returncode != 0
    assert "ImproperlyConfigured" in result.stderr
