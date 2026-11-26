import re
import sqlite3

import pytest
from click.testing import CliRunner

from guided_notes import create_app
from guided_notes.config import ConfigurationError
from guided_notes.db import init_db
from guided_notes.errors import AppError
from guided_notes import notes
from guided_notes.notes import get_catalog, list_available_catalogs


def csrf_from(client, url="/"):
    response = client.get(url)
    match = re.search(rb'name="csrf_token" value="([^"]+)"', response.data)
    assert match, response.data
    return match.group(1).decode()


def create_teacher(app, username="teacher", password="safe-password"):
    runner = app.test_cli_runner()
    result = runner.invoke(args=["auth", "create-teacher", username], input=f"{password}\n{password}\n")
    assert result.exit_code == 0, result.output
    assert password not in result.output
    with app.app_context():
        return sqlite3.connect(app.config["DATABASE"]).execute(
            "SELECT id FROM teachers WHERE username = ?", (username,)
        ).fetchone()[0]


def test_factory_registers_all_blueprints_and_pages(client, app):
    assert {"notes", "activities", "quiz"}.issubset(app.blueprints)
    assert "教師登入" in client.get("/").get_data(as_text=True)
    assert "學生加入" in client.get("/").get_data(as_text=True)
    assert "尚未開放" in client.get("/").get_data(as_text=True)
    assert client.get("/notes/").status_code == 200
    assert client.get("/activities/").status_code == 200
    assert client.get("/quiz/").status_code == 200


@pytest.mark.parametrize("missing", ["GUIDED_NOTES_SECRET_KEY", "GUIDED_NOTES_DATABASE"])
def test_missing_required_environment_is_clear(monkeypatch, missing):
    monkeypatch.setenv("GUIDED_NOTES_SECRET_KEY", "sample")
    monkeypatch.setenv("GUIDED_NOTES_DATABASE", "sample.sqlite3")
    monkeypatch.delenv(missing)
    with pytest.raises(ConfigurationError, match=missing):
        create_app()


def test_google_paths_are_not_required_at_startup_and_checked_on_use(app):
    assert app
    from guided_notes.notes import google_credentials_paths

    with app.app_context(), pytest.raises(AppError) as error:
        google_credentials_paths()
    assert error.value.code == "GOOGLE_CREDENTIALS_REQUIRED"
    assert "NOTES_GOOGLE_CLIENT_SECRETS" in error.value.message
    assert "NOTES_GOOGLE_TOKEN" in error.value.message


