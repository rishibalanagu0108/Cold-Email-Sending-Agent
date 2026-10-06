from __future__ import annotations

from pathlib import Path
from typing import Self

import pytest

from outreach.mail import DefiniteDeliveryError, GmailSMTPTransport, OutgoingEmail


class FakeSMTP:
    instance: FakeSMTP | None = None
    refuse = False

    def __init__(self, *args, **kwargs) -> None:
        self.login_args: tuple[str, str] | None = None
        self.message = None
        FakeSMTP.instance = self

    def __enter__(self) -> Self:
        return self

    def __exit__(self, *args) -> None:
        return None

    def login(self, address: str, password: str) -> None:
        self.login_args = (address, password)

    def send_message(self, message):
        self.message = message
        return {"bad@example.ai": (550, b"rejected")} if self.refuse else {}


def test_gmail_transport_builds_plain_text_message_with_pdf(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr("outreach.mail.smtplib.SMTP_SSL", FakeSMTP)
    resume = tmp_path / "resume.pdf"
    resume.write_bytes(b"%PDF fixture")
    transport = GmailSMTPTransport("candidate@gmail.com", "app-secret")

    message_id = transport.send(
        OutgoingEmail(
            sender="candidate@gmail.com",
            recipient="founder@example.ai",
            subject="AI Engineer",
            body="Hello",
            attachment_path=resume,
        )
    )

    assert message_id.startswith("<")
    assert FakeSMTP.instance is not None
    assert FakeSMTP.instance.login_args == ("candidate@gmail.com", "app-secret")
    assert FakeSMTP.instance.message["To"] == "founder@example.ai"
    assert any(part.get_filename() == "resume.pdf" for part in FakeSMTP.instance.message.walk())


def test_recipient_refusal_is_definite(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    FakeSMTP.refuse = True
    monkeypatch.setattr("outreach.mail.smtplib.SMTP_SSL", FakeSMTP)
    resume = tmp_path / "resume.pdf"
    resume.write_bytes(b"%PDF fixture")
    try:
        with pytest.raises(DefiniteDeliveryError, match="refused"):
            GmailSMTPTransport("candidate@gmail.com", "secret").send(
                OutgoingEmail(
                    sender="candidate@gmail.com",
                    recipient="bad@example.ai",
                    subject="AI Engineer",
                    body="Hello",
                    attachment_path=resume,
                )
            )
    finally:
        FakeSMTP.refuse = False
