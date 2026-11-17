"""Application entry point: ``python -m demoapp.main``."""

import logging
import os

from dotenv import load_dotenv

from demoapp.app import create_app


def main() -> None:
    """Load environment configuration and start the local development server."""
    load_dotenv()
    logging.basicConfig(level=logging.INFO)
    db_path = os.environ.get("DEMOAPP_DB", "demoapp.sqlite3")
    accounting_url = os.environ.get("ACCOUNTING_URL", "https://accounting.internal.example/v1/exports")
    accounting_api_key = os.environ.get("ACCOUNTING_API_KEY", "placeholder")
    port = int(os.environ.get("PORT", "8080"))
    app = create_app(
        db_path=db_path,
        accounting_url=accounting_url,
        accounting_api_key=accounting_api_key,
    )
    app.run(host="127.0.0.1", port=port)


if __name__ == "__main__":
    main()
