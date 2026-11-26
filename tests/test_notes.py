from dataclasses import replace
import json
import sqlite3
from unittest.mock import Mock

import pytest
from google.auth.exceptions import RefreshError
from googleapiclient.errors import HttpError
from httplib2 import Response

from guided_notes.db import get_db
from guided_notes.errors import AppError
from guided_notes.notes import get_catalog, list_available_catalogs
from guided_notes.notes_format import Merge, SheetGrid, parse_layout
from guided_notes.notes_sheets import GoogleSheets, source_from_link
from guided_notes.notes_writeback import Answer, EndedSnapshot, QuestionResult


def _cell(text):
    return {"userEnteredValue": {"stringValue": text}, "formattedValue": text}


def _layout(row=0, col=0):
    cells = {
        (0, 0): _cell(" 題號 "), (0, 1): _cell("題目"), (0, 3): _cell("作答 "),
        (1, 0): _cell("01"), (1, 1): _cell("單題文字"),
        (2, 0): _cell("3"), (2, 1): _cell("題組第一小題文字"), (2, 3): _cell("（1）"),
        (3, 1): _cell("題組第二小題文字"), (3, 3): _cell("(2)"),
        (4, 3): _cell("此列不屬於題組"),
    }
    merges = [
        Merge(0, 1, 1, 3), Merge(0, 3, 1, 6),
        Merge(1, 3, 2, 6), Merge(2, 0, 4, 1),
        Merge(2, 4, 3, 6), Merge(3, 4, 4, 6),
    ]
    return SheetGrid(
        "第一分頁",
        {(r + row, c + col): cell for (r, c), cell in cells.items()},
        [Merge(m.row + row, m.column + col, m.end_row + row, m.end_column + col) for m in merges],
    )


class FakeSheets:
    def __init__(self):
        self.grid = _layout()
        self.tab_list = [{"sheetId": 0, "title": self.grid.title}]
        self.reads = []
        self.writes = []
        self.mode = "normal"

    def tabs(self, spreadsheet_id):
        assert spreadsheet_id == "sheet-id"
        return self.tab_list

    def read(self, spreadsheet_id, sheet_id):
        self.reads.append((spreadsheet_id, sheet_id))
        assert spreadsheet_id == "sheet-id"
        if self.mode == "readback_auth" and self.writes:
            raise AppError("SHEETS_AUTH_REQUIRED", "請重新授權。", 401)
        return self.grid

    def write(self, spreadsheet_id, sheet_id, targets):
        assert (spreadsheet_id, sheet_id) == ("sheet-id", 0)
        self.writes.append([(entry["row"], entry["column"], entry["answer"]) for entry in targets])
        if self.mode == "partial":
            first = targets[0]
            self.grid.cells[first["row"], first["column"]] = _cell(first["answer"])
            raise AppError("SHEETS_WRITE_UNVERIFIED", "傳輸中斷", 502)
        for target in targets:
            answer = "不相符" if self.mode == "mismatch" else target["answer"]
            self.grid.cells[target["row"], target["column"]] = _cell(answer)


@pytest.fixture
def notes_case(app, client):
    with app.app_context(), get_db() as db:
        teacher_id = db.execute(
            "INSERT INTO teachers (username, password_hash) VALUES (?, ?)", ("first", "fixture")
        ).lastrowid
        other_id = db.execute(
            "INSERT INTO teachers (username, password_hash) VALUES (?, ?)", ("second", "fixture")
        ).lastrowid
    with client.session_transaction() as session:
        session.update(teacher_id=teacher_id, csrf_token="notes-fixture")
    sheets = FakeSheets()
    app.config.update(
        DEMO_CATALOG=False,
        NOTES_SHEETS_FACTORY=lambda: sheets,
        NOTES_COURSE_ACCESS=lambda actor, course: (
            (actor == teacher_id and course in {"course", "another"}) or (actor == other_id and course == "other")
        ),
    )
    return teacher_id, other_id, sheets


def _post(client, action, course="course", **data):
    return client.post(f"/notes/courses/{course}/{action}", json=data, headers={"X-CSRF-Token": "notes-fixture"})


def _save(client, course="course"):
    preview = _post(client, "import/preview", course, source="sheet-id").json["import_review"]
    return _post(client, "import/save", course, preview_id=preview["preview_id"]).json["saved_version"]


