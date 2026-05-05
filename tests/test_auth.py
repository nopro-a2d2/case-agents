"""Tests for the service-account ADC loader.

These tests never call GCP — they fabricate a structurally-valid key payload
(with a small RSA private key) so `service_account.Credentials.from_service_account_info`
will accept it without any network round-trip.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from case_agent import auth as auth_mod


def _ensure_clean_cache():
    auth_mod.reset_auth_cache()


@pytest.fixture(autouse=True)
def _clear_creds_env(monkeypatch):
    monkeypatch.delenv(auth_mod.ENV_VAR, raising=False)
    _ensure_clean_cache()
    yield
    _ensure_clean_cache()


def _write_valid_key(tmp_path: Path) -> Path:
    """Build a minimally valid service-account JSON with a freshly generated RSA key."""
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric import rsa

    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    pem = private_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    ).decode("utf-8")

    payload = {
        "type": "service_account",
        "project_id": "case-agent-test",
        "private_key_id": "fake-id",
        "private_key": pem,
        "client_email": "case-agent-test@case-agent-test.iam.gserviceaccount.com",
        "client_id": "0",
        "auth_uri": "https://accounts.google.com/o/oauth2/auth",
        "token_uri": "https://oauth2.googleapis.com/token",
    }
    p = tmp_path / "sa.json"
    p.write_text(json.dumps(payload), encoding="utf-8")
    return p


def test_missing_env_var_raises(monkeypatch) -> None:
    with pytest.raises(auth_mod.AuthConfigError, match="GOOGLE_APPLICATION_CREDENTIALS is not set"):
        auth_mod.get_credentials()


def test_path_not_a_file(monkeypatch, tmp_path: Path) -> None:
    bogus = tmp_path / "nope.json"
    monkeypatch.setenv(auth_mod.ENV_VAR, str(bogus))
    with pytest.raises(auth_mod.AuthConfigError, match="does not point to a readable file"):
        auth_mod.get_credentials()


def test_malformed_json_raises(monkeypatch, tmp_path: Path) -> None:
    bad = tmp_path / "bad.json"
    bad.write_text("{not valid json", encoding="utf-8")
    monkeypatch.setenv(auth_mod.ENV_VAR, str(bad))
    with pytest.raises(auth_mod.AuthConfigError, match="not valid JSON"):
        auth_mod.get_credentials()


def test_wrong_key_type_raises(monkeypatch, tmp_path: Path) -> None:
    bad = tmp_path / "external.json"
    bad.write_text(json.dumps({"type": "external_account"}), encoding="utf-8")
    monkeypatch.setenv(auth_mod.ENV_VAR, str(bad))
    with pytest.raises(auth_mod.AuthConfigError, match="external-account keys are not supported"):
        auth_mod.get_credentials()


def test_missing_required_field_raises(monkeypatch, tmp_path: Path) -> None:
    bad = tmp_path / "missing.json"
    bad.write_text(
        json.dumps({"type": "service_account", "client_email": "x@y", "token_uri": "u"}),
        encoding="utf-8",
    )
    monkeypatch.setenv(auth_mod.ENV_VAR, str(bad))
    with pytest.raises(auth_mod.AuthConfigError, match="missing required field 'private_key'"):
        auth_mod.get_credentials()


def test_valid_key_loads(monkeypatch, tmp_path: Path) -> None:
    key = _write_valid_key(tmp_path)
    monkeypatch.setenv(auth_mod.ENV_VAR, str(key))

    creds = auth_mod.get_credentials()
    assert creds is not None
    assert auth_mod.get_client_email() == "case-agent-test@case-agent-test.iam.gserviceaccount.com"

    # Cached: a second call returns the same object (no re-parse).
    assert auth_mod.get_credentials() is creds
