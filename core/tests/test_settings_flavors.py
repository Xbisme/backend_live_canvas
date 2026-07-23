"""Two-flavor guardrail (Constitution VIII, spec SC-003).

Asserts the settings package contains exactly the base plus the two allowed flavors
(dev, prod) and nothing else — in particular no ``staging`` or any third flavor.
"""

from pathlib import Path

SETTINGS_DIR = Path(__file__).resolve().parents[2] / "config" / "settings"

ALLOWED = {"__init__", "base", "dev", "prod"}


def test_exactly_two_flavors_plus_base() -> None:
    modules = {p.stem for p in SETTINGS_DIR.glob("*.py")}
    extra = modules - ALLOWED
    assert not extra, f"Unexpected settings module(s) found (only dev/prod allowed): {extra}"
    assert "dev" in modules and "prod" in modules
    assert "staging" not in modules
