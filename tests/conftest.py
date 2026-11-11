"""Shared fixtures."""

from collections.abc import Iterator
from pathlib import Path

import pytest
from faker import Faker
from flask import Flask
from flask.testing import FlaskClient

from demoapp import db
from demoapp.app import create_app


@pytest.fixture
def faker() -> Faker:
    """Deterministic fake data."""
    return Faker(seed=1234)


@pytest.fixture
def app(tmp_path: Path, faker: Faker) -> Iterator[Flask]:
    """App with a fresh database holding one user."""
    db_path = str(tmp_path / "test.sqlite3")
    application = create_app(db_path)
    db.add_user(db_path, faker.name(), faker.email())
    yield application


@pytest.fixture
def client(app: Flask) -> FlaskClient:
    """Test client for ``app``."""
    return app.test_client()
