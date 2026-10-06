from __future__ import annotations

import argparse

from outreach.config import get_settings
from outreach.db import create_database_engine


def main() -> None:
    parser = argparse.ArgumentParser(prog="outreach")
    parser.add_argument("command", choices=["status"])
    args = parser.parse_args()
    if args.command == "status":
        settings = get_settings()
        engine = create_database_engine(settings.database_url)
        print(f"database={engine.url.render_as_string(hide_password=True)}")
        print(f"host={settings.app_host}:{settings.app_port}")
        print(f"resume_configured={bool(settings.resume_path)}")
        print(f"gmail_configured={bool(settings.gmail_address and settings.gmail_app_password)}")


if __name__ == "__main__":
    main()