def _snapshot(teacher_id, version):
    return EndedSnapshot(
        "event", teacher_id, version["import_id"], version["import_version"], True, True,
        (
            QuestionResult("q-1", None),
            QuestionResult("q-3", "winner", (
                Answer("q-3-item-2", "=literal"), Answer("q-3-item-1", "(2)"),
            )),
        ),
    )


def test_layout_tracks_semantic_ids_and_merged_targets():
    questions = parse_layout(_layout(7, 5))
    single, group = questions
    assert single["display_number"] == "01"
    assert single["question_id"] == "q-1"
    assert single["type"] == "single"
    assert single["items"][0]["column"] == 8
    assert group["type"] == "group"
    assert [(item["label"], item["row"], item["column"]) for item in group["items"]] == [
        ("（1）", 9, 9), ("(2)", 10, 9),
    ]
    assert group["source_text"][0] == "題組第一小題文字"
    assert [item["source_text"][0] for item in group["items"]] == ["題組第一小題文字", "題組第二小題文字"]


@pytest.mark.parametrize("change", ["missing_header", "duplicate_header", "ambiguous_answer", "duplicate_number", "duplicate_label"])
def test_parser_rejects_ambiguous_sources(change):
    grid = _layout()
    if change == "missing_header":
        del grid.cells[0, 1]
    elif change == "duplicate_header":
        grid.cells[0, 6] = _cell("作答")
    elif change == "ambiguous_answer":
        grid.merges.remove(Merge(2, 4, 3, 6))
    elif change == "duplicate_number":
        grid.cells[4, 0] = _cell("1")
    else:
        grid.cells[3, 3] = _cell("(1)")
    with pytest.raises(AppError, match="題|表頭") as error:
        parse_layout(grid)
    assert error.value.code == "NOTES_FORMAT_INVALID"


def test_single_cell_layout_without_merge():
    grid = SheetGrid("單題", {(3, 0): _cell("題號"), (3, 2): _cell("題目"), (3, 7): _cell("作答"),
                              (4, 0): _cell("2"), (6, 0): _cell("5")}, [])
    result = parse_layout(grid)
    assert [question["display_number"] for question in result] == ["2", "5"]
    assert [question["items"][0]["column"] for question in result] == [7, 7]


def test_import_preview_is_private_and_version_round_trip(app, client, notes_case):
    teacher_id, other_id, sheets = notes_case
    sheets.grid.cells[1, 3] = _cell("來源舊答案")
    preview = _post(client, "import/preview", source="sheet-id", title="自訂講義").json["import_review"]
    assert (preview["question_count"], preview["submission_count"], preview["item_count"]) == (2, 2, 3)
    assert "來源舊答案" not in json.dumps(preview, ensure_ascii=False)
    with app.app_context():
        assert list_available_catalogs(teacher_id) == []
    version = _post(client, "import/save", preview_id=preview["preview_id"]).json["saved_version"]
    assert _post(client, "import/save", preview_id=preview["preview_id"]).json["saved_version"] == version
    with app.app_context():
        original = get_catalog(teacher_id, version["import_id"], "1")
        assert list_available_catalogs(teacher_id) == [{**version, "title": "自訂講義", "question_count": 2}]
        assert list_available_catalogs(other_id) == []
        assert set(original) == {"import_id", "import_version", "questions"}
        assert set(original["questions"][0]) == {"question_id", "display_number", "type", "items"}
        assert original["questions"][0]["items"] == [{"item_id": "q-1-item-1", "label": "", "order": 1}]
        assert [item["order"] for item in original["questions"][1]["items"]] == [1, 2]
    sheets.grid = _layout(5, 5)
    assert _save(client) == {**version, "import_version": "2"}
    with app.app_context():
        assert get_catalog(teacher_id, version["import_id"], "1") == original
        assert get_catalog(teacher_id, version["import_id"], "2")["questions"] == original["questions"]
        hidden = []
        for actor, version_key in [(other_id, "1"), (teacher_id, "unknown"), (teacher_id, "01")]:
            with pytest.raises(AppError) as error:
                get_catalog(actor, version["import_id"], version_key)
            hidden.append((error.value.code, error.value.status_code, error.value.message))
        assert len(set(hidden)) == 1 and hidden[0][:2] == ("CATALOG_NOT_FOUND", 404)
        assert len(list_available_catalogs(teacher_id)) == 2
        for lookup in (lambda: list_available_catalogs(999), lambda: get_catalog(999, version["import_id"], "1")):
            with pytest.raises(AppError) as error:
                lookup()
            assert (error.value.code, error.value.status_code) == ("TEACHER_REQUIRED", 401)


