"""Entry point: ``python -m demoapp.main``."""

import logging
import os

from dotenv import load_dotenv

from demoapp.app import create_app


def main() -> None:
    """Run the development server."""
    load_dotenv()
    logging.basicConfig(level=logging.INFO)
    app = create_app(os.environ.get("DEMOAPP_DB", "demoapp.sqlite3"))
    app.run(host="127.0.0.1", port=int(os.environ.get("PORT", "8080")))


if __name__ == "__main__":
    main()
