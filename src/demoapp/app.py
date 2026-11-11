"""Flask application factory for the demo service."""

import logging

from flask import Flask, abort, jsonify
from flask.typing import ResponseReturnValue

from demoapp import db

logger = logging.getLogger(__name__)


def create_app(db_path: str) -> Flask:
    """Create the Flask app backed by the SQLite database at ``db_path``."""
    app = Flask(__name__)
    app.config["DB_PATH"] = db_path
    db.init_db(db_path)

    @app.get("/health")
    def health() -> ResponseReturnValue:
        return jsonify(status="ok")

    @app.get("/users/<int:user_id>")
    def get_user(user_id: int) -> ResponseReturnValue:
        user = db.get_user(app.config["DB_PATH"], user_id)
        if user is None:
            logger.info("User %s not found", user_id)
            abort(404)
        return jsonify(id=user.id, name=user.name, email=user.email)

    return app