def test_import_multiple_tabs_and_course_permissions(app, client, notes_case):
    teacher_id, _, sheets = notes_case
    sheets.tab_list.append({"sheetId": 7, "title": "另一分頁"})
    tabs = _post(client, "import/preview", source="sheet-id").json["tabs"]
    assert [tab["sheetId"] for tab in tabs] == [0, 7]
    assert not sheets.reads
    preview = _post(client, "import/preview", source="sheet-id", sheet_id=7).json["import_review"]
    assert sheets.reads[-1] == ("sheet-id", 7)
    assert _post(client, "import/save", "another", preview_id=preview["preview_id"]).status_code == 404
    assert _post(client, "import/preview", "other", source="sheet-id").status_code == 403
    assert client.post("/notes/courses/course/import/save", json={"preview_id": preview["preview_id"]}).status_code == 400
    assert _post(client, "import/save", preview_id=preview["preview_id"]).status_code == 200
    with app.app_context():
        assert len(list_available_catalogs(teacher_id)) == 1
    app.config.pop("NOTES_COURSE_ACCESS")
    assert _post(client, "import/preview", source="sheet-id").status_code == 503


def test_notes_session_csrf_and_legacy_database(app, client, notes_case, tmp_path):
    from guided_notes.db import init_db

    teacher_id, _, _ = notes_case
    assert client.get("/notes/").status_code == 200
    rendered = client.post("/notes/courses/course/import/preview", data={"csrf_token": "notes-fixture", "source": "sheet-id"})
    assert "保存講義版本" in rendered.get_data(as_text=True)
    with app.app_context():
        init_db()
        init_db()
        assert get_db().execute("SELECT count(*) FROM teachers").fetchone()[0] == 2
        assert list_available_catalogs(teacher_id) == []
    with client.session_transaction() as session:
        session["teacher_id"] = 999
    assert client.get("/notes/courses/course").status_code == 401
    with client.session_transaction() as session:
        session.clear()
    assert client.get("/notes/courses/course").headers["Location"].endswith("/login")

    legacy = tmp_path / "foundation-only.sqlite3"
    with sqlite3.connect(legacy) as connection:
        connection.executescript("""
            CREATE TABLE teachers (id INTEGER PRIMARY KEY, username TEXT NOT NULL, password_hash TEXT NOT NULL);
            INSERT INTO teachers VALUES (1, 'legacy-teacher', 'fixture');
        """)
    app.config["DATABASE"] = str(legacy)
    with app.app_context():
        init_db()
        init_db()
        assert get_db().execute("SELECT username FROM teachers WHERE id = 1").fetchone()[0] == "legacy-teacher"
        assert list_available_catalogs(1) == []


def test_failed_save_rolls_back_version(app, client, notes_case):
    teacher_id, _, _ = notes_case
    preview = _post(client, "import/preview", source="sheet-id").json["import_review"]
    with app.app_context(), get_db() as db:
        db.execute(
            """CREATE TRIGGER reject_save BEFORE UPDATE ON notes_import_previews
               BEGIN SELECT RAISE(ABORT, 'test failure'); END"""
        )
    assert _post(client, "import/save", preview_id=preview["preview_id"]).status_code == 500
    with app.app_context(), get_db() as db:
        assert list_available_catalogs(teacher_id) == []
        db.execute("DROP TRIGGER reject_save")
    assert _post(client, "import/save", preview_id=preview["preview_id"]).json["saved_version"]["import_version"] == "1"


