"""Prod flavor settings tests (spec FR-010, FR-011).

Loading the prod settings module is exercised in a hermetic subprocess so the test
does not depend on the test runner's global settings, on any ``.env`` file, or on
os.environ leakage. This proves:
  * with valid config, prod is hardened (DEBUG off, security flags on);
  * with a required value missing, startup fails fast (ImproperlyConfigured).
"""

import json
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]

_VALID_ENV = {
    "DJANGO_SETTINGS_MODULE": "config.settings.prod",
    "SECRET_KEY": "x" * 64,
    "DATABASE_URL": "postgres://u:p@localhost:5432/livecanvas",
    "ALLOWED_HOSTS": "api.example.com",
}

# Dump the security-relevant settings as JSON so the parent can assert on them.
_DUMP_SCRIPT = (
    "import json;"
    "from django.conf import Settings;"
    "s=Settings('config.settings.prod');"
    "print(json.dumps({"
    "'DEBUG': s.DEBUG,"
    "'SECURE_SSL_REDIRECT': s.SECURE_SSL_REDIRECT,"
    "'SECURE_HSTS_SECONDS': s.SECURE_HSTS_SECONDS,"
    "'SESSION_COOKIE_SECURE': s.SESSION_COOKIE_SECURE,"
    "'CSRF_COOKIE_SECURE': s.CSRF_COOKIE_SECURE,"
    "'ALLOWED_HOSTS': s.ALLOWED_HOSTS,"
    "'has_whitenoise': any('whitenoise' in m for m in s.MIDDLEWARE),"
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


def test_prod_settings_hardened() -> None:
    result = _run(_DUMP_SCRIPT, _VALID_ENV)
    assert result.returncode == 0, result.stderr
    cfg = json.loads(result.stdout.strip().splitlines()[-1])
    assert cfg["DEBUG"] is False
    assert cfg["SECURE_SSL_REDIRECT"] is True
    assert cfg["SECURE_HSTS_SECONDS"] > 0
    assert cfg["SESSION_COOKIE_SECURE"] is True
    assert cfg["CSRF_COOKIE_SECURE"] is True
    assert cfg["ALLOWED_HOSTS"] == ["api.example.com"]
    assert cfg["has_whitenoise"] is True


def test_prod_fails_fast_without_secret_key() -> None:
    env = {"DJANGO_SETTINGS_MODULE": "config.settings.prod"}  # no SECRET_KEY/DATABASE_URL
    result = _run("from django.conf import Settings; Settings('config.settings.prod')", env)
    assert result.returncode != 0
    assert "ImproperlyConfigured" in result.stderr
