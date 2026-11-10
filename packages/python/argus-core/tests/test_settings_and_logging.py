from __future__ import annotations

import json
import logging

import pytest
from argus_core.logging import (
    REDACTED,
    bind_request_context,
    clear_request_context,
    configure_logging,
    get_logger,
)
from argus_core.settings import Environment, Settings
from pydantic import ValidationError


def test_production_requires_hardened_secrets() -> None:
    with pytest.raises(ValueError, match="ARGUS_CURSOR_SECRET"):
        Settings(env=Environment.PROD, _env_file=None)


def test_staging_rejects_stub_auth() -> None:
    with pytest.raises(ValueError, match="ARGUS_AUTH_MODE"):
        Settings(
            env=Environment.STAGING,
            cursor_secret="a-real-production-secret",
            _env_file=None,
        )


def test_local_defaults_are_accepted() -> None:
    settings = Settings(_env_file=None)
    assert settings.env is Environment.LOCAL
    assert settings.auth_mode == "stub"
    assert settings.is_local


def test_settings_are_immutable() -> None:
    settings = Settings(_env_file=None)
    with pytest.raises(ValidationError):
        settings.log_level = "DEBUG"  # type: ignore[misc]


def test_secrets_are_not_printed() -> None:
    settings = Settings(cursor_secret="super-secret-value", _env_file=None)
    assert "super-secret-value" not in repr(settings)


def test_json_logs_redact_sensitive_keys(capsys: pytest.CaptureFixture[str]) -> None:
    settings = Settings(log_format="json", _env_file=None)
    configure_logging(settings)
    bind_request_context(request_id="req_1", trace_id="a" * 32, tenant_id="tnt_x")
    try:
        get_logger("test").info(
            "token exchange", authorization="Bearer abc", nested_secret="shh", safe_field="visible"
        )
    finally:
        clear_request_context()
        logging.getLogger().handlers.clear()

    line = json.loads(capsys.readouterr().out.strip().splitlines()[-1])
    assert line["authorization"] == REDACTED
    assert line["nested_secret"] == REDACTED
    assert line["safe_field"] == "visible"
    assert line["request_id"] == "req_1"
    assert line["tenant_id"] == "tnt_x"
    assert line["service"] == settings.service_name
    assert line["env"] == "local"
