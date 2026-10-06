from __future__ import annotations

import imaplib
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from email import message_from_bytes, policy
from email.message import Message
from email.utils import parseaddr, parsedate_to_datetime

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from outreach.config import Settings
from outreach.models import Contact, OutreachMessage, Reply, Suppression
from outreach.verification import normalize_email

OPT_OUT_PHRASES = (
    "do not contact",
    "don't contact",
    "stop contacting",
    "remove me",
    "unsubscribe",
)
REJECTION_PHRASES = (
    "not moving forward",
    "position has been filled",
    "role has been filled",
    "not a fit",
    "not interested",
)


@dataclass(frozen=True)
class InboundReply:
    gmail_message_id: str
    in_reply_to: str | None
    references: tuple[str, ...]
    sender: str
    subject: str
    body: str
    received_at: datetime


class GmailIMAPReader:
    def __init__(self, address: str, app_password: str, timeout: float = 30) -> None:
        self.address = address
        self.app_password = app_password
        self.timeout = timeout

    @classmethod
    def from_settings(cls, settings: Settings) -> GmailIMAPReader:
        if not settings.gmail_address or not settings.gmail_app_password:
            raise ValueError("Gmail address and app password are required")
        return cls(settings.gmail_address, settings.gmail_app_password)

    def fetch(self, *, since_days: int = 90, limit: int = 500) -> list[InboundReply]:
        since = (datetime.now(UTC) - timedelta(days=since_days)).strftime("%d-%b-%Y")
        replies: list[InboundReply] = []
        with imaplib.IMAP4_SSL("imap.gmail.com", 993, timeout=self.timeout) as client:
            client.login(self.address, self.app_password)
            client.select("INBOX", readonly=True)
            status, data = client.search(None, "SINCE", since)
            if status != "OK":
                raise RuntimeError("Gmail inbox search failed")
            message_numbers = data[0].split()[-limit:]
            for number in message_numbers:
                fetch_status, payload = client.fetch(number, "(RFC822)")
                if fetch_status != "OK" or not payload or not isinstance(payload[0], tuple):
                    continue
                parsed = message_from_bytes(payload[0][1], policy=policy.default)
                inbound = _to_inbound(parsed)
                if inbound:
                    replies.append(inbound)
        return replies


def classify_reply(body: str) -> str:
    normalized = " ".join(body.lower().split())
    if any(phrase in normalized for phrase in OPT_OUT_PHRASES):
        return "opt_out"
    if any(phrase in normalized for phrase in REJECTION_PHRASES):
        return "rejected"
    return "replied"


def sync_replies(session: Session, inbound: Iterable[InboundReply]) -> dict[str, int]:
    counts = {"matched": 0, "suppressed": 0, "unmatched": 0, "duplicate": 0}
    for item in inbound:
        if session.scalar(select(Reply).where(Reply.gmail_message_id == item.gmail_message_id)):
            counts["duplicate"] += 1
            continue
        thread_ids = {value for value in (*item.references, item.in_reply_to) if value}
        outreach = (
            session.scalar(
                select(OutreachMessage).where(OutreachMessage.gmail_message_id.in_(thread_ids))
            )
            if thread_ids
            else None
        )
        if not outreach:
            counts["unmatched"] += 1
            continue
        classification = classify_reply(item.body)
        reply = Reply(
            outreach_message_id=outreach.id,
            gmail_message_id=item.gmail_message_id,
            classification=classification,
            received_at=item.received_at,
        )
        session.add(reply)
        outreach.status = "replied"
        counts["matched"] += 1
        if classification in {"opt_out", "rejected"}:
            contact = session.get_one(Contact, outreach.contact_id)
            existing = session.scalar(
                select(Suppression).where(
                    Suppression.company_id == outreach.company_id,
                    or_(
                        Suppression.normalized_email == contact.normalized_email,
                        Suppression.normalized_email.is_(None),
                    ),
                    Suppression.permanent.is_(True),
                )
            )
            if not existing:
                session.add(
                    Suppression(
                        company_id=outreach.company_id,
                        normalized_email=contact.normalized_email,
                        reason=classification,
                        permanent=True,
                    )
                )
                counts["suppressed"] += 1
    session.commit()
    return counts


def _to_inbound(message: Message) -> InboundReply | None:
    message_id = message.get("Message-ID")
    if not message_id:
        return None
    body = _plain_body(message)
    date_header = message.get("Date")
    try:
        received_at = (
            parsedate_to_datetime(date_header).astimezone(UTC) if date_header else datetime.now(UTC)
        )
    except (TypeError, ValueError):
        received_at = datetime.now(UTC)
    references = tuple((message.get("References") or "").split())
    return InboundReply(
        gmail_message_id=message_id.strip(),
        in_reply_to=(message.get("In-Reply-To") or "").strip() or None,
        references=references,
        sender=normalize_email(parseaddr(message.get("From") or "")[1]),
        subject=message.get("Subject") or "",
        body=body,
        received_at=received_at,
    )


def _plain_body(message: Message) -> str:
    if message.is_multipart():
        for part in message.walk():
            if part.get_content_type() == "text/plain" and not part.get_filename():
                return str(part.get_content())
        return ""
    return str(message.get_content())
