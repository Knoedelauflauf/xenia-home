"""Every message the integration can show has a text in every language."""

import json
from pathlib import Path
import re
from typing import Any

import pytest

INTEGRATION = Path(__file__).parent.parent / "custom_components" / "xenia_home"
SOURCE = "\n".join(path.read_text() for path in INTEGRATION.glob("*.py"))
EN = json.loads((INTEGRATION / "translations" / "en.json").read_text())

# Abort reasons Home Assistant raises for the config flow helpers the flow uses.
IMPLICIT_ABORTS = {
    "_abort_if_unique_id_configured": {"already_configured", "already_in_progress"},
    "_abort_if_unique_id_mismatch": {"unique_id_mismatch"},
    "async_update_reload_and_abort": {"reconfigure_successful"},
}


def _keys(tree: dict[str, Any], prefix: str = "") -> dict[str, str]:
    """Flatten a translation file to {dotted.key: text}."""
    flat: dict[str, str] = {}
    for key, value in tree.items():
        if isinstance(value, dict):
            flat.update(_keys(value, f"{prefix}{key}."))
        else:
            flat[f"{prefix}{key}"] = value
    return flat


def _named_keys() -> set[str]:
    """Return the message and entity keys the code names."""
    return set(re.findall(r'translation_key(?: =|=)\s*"([a-z_]+)"', SOURCE))


@pytest.mark.parametrize("key", sorted(_named_keys()))
def test_named_keys_have_a_text(key: str) -> None:
    """Every translation key in the code has an exception, issue or entity text."""
    texts = _keys(EN)
    assert (
        f"exceptions.{key}.message" in texts
        or f"issues.{key}.title" in texts
        or any(re.fullmatch(rf"entity\.\w+\.{key}\.name", path) for path in texts)
    )


def test_flow_errors_and_aborts_have_a_text() -> None:
    """Every error and abort reason the flows can show has a text."""
    errors = set(re.findall(r'errors\[[^\]]+\] = "([a-z_]+)"', SOURCE))
    aborts = set(re.findall(r'reason="([a-z_]+)"', SOURCE))
    for helper, reasons in IMPLICIT_ABORTS.items():
        if helper in SOURCE:
            aborts |= reasons
    texts = _keys(EN)
    for error in errors:
        assert {f"config.error.{error}", f"options.error.{error}"} & texts.keys(), error
    for abort in aborts:
        assert {f"config.abort.{abort}", f"options.abort.{abort}"} & texts.keys(), abort


def test_strings_match_english() -> None:
    """strings.json and the English translation are the same."""
    strings = json.loads((INTEGRATION / "strings.json").read_text())
    assert strings == EN


def test_german_has_every_text_and_placeholder() -> None:
    """The German translation has the same keys and placeholders as the English one."""
    de = _keys(json.loads((INTEGRATION / "translations" / "de.json").read_text()))
    en = _keys(EN)
    assert de.keys() == en.keys()
    for key, text in en.items():
        assert set(re.findall(r"{\w+}", de[key])) == set(re.findall(r"{\w+}", text)), (
            key
        )
