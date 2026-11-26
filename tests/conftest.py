import pytest

from guided_notes import create_app
from guided_notes.db import init_db


@pytest.fixture
def app(tmp_path, monkeypatch):
    database = tmp_path / "fresh-test.sqlite3"
    monkeypatch.setenv("GUIDED_NOTES_SECRET_KEY", "pytest-only-random-example")
    monkeypatch.setenv("GUIDED_NOTES_DATABASE", str(database))
    monkeypatch.delenv("NOTES_GOOGLE_CLIENT_SECRETS", raising=False)
    monkeypatch.delenv("NOTES_GOOGLE_TOKEN", raising=False)
    monkeypatch.delenv("GUIDED_NOTES_DEMO_CATALOG", raising=False)
    application = create_app({"TESTING": True})
    with application.app_context():
        init_db()
    yield application


@pytest.fixture
def client(app):
    return app.test_client()
