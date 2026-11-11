"""HTTP tests for the demo service."""

import pytest
from flask.testing import FlaskClient


def test_health(client: FlaskClient) -> None:
    response = client.get("/health")
    assert response.status_code == 200
    assert response.get_json() == {"status": "ok"}


def test_get_existing_user(client: FlaskClient) -> None:
    response = client.get("/users/1")
    assert response.status_code == 200
    body = response.get_json()
    assert body["id"] == 1
    assert body["name"]
    assert "@" in body["email"]


@pytest.mark.parametrize("user_id", [0, 2, 999999])
def test_get_missing_user(client: FlaskClient, user_id: int) -> None:
    assert client.get(f"/users/{user_id}").status_code == 404


def test_search_by_prefix(client: FlaskClient) -> None:
    user = client.get("/users/1").get_json()
    matches = client.get("/users/search", query_string={"q": user["name"][:3]}).get_json()
    assert [m["id"] for m in matches] == [1]


def test_search_no_match(client: FlaskClient) -> None:
    assert client.get("/users/search", query_string={"q": "zzzz-no-such-user"}).get_json() == []
