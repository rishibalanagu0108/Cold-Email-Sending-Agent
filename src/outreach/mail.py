from __future__ import annotations

import hashlib
import smtplib
import ssl
import time
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from email.message import EmailMessage
from email.utils import make_msgid
from pathlib import Path
from typing import Protocol

from sqlalchemy import select
from sqlalchemy.orm import Session

from outreach.config import Settings
from outreach.foundation import company_eligibility
from outreach.models import (
    Approval,
    Contact,
    ContactVerification,
    Draft,
    Job,
    JobMatch,
    OutreachMessage,
    ResumeVersion,
    SendBatch,
)


class DeliveryError(RuntimeError):
    pass


class DefiniteDeliveryError(DeliveryError):
    pass


class AmbiguousDeliveryError(DeliveryError):
    pass


@dataclass(frozen=True)
class OutgoingEmail:
    sender: str
    recipient: str
    subject: str
    body: str
    attachment_path: Path


class MailTransport(Protocol):
    def send(self, outgoing: OutgoingEmail) -> str: ...


class GmailSMTPTransport:
    def __init__(self, address: str, app_password: str, timeout: float = 30) -> None:
        self.address = address
        self.app_password = app_password
        self.timeout = timeout

    @classmethod
    def from_settings(cls, settings: Settings) -> GmailSMTPTransport:
        if not settings.gmail_address or not settings.gmail_app_password:
            raise ValueError("Gmail address and app password are required")
        return cls(settings.gmail_address, settings.gmail_app_password.get_secret_value())

    def send(self, outgoing: OutgoingEmail) -> str:
        message_id = make_msgid(domain=self.address.rsplit("@", 1)[-1])
        message = EmailMessage()
        message["From"] = outgoing.sender
        message["To"] = outgoing.recipient
        message["Subject"] = outgoing.subject
        message["Message-ID"] = message_id
        message.set_content(outgoing.body)
        content = outgoing.attachment_path.read_bytes()
        message.add_attachment(
            content,
            maintype="application",
            subtype="pdf",
            filename=outgoing.attachment_path.name,
        )
        try:
            with smtplib.SMTP_SSL(
                "smtp.gmail.com", 465, context=ssl.create_default_context(), timeout=self.timeout
            ) as smtp:
                smtp.login(self.address, self.app_password)
                refused = smtp.send_message(message)
                if refused:
                    raise DefiniteDeliveryError("Gmail refused one or more recipients")
        except (smtplib.SMTPAuthenticationError, smtplib.SMTPRecipientsRefused) as exc:
            raise DefiniteDeliveryError(type(exc).__name__) from exc
        except smtplib.SMTPResponseException as exc:
            error = DefiniteDeliveryError if exc.smtp_code >= 500 else AmbiguousDeliveryError
            raise error(f"SMTP {exc.smtp_code}") from exc
        except (OSError, smtplib.SMTPException) as exc:
            raise AmbiguousDeliveryError(type(exc).__name__) from exc
        return message_id


@dataclass(frozen=True)
class SendResult:
    batch_id: str
    sent: int
    failed: int
    blocked: int
    delivery_unknown: int


