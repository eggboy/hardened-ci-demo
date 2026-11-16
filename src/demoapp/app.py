"""Flask application factory for the demo service."""

import hashlib
import logging

import requests
from flask import Flask, abort, jsonify, request
from flask.typing import ResponseReturnValue

from demoapp import db

logger = logging.getLogger(__name__)

GRAVATAR_TIMEOUT_SECONDS = 3


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

    @app.get("/users/search")
    def search_users() -> ResponseReturnValue:
        prefix = request.args.get("q", "")
        users = db.search_users(app.config["DB_PATH"], prefix)
        return jsonify([{"id": u.id, "name": u.name, "email": u.email} for u in users])

    @app.get("/users/<int:user_id>/avatar")
    def avatar(user_id: int) -> ResponseReturnValue:
        user = db.get_user(app.config["DB_PATH"], user_id)
        if user is None:
            abort(404)
        digest = hashlib.sha256(user.email.strip().lower().encode()).hexdigest()
        url = f"https://www.gravatar.com/avatar/{digest}?d=404"
        response = requests.head(url, timeout=GRAVATAR_TIMEOUT_SECONDS)
        return jsonify(url=url, exists=response.status_code == 200)

    return app