def test_init_db_creates_schema_on_empty_database(app, tmp_path):
    database = tmp_path / "another-empty.sqlite3"
    app.config["DATABASE"] = str(database)
    runner = app.test_cli_runner()
    result = runner.invoke(args=["init-db"])
    assert result.exit_code == 0, result.output
    assert "初始化完成" in result.output
    with sqlite3.connect(database) as connection:
        tables = {row[0] for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    assert "teachers" in tables
    assert runner.invoke(args=["init-db"]).exit_code == 0


def test_create_teacher_prompts_twice_and_stores_hash(app):
    result = app.test_cli_runner().invoke(
        args=["auth", "create-teacher", "cli-teacher"], input="not-echoed-123\nnot-echoed-123\n"
    )
    assert result.exit_code == 0, result.output
    assert "not-echoed-123" not in result.output
    with app.app_context():
        row = sqlite3.connect(app.config["DATABASE"]).execute(
            "SELECT password_hash FROM teachers WHERE username = ?", ("cli-teacher",)
        ).fetchone()
    assert row and row[0] != "not-echoed-123"
    assert app.test_cli_runner().invoke(
        args=["auth", "create-teacher", "extra", "password"]
    ).exit_code != 0


def test_password_confirmation_mismatch_creates_no_row(app):
    result = app.test_cli_runner().invoke(
        args=["auth", "create-teacher", "mismatch"], input="first-pass\nsecond-pass\n"
    )
    assert result.exit_code != 0
    assert "兩次密碼不一致" in result.output
    with sqlite3.connect(app.config["DATABASE"]) as connection:
        assert connection.execute("SELECT COUNT(*) FROM teachers WHERE username='mismatch'").fetchone()[0] == 0


def test_login_wrong_password_is_generic_and_teacher_page_is_protected(client, app):
    protected = client.get("/teacher")
    assert protected.status_code == 302
    assert protected.headers["Location"].endswith("/login")
    create_teacher(app)
    token = csrf_from(client, "/login")
    invalid = client.post("/login", data={"csrf_token": token, "username": "teacher", "password": "wrong"})
    unknown = client.post("/login", data={"csrf_token": token, "username": "missing", "password": "wrong"})
    assert invalid.status_code == unknown.status_code == 401
    assert "帳號或密碼錯誤" in invalid.get_data(as_text=True)
    assert "帳號或密碼錯誤" in unknown.get_data(as_text=True)
    assert "LOGIN_FAILED" in invalid.get_data(as_text=True)
    assert "LOGIN_FAILED" in unknown.get_data(as_text=True)


def test_correct_login_and_logout(client, app):
    create_teacher(app)
    token = csrf_from(client, "/login")
    response = client.post(
        "/login", data={"csrf_token": token, "username": "teacher", "password": "safe-password"}
    )
    assert response.status_code == 302
    assert client.get("/teacher").status_code == 200
    logout_token = csrf_from(client, "/teacher")
    assert client.post("/logout", data={"csrf_token": logout_token}).status_code == 302
    assert client.get("/teacher").headers["Location"].endswith("/login")


def test_state_changes_require_csrf(client):
    missing = client.post("/logout")
    invalid = client.post("/logout", data={"csrf_token": "wrong"})
    assert missing.status_code == invalid.status_code == 400
    assert missing.json["error"]["code"] == "HTTP_400"
    assert "message" in missing.json["error"]


def test_unexpected_route_uses_common_error_format(client):
    response = client.get("/no-such-route")
    assert response.status_code == 404
    assert set(response.json["error"]) == {"code", "message"}


def test_catalog_demo_shape_and_teacher_scoped_api(app, monkeypatch):
    app.config["DEMO_CATALOG"] = True
    teacher_id = create_teacher(app, "demo-teacher-one")
    second_teacher_id = create_teacher(app, "demo-teacher-two")
    with app.app_context():
        summaries = list_available_catalogs(teacher_id)
        assert summaries == [{
            "import_id": "demo-guided-notes",
            "import_version": "1",
            "title": "示範用填空學習單",
            "question_count": 3,
        }]
        catalog = get_catalog(teacher_id, "demo-guided-notes", "1")
        assert list(catalog) == ["import_id", "import_version", "questions"]
        assert [question["display_number"] for question in catalog["questions"]] == ["1", "2", "3"]
        assert [question["type"] for question in catalog["questions"]] == ["group", "single", "single"]
        assert len(catalog["questions"][0]["items"]) == 2
        assert [item["order"] for item in catalog["questions"][0]["items"]] == [1, 2]
        assert all(len(question["items"]) == 1 for question in catalog["questions"][1:])
        for question in catalog["questions"]:
            assert {"question_id", "display_number", "type", "items"}.issubset(question)
            assert all({"item_id", "label", "order"}.issubset(item) for item in question["items"])
        # Demo catalog is shared among existing teachers.
        assert get_catalog(second_teacher_id, "demo-guided-notes", "1")["import_id"] == "demo-guided-notes"
        with pytest.raises(AppError) as error:
            get_catalog(99, "demo-guided-notes", "1")
        assert error.value.code == "TEACHER_REQUIRED"
        with pytest.raises(AppError) as error:
            list_available_catalogs(99)
        assert error.value.code == "TEACHER_REQUIRED"


def test_catalog_non_demo_filters_by_teacher_and_missing_catalog_error(app, monkeypatch):
    app.config["DEMO_CATALOG"] = False
    owner_id = create_teacher(app, "catalog-owner")
    other_id = create_teacher(app, "catalog-other")
    own_catalog = {
        "import_id": "teacher-10-catalog",
        "import_version": "v1",
        "title": "教師 10 的講義",
        "questions": [{
            "question_id": "q1",
            "display_number": "1",
            "type": "single",
            "items": [{"item_id": "i1", "label": "", "order": 1}],
        }],
    }
    monkeypatch.setattr(notes, "_catalogs_for_teacher", lambda teacher_id: [own_catalog] if teacher_id == owner_id else [])
    with app.app_context():
        assert list_available_catalogs(owner_id) == [{
            "import_id": "teacher-10-catalog",
            "import_version": "v1",
            "title": "教師 10 的講義",
            "question_count": 1,
        }]
        assert list_available_catalogs(other_id) == []
        assert get_catalog(owner_id, "teacher-10-catalog", "v1")["import_id"] == "teacher-10-catalog"
        with pytest.raises(AppError) as error:
            get_catalog(other_id, "teacher-10-catalog", "v1")
        assert error.value.code == "CATALOG_NOT_FOUND"


def test_app_error_handler_returns_code_and_message_json(client, app):
    def raise_app_error():
        raise AppError("SAMPLE_ERROR", "示範錯誤訊息。", 409)

    app.add_url_rule("/_test/app-error", view_func=raise_app_error)
    response = client.get("/_test/app-error")
    assert response.status_code == 409
    assert response.json == {"error": {"code": "SAMPLE_ERROR", "message": "示範錯誤訊息。"}}


def test_gitignore_covers_runtime_secrets_and_database():
    from pathlib import Path

    contents = Path(".gitignore").read_text(encoding="utf-8")
    assert ".env" in contents
    assert "*.sqlite3" in contents
    assert "instance/" in contents
    assert ".venv/" in contents
