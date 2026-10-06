from __future__ import annotations

from pathlib import Path

from outreach.config import Settings


def test_secrets_are_hidden_from_configuration_representation() -> None:
    settings = Settings(
        database_url=("postgresql://user:database-secret@example.neon.tech/db?sslmode=require"),
        gmail_address="candidate@gmail.com",
        gmail_app_password="gmail-secret",
    )
    rendered = repr(settings)
    assert "database-secret" not in rendered
    assert "gmail-secret" not in rendered


def test_sensitive_local_files_are_gitignored() -> None:
    ignore = Path(".gitignore").read_text(encoding="utf-8").splitlines()
    assert ".env" in ignore
    assert ".local/" in ignore
    assert "*.pdf" in ignore
