import codecs
import csv
from io import StringIO

import pytest

from guided_notes import activities, quiz
from guided_notes.db import get_db
from guided_notes.notes_format import Merge
from guided_notes.results_csv import render_activity_results_csv
from test_notes import FakeSheets, _cell, _save


@pytest.fixture
def csv_activity(app, client):
    sheets = FakeSheets()
    sheets.grid.cells.pop((4, 3))
    sheets.grid.cells.update({
        (1, 3): _cell("未公開的講義原答案"),
        (4, 0): _cell("7"),
        (4, 1): _cell("這題不送出"),
    })
    sheets.grid.merges.append(Merge(4, 3, 5, 6))
    app.config["NOTES_SHEETS_FACTORY"] = lambda: sheets

    with app.app_context(), get_db() as db:
        owner, other = [
            db.execute("INSERT INTO teachers(username,password_hash) VALUES(?,?)", (name, "fixture")).lastrowid
            for name in ("csv-owner", "csv-other")
        ]
        course = activities.create_course(owner, "匯出驗收課程")
    with client.session_transaction() as session:
        session.update(teacher_id=owner, csrf_token="notes-fixture")
    version = _save(client, course)
    with app.app_context():
        activities.add_course_catalog(owner, course, **version)
        classroom = activities.create_classroom(owner, course, "匯出驗收課堂")
        code = get_db().execute("SELECT join_code FROM classrooms WHERE id=?", (classroom,)).fetchone()[0]
        activity = activities.create_activity(owner, classroom, **version)
    return owner, other, classroom, code, activity, sheets


def _read_csv(payload):
    return list(csv.reader(StringIO(payload.decode("utf-8-sig"), newline=""), strict=True))


def test_teacher_downloads_all_settled_results_from_the_closed_classroom(app, client, csv_activity):
    owner, _, room, code, activity, sheets = csv_activity
    red_name, blue_name = '紅, "隊"', "+藍隊"
    special_answer = '第一行, "雙引號"\n第二行'
    with app.app_context():
        activities.join_classroom(code, red_name)
        activities.join_classroom(code, blue_name)
        red, blue = [
            get_db().execute("SELECT id FROM teams WHERE classroom_id=? AND name=?", (room, name)).fetchone()[0]
            for name in (red_name, blue_name)
        ]
        activities.start_activity(owner, room, activity)
        quiz.submit_answer(room, activity, red, "q-3", "red-group",
                           {"q-3-item-2": "=1+1", "q-3-item-1": special_answer})
        quiz.submit_answer(room, activity, blue, "q-3", "blue-group",
                           {"q-3-item-1": "-文字", "q-3-item-2": "＠答案"})
        quiz.submit_answer(room, activity, blue, "q-1", "blue-single", {"q-1-item-1": "香蕉"})
        quiz.submit_answer(room, activity, red, "q-1", "red-single", {"q-1-item-1": "蘋果"})
        activities.end_activity(owner, room, activity)
        activities.close_classroom(owner, room)
        expected_results = quiz.get_activity_results(owner, activity)
        expected_snapshot = quiz.get_ended_snapshot(owner, activity)

    url = f"/quiz/api/results/{activity}/csv"
    page = client.get(f"/activities/teacher/classrooms/{room}")
    assert page.status_code == 200
    assert f'href="{url}">下載 CSV</a>' in page.get_data(as_text=True)
    reads_before = list(sheets.reads)
    response = client.get(url)
    assert response.status_code == 200
    assert response.headers["Content-Type"] == "text/csv; charset=utf-8"
    assert response.headers["Content-Disposition"] == f"attachment; filename=activity-results-{activity}.csv"
    assert response.headers["Cache-Control"] == "no-store"
    assert response.data.startswith(codecs.BOM_UTF8)
    assert _read_csv(response.data) == [
        ["題號", "小題識別", "組別", "答案", "受理順位", "是否勝組"],
        ["01", "q-1-item-1", "\t+藍隊", "香蕉", "1", "是"],
        ["01", "q-1-item-1", red_name, "蘋果", "2", "否"],
        ["3", "q-3-item-1", red_name, special_answer, "1", "是"],
        ["3", "q-3-item-2", red_name, "\t=1+1", "1", "是"],
        ["3", "q-3-item-1", "\t+藍隊", "\t-文字", "2", "否"],
        ["3", "q-3-item-2", "\t+藍隊", "\t＠答案", "2", "否"],
        ["7", "", "", "", "", ""],
    ]
    assert "未公開的講義原答案" not in response.get_data(as_text=True)
    assert client.get(url).data == response.data
    with app.app_context():
        assert quiz.get_activity_results(owner, activity) == expected_results
        assert quiz.get_ended_snapshot(owner, activity) == expected_snapshot
    assert sheets.reads == reads_before and sheets.writes == []


def test_csv_denies_unfinished_activities_and_unqualified_callers(app, client, csv_activity):
    owner, other, room, code, activity, sheets = csv_activity
    url = f"/quiz/api/results/{activity}/csv"
    page_url = f"/activities/teacher/classrooms/{room}"
    reads_before = list(sheets.reads)
    for phase in ("preparing", "active"):
        if phase == "active":
            with app.app_context():
                activities.start_activity(owner, room, activity)
        page = client.get(page_url)
        assert page.status_code == 200
        assert "下載 CSV" not in page.get_data(as_text=True)
        response = client.get(url)
        assert (response.status_code, response.json["error"]["code"]) == (409, "RESULT_NOT_READY")
        assert "Content-Disposition" not in response.headers

    with app.app_context():
        proof, _ = activities.join_classroom(code, "學生組")
        activities.end_activity(owner, room, activity)
    anonymous = app.test_client()
    student = app.test_client()
    student.set_cookie(activities.PROOF_COOKIE, proof)
    other_teacher = app.test_client()
    with other_teacher.session_transaction() as session:
        session["teacher_id"] = other
    for requester, path, status, error in [
        (anonymous, url, 401, "TEACHER_REQUIRED"),
        (student, url, 401, "TEACHER_REQUIRED"),
        (other_teacher, url, 404, "ACTIVITY_NOT_FOUND"),
        (client, "/quiz/api/results/missing/csv", 404, "ACTIVITY_NOT_FOUND"),
    ]:
        response = requester.get(path)
        assert (response.status_code, response.json["error"]["code"]) == (status, error)
        assert "Content-Disposition" not in response.headers
    assert sheets.reads == reads_before and sheets.writes == []


@pytest.mark.parametrize("unsafe", [
    "=1+1", "+文字", "-文字", "@文字", "  =1+1", "\t文字", "\r文字", "\n文字",
    "　＝文字", "＋文字", "－文字", "＠文字",
])
def test_csv_neutralizes_dangerous_prefixes_in_each_text_column(unsafe):
    results = {"questions": [{
        "display_number": unsafe,
        "teams": [{"team_name": unsafe, "rank": 1, "is_winner": True,
                   "answers": [{"item_id": unsafe, "text": unsafe}]}],
    }]}
    header, row = _read_csv(render_activity_results_csv(results))
    assert len(header) == 6
    assert row == ["\t" + unsafe] * 4 + ["1", "是"]
