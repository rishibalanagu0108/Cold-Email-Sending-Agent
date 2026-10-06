from __future__ import annotations

import pytest
from pydantic import ValidationError

from outreach.config import Settings
from outreach.mail import GmailSMTPTransport


def test_neon_url_requires_tls_and_uses_psycopg() -> None:
    settings = Settings(
        database_url="postgresql://user:secret@example.neon.tech/db?sslmode=require"
    )
    assert settings.database_url.startswith("postgresql+psycopg://")

    with pytest.raises(ValidationError, match="sslmode=require"):
        Settings(database_url="postgresql://user:secret@example.neon.tech/db")


def test_gmail_secret_is_hidden_but_available_to_server_adapter() -> None:
    settings = Settings(
        database_url="sqlite+pysqlite:///:memory:",
        gmail_address="candidate@gmail.com",
        gmail_app_password="local-app-secret",
    )
    assert "local-app-secret" not in repr(settings)
    transport = GmailSMTPTransport.from_settings(settings)
    assert transport.address == "candidate@gmail.com"
    assert transport.app_password == "local-app-secret"


def test_public_dashboard_bind_is_rejected() -> None:
    with pytest.raises(ValidationError, match="loopback"):
        Settings(database_url="sqlite+pysqlite:///:memory:", app_host="0.0.0.0")


def test_database_configuration_is_required() -> None:
    with pytest.raises(ValidationError, match="database_url"):
        Settings(_env_file=None)
