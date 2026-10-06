# Architecture — AI Job Outreach MVP

> Planning document. Implementation is blocked until the Genesis plan is explicitly approved.

## Architecture outcome

Build one local Python application with server-rendered pages, a small command-line interface, Neon PostgreSQL, and direct Gmail SMTP/IMAP integration. Codex CLI performs web research and drafting outside the running application, then imports a strictly validated JSON bundle. The application never invokes an LLM API.

## Technology selection

The default stack is deliberately small and Python-first because the product targets an AI-engineering workflow:

- Python 3.12+
- FastAPI for local HTTP routes and form handling
- Jinja2 templates plus minimal vanilla JavaScript and CSS
- Pydantic for settings and import-bundle validation
- SQLAlchemy 2 and Alembic for Neon PostgreSQL
- Psycopg 3 PostgreSQL driver
- `pypdf` for local resume text extraction
- Python standard-library `smtplib`, `imaplib`, and `email` packages for Gmail
- Pytest for executable checks

Do not add a SPA framework, task queue, scheduler, cache, vector database, browser automation framework, or LLM SDK to the MVP. If the actual resume shows a materially better maintainable stack, record and approve that change before implementation.

## System boundary

```text
Public job/company sources
          |
          | read manually through Codex tools
          v
Codex CLI -> local run context -> validated JSON bundle
                                      |
                                      v
Local FastAPI app <------------> Neon PostgreSQL
       |                              structured records only
       |
       +-> local resume PDF
       |
       +-> Gmail SMTP (approved send only)
       +-> Gmail IMAP (manual reply sync only)
```

Codex may propose records; it cannot approve or send them. Web pages, job descriptions, bundle strings, and received email are untrusted data.

## Components

### Local web application

- Binds to `127.0.0.1` by default.
- Renders setup, opportunity, review, history, suppression, and health pages.
- Owns all state transitions and authorization checks.
- Does not expose Gmail credentials or database credentials to browser code.

### Application CLI

The package exposes these stable operations:

- `python -m outreach status`
- `python -m outreach resume import PATH`
- `python -m outreach prepare-context --limit 20 --output PATH`
- `python -m outreach bundle validate PATH`
- `python -m outreach bundle import PATH`
- `python -m outreach serve`
- `python -m outreach replies sync`

`prepare-context` produces a local, Git-ignored context file containing the confirmed profile, active settings, recent company/job identities, outreach cooldowns, replies, and suppressions needed by Codex. It never includes secrets.

### Bundle validator and importer

- Accepts one versioned JSON schema.
- Rejects more than 20 distinct companies.
- Validates URLs, timestamps, score arithmetic, evidence references, contact verification, draft claims, and canonical identities.
- Rechecks database eligibility inside the import transaction.
- Uses a caller-supplied run idempotency key.
- Commits all accepted records atomically or commits none.
- Creates only `pending_review`, rejected, or skipped records; never approvals or send attempts.

### Resume service

- Stores the original PDF beneath a configurable local data directory.
- Stores a content hash and version ID in Neon, not the binary.
- Extracts facts with page or text-span evidence.
- Requires the user to confirm extracted identity, signature, links, and facts.
- Never lets an unconfirmed profile generate a sendable draft.

### Matching service

Uses deterministic score components from the approved specification. Codex supplies evidence and proposed component scores; the importer recomputes totals, enforces ranges, and rejects missing evidence. The system does not claim that a numeric fit score is an objective hiring probability.

### Contact verification service

A recipient is `verified` only through one of these MVP paths:

1. The exact professional address appears on an official company or individual professional source, the domain relationship is valid, and the domain accepts mail; or
2. An optionally configured free verification provider returns its documented valid result and the contact identity/domain matches the researched company.

Syntax-only checks, guessed patterns, unsupported catch-all domains, scraped personal addresses, stale results, and unverifiable results remain blocked. Provider adapters are optional and must not weaken the public-evidence path.

### Approval service

- Computes a revision hash over recipient, subject, body, resume version, and attachment.
- Approval stores that hash and user timestamp.
- Any covered change invalidates approval.
- The send gate independently reloads the current database state and rechecks verification, suppression, cooldown, attachment, approval hash, and prior send idempotency.

### Gmail adapter

- Reads credentials from server-side environment settings.
- Sends sequentially with at least 30 seconds between attempts by default.
- Persists an attempt before contacting Gmail and records the Gmail message ID on success.
- Stops the batch on authentication or quota errors.
- Marks timeouts or uncertain responses `delivery_unknown`; never retries them automatically.
- Uses IMAP only during a user-triggered reply sync.

## Data ownership and storage

Neon is authoritative for structured state. The local filesystem is authoritative for the resume PDF and temporary Codex run bundles.

Core relationships:

- One resume version has many evidenced profile facts.
- One canonical company has many jobs, contacts, and outreach records.
- One discovery run may import at most 20 company candidates.
- One company candidate selects one primary job.
- One draft has many evidence-backed claims and zero or one current approval.
- One approved draft has at most one successful outreach message.
- Replies and suppressions attach to both recipient and canonical company when applicable.

Database constraints must enforce normalized email uniqueness, canonical job uniqueness, one candidate per company per run, one successful message per draft revision, and idempotent run/send keys.

## Security and privacy

- `.env`, `.local/`, resume files, preparation bundles, and test artifacts containing personal data are Git-ignored.
- `.env.example` contains variable names and safe placeholders only.
- Database TLS is mandatory.
- Templates escape untrusted text by default; sanitized plain text is preferred.
- Imported URLs allow only HTTP(S); fetching remains a Codex activity, preventing server-side request forgery in the app.
- Logs contain identifiers and safe status codes, not credentials, full email bodies, or resume content.
- Tests use fake Gmail and database adapters and can never address a real recipient.

## Failure and recovery model

- Import failure: roll back the transaction and return field-level errors.
- Stale opportunity: block approval/send until revalidated.
- Send failure before accepted delivery: record `failed`; require a new user decision before retry.
- Ambiguous delivery: record `delivery_unknown`; reconcile Sent Mail manually.
- Partial batch failure: preserve successes, stop where safety requires, and never replay successful entries.
- Interrupted Codex run: reuse the same run ID; database idempotency prevents duplicate import.

## Intended repository shape

```text
ai-job-outreach/
├── AGENTS.md
├── README.md
├── SPEC.md
├── ARCHITECTURE.md
├── CODEX_RUNBOOK.md
├── CODEX_BUILD_PROMPT.md
├── pyproject.toml
├── .env.example
├── alembic.ini
├── migrations/
├── src/outreach/
│   ├── __main__.py
│   ├── config.py
│   ├── db.py
│   ├── models.py
│   ├── schemas.py
│   ├── resume.py
│   ├── identity.py
│   ├── matching.py
│   ├── bundles.py
│   ├── verification.py
│   ├── approvals.py
│   ├── mail.py
│   ├── replies.py
│   ├── web.py
│   ├── templates/
│   └── static/
└── tests/
```

The file layout is a target, not permission to create unused abstractions. Combine modules when the implementation remains clear and testable.