def test_writeback_reconfirms_moved_source_and_only_writes_winner(app, client, notes_case):
    teacher_id, _, sheets = notes_case
    version = _save(client)
    snapshot = _snapshot(teacher_id, version)
    app.config["NOTES_ENDED_SNAPSHOT"] = lambda *_: snapshot
    review = _post(client, "writeback/preview", activity_id="event").json["writeback_review"]
    assert not sheets.writes
    sheets.grid = _layout(5, 3)
    changed = _post(client, "writeback/confirm", activity_id="event", preview_id=review["preview_id"])
    assert changed.status_code == 409
    recheck = changed.json["writeback_review"]
    assert recheck["status"] == "source_changed" and not sheets.writes
    assert _post(client, "writeback/confirm", activity_id="event", preview_id=review["preview_id"]).status_code == 409
    confirmed = _post(client, "writeback/confirm", activity_id="event", preview_id=recheck["preview_id"])
    result = confirmed.json["writeback_review"]
    assert result["status"] == "verified" and result["skipped_count"] == 1
    assert sheets.writes == [[(7, 7, "(2)"), (8, 7, "=literal")]]
    assert sheets.grid.text(7, 6) == "（1）"
    assert not sheets.grid.entered(6, 6)
    assert _post(client, "writeback/confirm", activity_id="event", preview_id=recheck["preview_id"]).status_code == 200
    assert len(sheets.writes) == 1


def test_writeback_partial_failure_then_safe_retry(app, client, notes_case):
    teacher_id, _, sheets = notes_case
    app.config["NOTES_ENDED_SNAPSHOT"] = lambda *_: snapshot
    snapshot = _snapshot(teacher_id, _save(client))
    review = _post(client, "writeback/preview", activity_id="event").json["writeback_review"]
    sheets.mode = "partial"
    partial = _post(client, "writeback/confirm", activity_id="event", preview_id=review["preview_id"])
    assert partial.status_code == 502
    assert [target["status"] for target in partial.json["writeback_review"]["targets"]] == ["verified", "unverified"]
    sheets.mode = "normal"
    retried = _post(client, "writeback/confirm", activity_id="event", preview_id=review["preview_id"])
    assert retried.json["writeback_review"]["status"] == "verified"
    assert sheets.writes[-1] == [(3, 4, "=literal")]


def test_writeback_readback_conflict_wont_overwrite_on_retry(app, client, notes_case):
    teacher_id, _, sheets = notes_case
    snapshot = _snapshot(teacher_id, _save(client))
    app.config["NOTES_ENDED_SNAPSHOT"] = lambda *_: snapshot
    review = _post(client, "writeback/preview", activity_id="event").json["writeback_review"]
    sheets.mode = "mismatch"
    first = _post(client, "writeback/confirm", activity_id="event", preview_id=review["preview_id"])
    assert first.status_code == 409 and first.json["writeback_review"]["status"] == "conflict"
    retry = _post(client, "writeback/confirm", activity_id="event", preview_id=review["preview_id"])
    assert retry.status_code == 409 and len(sheets.writes) == 1


def test_writeback_does_not_rewrite_a_verified_cell_cleared_by_a_teacher(app, client, notes_case):
    teacher_id, _, sheets = notes_case
    snapshot = _snapshot(teacher_id, _save(client))
    app.config["NOTES_ENDED_SNAPSHOT"] = lambda *_: snapshot
    review = _post(client, "writeback/preview", activity_id="event").json["writeback_review"]
    assert _post(client, "writeback/confirm", activity_id="event", preview_id=review["preview_id"]).status_code == 200
    del sheets.grid.cells[2, 4]
    retry = _post(client, "writeback/confirm", activity_id="event", preview_id=review["preview_id"])
    assert retry.status_code == 409
    assert [item["status"] for item in retry.json["writeback_review"]["targets"]] == ["conflict", "verified"]
    assert len(sheets.writes) == 1


def test_writeback_lost_readback_reports_auth_and_rechecks_without_rewrite(app, client, notes_case):
    teacher_id, _, sheets = notes_case
    snapshot = _snapshot(teacher_id, _save(client))
    app.config["NOTES_ENDED_SNAPSHOT"] = lambda *_: snapshot
    review = _post(client, "writeback/preview", activity_id="event").json["writeback_review"]
    sheets.mode = "readback_auth"
    first = _post(client, "writeback/confirm", activity_id="event", preview_id=review["preview_id"])
    result = first.json["writeback_review"]
    assert (first.status_code, result["status"], result["issue"]["code"]) == (502, "unverified", "SHEETS_AUTH_REQUIRED")
    sheets.mode = "normal"
    retry = _post(client, "writeback/confirm", activity_id="event", preview_id=review["preview_id"])
    assert retry.json["writeback_review"]["status"] == "verified"
    assert len(sheets.writes) == 1


