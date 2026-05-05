"""Service-account ADC for Vertex AI.

This module deliberately bypasses the gcloud-CLI flavour of Application Default
Credentials. Auth is sourced exclusively from a service-account JSON key file
pointed to by ``GOOGLE_APPLICATION_CREDENTIALS``.

Why no implicit ADC chain?
    Vertex deployments often live in environments where ``gcloud`` is not
    installed (containers, Lambda, GitHub Actions). Forcing the explicit
    service-account path makes credential resolution deterministic, gives
    actionable error messages on misconfiguration, and prevents accidental
    use of a developer's personal ADC in production.

The loader is cached for the life of the process. Use :func:`reset_auth_cache`
in tests when you need to swap credentials between cases.
"""

from __future__ import annotations

import json
import os
from functools import lru_cache
from pathlib import Path

from google.oauth2 import service_account


VERTEX_SCOPES = ("https://www.googleapis.com/auth/cloud-platform",)
"""Required OAuth scope for any Vertex AI API call."""

ENV_VAR = "GOOGLE_APPLICATION_CREDENTIALS"


class AuthConfigError(RuntimeError):
    """Raised when service-account credentials cannot be resolved."""


def _resolve_key_path() -> Path:
    raw = os.environ.get(ENV_VAR)
    if not raw:
        raise AuthConfigError(
            f"{ENV_VAR} is not set. Point it at a service-account JSON key file. "
            "case-agent does not fall back to gcloud ADC."
        )
    path = Path(raw).expanduser()
    if not path.is_absolute():
        path = path.resolve()
    if not path.is_file():
        raise AuthConfigError(
            f"{ENV_VAR}={raw!r} does not point to a readable file ({path})."
        )
    if not os.access(path, os.R_OK):
        raise AuthConfigError(
            f"{ENV_VAR}={raw!r} exists but is not readable by the current user."
        )
    return path


def _validate_key_payload(path: Path) -> dict:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        raise AuthConfigError(
            f"Service-account key at {path} is not valid JSON: {e}"
        ) from e
    if not isinstance(payload, dict):
        raise AuthConfigError(
            f"Service-account key at {path} must be a JSON object, got {type(payload).__name__}."
        )
    key_type = payload.get("type")
    if key_type != "service_account":
        raise AuthConfigError(
            f"Key at {path} has type={key_type!r}; expected 'service_account'. "
            "Workload-Identity / external-account keys are not supported in this build."
        )
    for required in ("client_email", "token_uri", "private_key"):
        if required not in payload:
            raise AuthConfigError(
                f"Service-account key at {path} is missing required field {required!r}."
            )
    return payload


@lru_cache(maxsize=1)
def _load_cached() -> tuple[service_account.Credentials, str]:
    """Cached: returns (credentials, client_email) for the configured key file."""
    path = _resolve_key_path()
    payload = _validate_key_payload(path)
    creds = service_account.Credentials.from_service_account_info(
        payload, scopes=list(VERTEX_SCOPES)
    )
    return creds, payload["client_email"]


def get_credentials() -> service_account.Credentials:
    """Return cached service-account credentials, or raise AuthConfigError."""
    return _load_cached()[0]


def get_client_email() -> str:
    """Return the service-account email currently in use (for logging/debug)."""
    return _load_cached()[1]


def reset_auth_cache() -> None:
    """Clear the credentials cache. Mostly for tests after env changes."""
    _load_cached.cache_clear()
