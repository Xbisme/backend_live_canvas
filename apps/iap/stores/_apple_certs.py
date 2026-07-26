"""Apple root CA loading for JWS signature verification.

The App Store Server library verifies signed payloads against Apple's root CAs. In real
deployments these are provisioned as PEM/DER files referenced by env; the loader reads
them lazily so the module stays import-safe with no certs configured (tests mock the
verification boundary and never reach here).
"""

from __future__ import annotations

from pathlib import Path

from django.conf import settings


def load_apple_root_certs() -> list[bytes]:
    """Return Apple root CA DER blobs from ``IAP_APPLE_ROOT_CERTS_DIR`` (if configured).

    Empty when unset — acceptable for dev/tests (which mock the verifier); production sets
    the directory so signature verification has the real trust anchors.
    """
    certs_dir = getattr(settings, "IAP_APPLE_ROOT_CERTS_DIR", "")
    if not certs_dir:
        return []
    directory = Path(certs_dir)
    if not directory.is_dir():
        return []
    return [p.read_bytes() for p in sorted(directory.glob("*.cer"))]
