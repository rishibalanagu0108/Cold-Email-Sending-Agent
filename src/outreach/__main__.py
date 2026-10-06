from __future__ import annotations

import argparse
import json
from pathlib import Path

import uvicorn
from sqlalchemy.orm import Session

from outreach.bundles import import_bundle, load_bundle
from outreach.config import get_settings
from outreach.context import build_preparation_context
from outreach.db import create_database_engine
from outreach.resume import import_resume
from outreach.web import create_app


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="outreach")
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("status")
    commands.add_parser("serve")

    resume = commands.add_parser("resume")
    resume_commands = resume.add_subparsers(dest="resume_command", required=True)
    resume_import = resume_commands.add_parser("import")
    resume_import.add_argument("path", type=Path)

    context = commands.add_parser("prepare-context")
    context.add_argument("--limit", type=int, default=20)
    context.add_argument("--output", type=Path, required=True)

    bundle = commands.add_parser("bundle")
    bundle_commands = bundle.add_subparsers(dest="bundle_command", required=True)
    for name in ("validate", "import"):
        child = bundle_commands.add_parser(name)
        child.add_argument("path", type=Path)
    return parser


def main() -> None:
    args = build_parser().parse_args()
    settings = get_settings()
    engine = create_database_engine(settings.database_url)

    if args.command == "status":
        print(f"database={engine.url.render_as_string(hide_password=True)}")
        print(f"host={settings.app_host}:{settings.app_port}")
        print(f"resume_configured={bool(settings.resume_path)}")
        print(f"gmail_configured={bool(settings.gmail_address and settings.gmail_app_password)}")
        return

    if args.command == "serve":
        uvicorn.run(create_app(engine, settings), host=settings.app_host, port=settings.app_port)
        return

    with Session(engine) as session:
        if args.command == "resume":
            version = import_resume(session, args.path, settings.local_data_dir)
            session.commit()
            print(json.dumps({"resume_version_id": version.id, "confirmed": version.confirmed}))
            return

        if args.command == "prepare-context":
            payload = build_preparation_context(session, args.limit)
            output = args.output.resolve()
            output.parent.mkdir(parents=True, exist_ok=True)
            output.write_text(json.dumps(payload, indent=2), encoding="utf-8")
            print(json.dumps({"output": str(output), "limit": args.limit}))
            return

        prepared = load_bundle(args.path)
        if args.bundle_command == "validate":
            print(
                json.dumps(
                    {
                        "valid": True,
                        "eligible": sum(
                            candidate.status == "eligible" for candidate in prepared.candidates
                        ),
                    }
                )
            )
            return
        result = import_bundle(session, prepared)
        print(result.model_dump_json())


if __name__ == "__main__":
    main()