def send_approved_batch(
    session: Session,
    draft_ids: list[str],
    *,
    sender: str,
    transport: MailTransport,
    batch_key: str,
    at: datetime | None = None,
    pace_seconds: float = 30,
    sleep=time.sleep,
) -> SendResult:
    unique_ids = list(dict.fromkeys(draft_ids))
    if not unique_ids or len(unique_ids) > 20:
        raise ValueError("Select between 1 and 20 drafts")
    now = _aware(at or datetime.now(UTC))
    existing_batch = session.scalar(select(SendBatch).where(SendBatch.idempotency_key == batch_key))
    if existing_batch:
        return _summarize_batch(session, existing_batch.id)

    batch = SendBatch(idempotency_key=batch_key, status="sending")
    session.add(batch)
    session.commit()
    counts = {"sent": 0, "failed": 0, "blocked": 0, "delivery_unknown": 0}

    for index, draft_id in enumerate(unique_ids):
        try:
            draft, approval, contact, resume, job, company_id = _sendable(session, draft_id, now)
        except ValueError:
            counts["blocked"] += 1
            continue

        message_key = hashlib.sha256(f"{draft.id}:{draft.revision_hash}".encode()).hexdigest()
        attempt = session.scalar(
            select(OutreachMessage).where(OutreachMessage.idempotency_key == message_key)
        )
        if attempt and attempt.status in {"sending", "sent", "delivery_unknown"}:
            counts["blocked"] += 1
            continue
        if attempt and _aware(approval.approved_at) <= _aware(attempt.updated_at):
            counts["blocked"] += 1
            continue
        if not attempt:
            attempt = OutreachMessage(
                batch_id=batch.id,
                company_id=company_id,
                job_id=job.id,
                contact_id=contact.id,
                draft_id=draft.id,
                approval_id=approval.id,
                idempotency_key=message_key,
                status="sending",
            )
            session.add(attempt)
        else:
            attempt.batch_id = batch.id
            attempt.approval_id = approval.id
            attempt.status = "sending"
            attempt.error_code = None
        session.commit()

        outgoing = OutgoingEmail(
            sender=sender,
            recipient=contact.normalized_email,
            subject=draft.subject,
            body=draft.body,
            attachment_path=Path(resume.local_path),
        )
        try:
            gmail_message_id = transport.send(outgoing)
        except DefiniteDeliveryError as exc:
            attempt.status = "failed"
            attempt.error_code = str(exc)[:100]
            draft.status = "pending_review"
            counts["failed"] += 1
            session.commit()
            continue
        except AmbiguousDeliveryError as exc:
            attempt.status = "delivery_unknown"
            attempt.error_code = str(exc)[:100]
            batch.status = "delivery_unknown"
            counts["delivery_unknown"] += 1
            session.commit()
            break

        attempt.status = "sent"
        attempt.gmail_message_id = gmail_message_id
        attempt.sent_at = now
        draft.status = "sent"
        counts["sent"] += 1
        session.commit()
        if index < len(unique_ids) - 1 and pace_seconds:
            sleep(pace_seconds)

    if batch.status != "delivery_unknown":
        batch.status = "completed" if counts["failed"] == 0 else "partial_failure"
        session.commit()
    return SendResult(batch_id=batch.id, **counts)


def _sendable(
    session: Session, draft_id: str, now: datetime
) -> tuple[Draft, Approval, Contact, ResumeVersion, Job, str]:
    draft = session.get(Draft, draft_id)
    if not draft or draft.status != "approved":
        raise ValueError("Draft is not approved")
    approval = session.scalar(
        select(Approval)
        .where(Approval.draft_id == draft.id, Approval.revision_hash == draft.revision_hash)
        .order_by(Approval.approved_at.desc())
        .limit(1)
    )
    if not approval:
        raise ValueError("Current draft revision is not approved")
    contact = session.get_one(Contact, draft.contact_id)
    verification = session.scalar(
        select(ContactVerification)
        .where(ContactVerification.contact_id == contact.id)
        .order_by(ContactVerification.verified_at.desc())
        .limit(1)
    )
    if (
        not contact.professional
        or not verification
        or verification.status != "verified"
        or now - _aware(verification.verified_at) > timedelta(days=30)
    ):
        raise ValueError("Contact verification is not current")
    resume = session.get_one(ResumeVersion, draft.resume_version_id)
    if not resume.confirmed or not Path(resume.local_path).is_file():
        raise ValueError("Resume attachment is unavailable")
    match = session.get_one(JobMatch, draft.job_match_id)
    job = session.get_one(Job, match.job_id)
    eligibility = company_eligibility(session, match.company_id, job.fingerprint, at=now)
    if not eligibility.eligible:
        raise ValueError(eligibility.reason or "Company is not eligible")
    return draft, approval, contact, resume, job, match.company_id


def _summarize_batch(session: Session, batch_id: str) -> SendResult:
    messages = session.scalars(
        select(OutreachMessage).where(OutreachMessage.batch_id == batch_id)
    ).all()
    counts = {"sent": 0, "failed": 0, "blocked": 0, "delivery_unknown": 0}
    for message in messages:
        if message.status in counts:
            counts[message.status] += 1
    return SendResult(batch_id=batch_id, **counts)


def _aware(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)