def test_writeback_repreviews_edited_old_value_and_rejects_new_question(app, client, notes_case):
    teacher_id, _, sheets = notes_case
    snapshot = _snapshot(teacher_id, _save(client))
    app.config["NOTES_ENDED_SNAPSHOT"] = lambda *_: snapshot
    review = _post(client, "writeback/preview", activity_id="event").json["writeback_review"]
    sheets.grid.cells[2, 4] = _cell("教師剛編輯")
    changed = _post(client, "writeback/confirm", activity_id="event", preview_id=review["preview_id"])
    assert changed.json["writeback_review"]["targets"][0]["original_display"] == "教師剛編輯"
    sheets.grid.cells[1, 0] = _cell("7")
    denied = _post(client, "writeback/confirm", activity_id="event",
                   preview_id=changed.json["writeback_review"]["preview_id"])
    assert denied.json["error"]["code"] == "SOURCE_REIMPORT_REQUIRED" and not sheets.writes


@pytest.mark.parametrize(("defect", "error_code"), [
    ("pending", "RESULT_NOT_READY"), ("not_closed", "RESULT_NOT_READY"),
    ("version", "RESULT_CATALOG_MISMATCH"), ("duplicate_question", "RESULT_CATALOG_MISMATCH"),
    ("unknown_question", "RESULT_CATALOG_MISMATCH"), ("unknown_item", "RESULT_CATALOG_MISMATCH"),
    ("duplicate_item", "RESULT_CATALOG_MISMATCH"), ("missing_item", "RESULT_CATALOG_MISMATCH"),
    ("other_teacher", "ACTIVITY_NOT_FOUND"), ("integration", "NOTES_INTEGRATION_PENDING"),
])
def test_invalid_settlement_does_not_reach_google(app, client, notes_case, defect, error_code):
    teacher_id, other_id, sheets = notes_case
    snapshot = _snapshot(teacher_id, _save(client))
    first, group = snapshot.questions
    bad = {
        "pending": replace(snapshot, settled=False), "not_closed": replace(snapshot, closed=False),
        "version": replace(snapshot, import_version="99"), "duplicate_question": replace(snapshot, questions=(first, group, group)),
        "unknown_question": replace(snapshot, questions=(first, replace(group, question_id="bad"))),
        "other_teacher": replace(snapshot, teacher_id=other_id),
    }
    bad_items = {
        "unknown_item": (group.answers[0], Answer("bad-item", "x")),
        "duplicate_item": (group.answers[0], group.answers[0]),
        "missing_item": (group.answers[0],),
    }
    if defect != "integration":
        snapshot = (replace(snapshot, questions=(first, replace(group, answers=bad_items[defect])))
                    if defect in bad_items else bad[defect])
        app.config["NOTES_ENDED_SNAPSHOT"] = lambda *_: snapshot
    reads_before = list(sheets.reads)
    assert _post(client, "writeback/preview", activity_id="event").json["error"]["code"] == error_code
    assert sheets.reads == reads_before and not sheets.writes


def test_source_url_parser():
    assert source_from_link("https://docs.google.com/spreadsheets/d/sheet-id/edit#gid=0") == ("sheet-id", 0)
    assert source_from_link("sheet-id") == ("sheet-id", None)
    with pytest.raises(AppError):
        source_from_link("https://example.test/spreadsheets/d/sheet-id/edit")


def test_google_client_grid_fields_and_literal_write(monkeypatch):
    from guided_notes import notes_sheets

    api = Mock()
    monkeypatch.setattr(notes_sheets, "_credentials", Mock())
    monkeypatch.setattr(notes_sheets, "build", Mock(return_value=Mock(spreadsheets=Mock(return_value=api))))
    api.getByDataFilter.return_value.execute.return_value = {"sheets": [{
        "properties": {"sheetId": 0, "title": "測試"},
        "merges": [{"endRowIndex": 1, "endColumnIndex": 2}],
        "data": [{"startRow": 4, "startColumn": 3, "rowData": [{"values": [_cell("文字")]}]}],
    }]}
    gateway = GoogleSheets()
    sheet = gateway.read("sheet-id", 0)
    assert sheet.text(4, 3) == "文字"
    assert sheet.span(0, 1) == Merge(0, 0, 1, 2)
    assert api.getByDataFilter.call_args.kwargs["body"] == {"dataFilters": [{"gridRange": {"sheetId": 0}}]}
    gateway.write("sheet-id", 0, [{"row": 4, "column": 3, "answer": "=1+2"}])
    assert api.batchUpdate.call_args.kwargs["body"] == {"requests": [{"updateCells": {
        "start": {"sheetId": 0, "rowIndex": 4, "columnIndex": 3},
        "rows": [{"values": [{"userEnteredValue": {"stringValue": "=1+2"}}]}],
        "fields": "userEnteredValue",
    }}]}
    assert api.batchUpdate.return_value.execute.call_args.kwargs == {"num_retries": 0}


@pytest.mark.parametrize(("status", "expected"), [(401, "SHEETS_AUTH_REQUIRED"), (403, "SHEETS_ACCESS_DENIED"), (503, "SHEETS_READ_FAILED")])
def test_google_client_errors_do_not_expose_upstream_message(monkeypatch, status, expected):
    from guided_notes import notes_sheets

    api = Mock()
    api.get.return_value.execute.side_effect = HttpError(Response({"status": str(status)}), b'{"error":{"message":"private"}}')
    monkeypatch.setattr(notes_sheets, "_credentials", Mock())
    monkeypatch.setattr(notes_sheets, "build", Mock(return_value=Mock(spreadsheets=Mock(return_value=api))))
    with pytest.raises(AppError) as error:
        GoogleSheets().tabs("sheet-id")
    assert error.value.code == expected and "private" not in error.value.message


def test_oauth_cli_uses_external_token_path_and_mock_browser(app, tmp_path, monkeypatch):
    from guided_notes import notes_sheets

    client_path = tmp_path / "example-client.json"
    token_path = tmp_path / "example-token.json"
    monkeypatch.setenv("NOTES_GOOGLE_CLIENT_SECRETS", str(client_path))
    monkeypatch.setenv("NOTES_GOOGLE_TOKEN", str(token_path))
    token = Mock(valid=True, has_scopes=Mock(return_value=True), to_json=Mock(return_value='{"example": true}'))
    flow = Mock()
    flow.run_local_server.return_value = token
    monkeypatch.setattr(notes_sheets.InstalledAppFlow, "from_client_secrets_file", Mock(return_value=flow))
    result = app.test_cli_runner().invoke(args=["notes", "authorize-sheets"])
    assert result.exit_code == 0, result.output
    assert token_path.read_text(encoding="utf-8") == '{"example": true}'
    assert flow.run_local_server.call_args.kwargs["host"] == "127.0.0.1"
    assert str(tmp_path) not in result.output


def test_expired_oauth_in_http_never_opens_sign_in(app, client, notes_case, tmp_path, monkeypatch):
    from guided_notes import notes_sheets

    app.config.pop("NOTES_SHEETS_FACTORY")
    token_path = tmp_path / "example-token.json"
    token_path.write_text(json.dumps({"scopes": [notes_sheets._SCOPES[0]]}), encoding="utf-8")
    monkeypatch.setenv("NOTES_GOOGLE_CLIENT_SECRETS", str(tmp_path / "example-client.json"))
    monkeypatch.setenv("NOTES_GOOGLE_TOKEN", str(token_path))
    open_browser = Mock()
    token = Mock(valid=False, refresh=Mock(side_effect=RefreshError("private error")))
    monkeypatch.setattr(notes_sheets.Credentials, "from_authorized_user_info", Mock(return_value=token))
    monkeypatch.setattr(notes_sheets.InstalledAppFlow, "from_client_secrets_file", open_browser)
    response = _post(client, "import/preview", source="sheet-id")
    assert (response.status_code, response.json["error"]["code"]) == (401, "SHEETS_AUTH_REQUIRED")
    assert "private" not in response.json["error"]["message"]
    open_browser.assert_not_called()
