import hashlib
import json
import sqlite3
import threading

import pytest
from werkzeug.security import generate_password_hash

from guided_notes import activities
from guided_notes.db import get_db, init_db
from guided_notes.errors import AppError
from guided_notes.notes import list_course_catalogs as list_notes_course_catalogs


def teacher(app, username):
    with app.app_context():
        db = get_db()
        db.execute("INSERT INTO teachers(username,password_hash) VALUES (?,?)", (username, generate_password_hash("pw")))
        db.commit()
        return db.execute("SELECT id FROM teachers WHERE username=?", (username,)).fetchone()[0]


def setup_catalog(app, teacher_id):
    app.config["DEMO_CATALOG"] = True
    with app.app_context():
        course = activities.create_course(teacher_id, "課程一")
        activities.add_course_catalog(teacher_id, course, "demo-guided-notes", "1")
        room = activities.create_classroom(teacher_id, course, "課堂一")
        code = get_db().execute("SELECT join_code FROM classrooms WHERE id=?", (room,)).fetchone()[0]
        return course, room, code


def make_activity(app, teacher_id, classroom_id, title="活動"):
    with app.app_context():
        return activities.create_activity(teacher_id, classroom_id, "demo-guided-notes", "1", title)


def test_init_db_creates_activity_schema_and_is_idempotent(app):
    with app.app_context():
        init_db()
        init_db()
        names = {row[0] for row in get_db().execute("SELECT name FROM sqlite_master WHERE type='table'")}
        assert {"teachers", "courses", "course_catalogs", "classrooms", "teams", "student_proofs", "activities", "activity_questions"} <= names


def test_teacher_course_catalog_and_classroom_ownership(app):
    owner = teacher(app, "owner")
    other = teacher(app, "other")
    app.config["DEMO_CATALOG"] = True
    with app.app_context():
        course = activities.create_course(owner, "我的課程")
        assert len(activities.list_courses(owner)) == 1
        with pytest.raises(AppError) as err:
            activities.list_course_catalogs(other, course)
        assert err.value.code == "RESOURCE_NOT_FOUND"
        activities.add_course_catalog(owner, course, "demo-guided-notes", "1")
        assert activities.list_course_catalogs(owner, course)[0]["title"] == "示範用填空學習單"
        with pytest.raises(AppError) as err:
            activities.add_course_catalog(owner, course, "missing", "9")
        assert err.value.code == "CATALOG_NOT_FOUND"


def test_notes_course_access_defaults_to_activities_ownership_and_allows_override(app):
    owner = teacher(app, "owner")
    other = teacher(app, "other")
    with app.app_context():
        course = activities.create_course(owner, "我的課程")
        assert app.config["NOTES_COURSE_ACCESS"] is activities.notes_course_access
        assert activities.notes_course_access(owner, course) is True
        assert activities.notes_course_access(other, course) is False
        assert activities.notes_course_access(owner, "missing-course") is False
        assert activities.notes_course_access(owner, None) is False

        app.config["NOTES_COURSE_ACCESS"] = lambda teacher_id, course_id: (
            teacher_id == owner and course_id == "test-override"
        )
        assert list_notes_course_catalogs(owner, "test-override") == []
        with pytest.raises(AppError) as err:
            list_notes_course_catalogs(other, "test-override")
        assert err.value.code == "COURSE_FORBIDDEN"


def test_course_catalogs_are_scoped_and_demo_mode_remains_compatible(app):
    owner = teacher(app, "owner")
    with app.app_context():
        course_x = activities.create_course(owner, "課程 X")
        course_y = activities.create_course(owner, "課程 Y")
        versions = {
            course_x: ("catalog-x", "講義 X"),
            course_y: ("catalog-y", "講義 Y"),
        }
        for index, (course_id, (import_id, title)) in enumerate(versions.items(), start=1):
            layout = [{
                "question_id": f"question-{index}", "display_number": str(index), "type": "single",
                "items": [{"item_id": f"item-{index}", "label": "", "order": 1}],
            }]
            get_db().execute(
                """INSERT INTO notes_versions
                   (import_id, import_version, teacher_id, course_id, spreadsheet_id, sheet_id, title, layout)
                   VALUES (?, 1, ?, ?, ?, 0, ?, ?)""",
                (import_id, owner, course_id, f"sheet-{index}", title, json.dumps(layout)),
            )
        get_db().commit()

        client = app.test_client()
        with client.session_transaction() as session:
            session["teacher_id"] = owner
        page_x = client.get(f"/activities/teacher/courses/{course_x}")
        page_text = page_x.get_data(as_text=True)
        assert page_x.status_code == 200
        assert "講義 X" in page_text and "講義 Y" not in page_text
        assert f'href="/notes/courses/{course_x}"' in page_text

        activities.add_course_catalog(owner, course_x, "catalog-x", "1")
        with pytest.raises(AppError) as err:
            activities.add_course_catalog(owner, course_y, "catalog-x", "1")
        assert err.value.code == "CATALOG_NOT_FOUND"
        assert activities.list_course_catalogs(owner, course_y) == []

        activity_id = activities.create_activity(owner, activities.create_classroom(owner, course_x, "課堂"), "catalog-x", "1")
        question = get_db().execute(
            "SELECT question_id FROM activity_questions WHERE activity_id=?", (activity_id,)
        ).fetchone()[0]
        assert question == "question-1"

        app.config["DEMO_CATALOG"] = True
        demo_page = client.get(f"/activities/teacher/courses/{course_y}").get_data(as_text=True)
        assert "示範用填空學習單" in demo_page
        activities.add_course_catalog(owner, course_y, "demo-guided-notes", "1")
        demo_activity = activities.create_activity(owner, activities.create_classroom(owner, course_y, "示範課堂"),
                                                   "demo-guided-notes", "1")
        assert get_db().execute(
            "SELECT count(*) FROM activity_questions WHERE activity_id=?", (demo_activity,)
        ).fetchone()[0] == 3


def test_notes_pages_render_html_errors_and_course_links(app):
    owner = teacher(app, "owner")
    other = teacher(app, "other")
    with app.app_context():
        course = activities.create_course(owner, "我的課程")
    client = app.test_client()
    with client.session_transaction() as session:
        session.update(teacher_id=owner, csrf_token="notes-csrf")

    notes_page = client.get(f"/notes/courses/{course}")
    notes_page_text = notes_page.get_data(as_text=True)
    assert notes_page.status_code == 200
    assert f'href="/activities/teacher/courses/{course}"' in notes_page_text
    assert "回課程頁" in notes_page_text

    invalid_source = client.post(
        f"/notes/courses/{course}/import/preview",
        data={"csrf_token": "notes-csrf", "source": "http://not-a-sheets-link"},
    )
    invalid_text = invalid_source.get_data(as_text=True)
    assert invalid_source.status_code == 400 and invalid_source.content_type.startswith("text/html")
    assert "NOTES_SOURCE_INVALID" in invalid_text and "請輸入有效的 Google Sheets" in invalid_text
    assert f'href="/notes/courses/{course}"' in invalid_text

    missing_credentials = client.post(
        f"/notes/courses/{course}/import/preview",
        data={"csrf_token": "notes-csrf", "source": "valid-sheet-id"},
    )
    credential_text = missing_credentials.get_data(as_text=True)
    assert missing_credentials.status_code == 500 and missing_credentials.content_type.startswith("text/html")
    assert "GOOGLE_CREDENTIALS_REQUIRED" in credential_text
    assert f'href="/notes/courses/{course}"' in credential_text

    with client.session_transaction() as session:
        session["teacher_id"] = other
    forbidden = client.get(f"/notes/courses/{course}")
    forbidden_text = forbidden.get_data(as_text=True)
    assert forbidden.status_code == 403 and forbidden.content_type.startswith("text/html")
    assert "COURSE_FORBIDDEN" in forbidden_text and "無法存取這門課程" in forbidden_text
    assert 'href="/activities/teacher/courses"' in forbidden_text
    missing_course = client.get("/notes/courses/not-a-course")
    assert missing_course.status_code == 403
    assert "COURSE_FORBIDDEN" in missing_course.get_data(as_text=True)


def test_classroom_codes_and_team_names_are_scoped(app):
    owner = teacher(app, "teacher")
    course, room_one, code_one = setup_catalog(app, owner)
    with app.app_context():
        room_two = activities.create_classroom(owner, course, "課堂二")
        code_two = get_db().execute("SELECT join_code FROM classrooms WHERE id=?", (room_two,)).fetchone()[0]
        assert code_one != code_two
        assert len(code_one) == len(code_two) == 6
        assert not set(code_one + code_two) & set("0O1I")
        token_a, _ = activities.join_classroom(code_one.lower(), "  Team   Alpha ")
        token_b, _ = activities.join_classroom(code_one, "team alpha")
        token_c, _ = activities.join_classroom(code_two, "TEAM ALPHA")
        proof = get_db().execute("SELECT team_id, token_hash FROM student_proofs ORDER BY rowid").fetchall()
        assert proof[0]["team_id"] == proof[1]["team_id"] != proof[2]["team_id"]
        assert proof[0]["token_hash"] == hashlib.sha256(token_a.encode()).hexdigest()
        assert proof[1]["token_hash"] == hashlib.sha256(token_b.encode()).hexdigest()
        assert proof[0]["token_hash"] != proof[1]["token_hash"]
        assert token_a != token_b != token_c
        with pytest.raises(AppError, match="組名長度"):
            activities.join_classroom(code_one, "   ")


def test_activity_snapshot_state_order_close_and_quiz_eligibility(app):
    owner = teacher(app, "teacher")
    _, classroom, code = setup_catalog(app, owner)
    with app.app_context():
        token, _ = activities.join_classroom(code, "Alpha")
        first = activities.create_activity(owner, classroom, "demo-guided-notes", "1")
        state = activities.student_state(token)
        assert state["activity"]["phase"] == "preparing"
        assert "question_numbers" in state["activity"]
        version_before_start = state["state_version"]
        activities.start_activity(owner, classroom, first)
        assert activities.student_state(token)["state_version"] > version_before_start
        question_id = get_db().execute("SELECT question_id FROM activity_questions WHERE activity_id=? ORDER BY question_order LIMIT 1", (first,)).fetchone()[0]
        with activities.immediate_transaction(get_db()):
            activities.assert_submission_eligible(get_db(), classroom, first,
                get_db().execute("SELECT team_id FROM student_proofs").fetchone()[0], question_id)
            assert get_db().in_transaction
        activities.end_activity(owner, classroom, first)
        state = activities.student_state(token)
        assert state["activity"]["phase"] == "ended"
        assert state["activity"]["question_numbers"]
        with pytest.raises(AppError) as err:
            activities.start_activity(owner, classroom, first)
        assert err.value.code == "ACTIVITY_NOT_PREPARING"
        with pytest.raises(AppError) as err:
            with activities.immediate_transaction(get_db()):
                activities.assert_submission_eligible(get_db(), classroom, first,
                    get_db().execute("SELECT team_id FROM student_proofs").fetchone()[0], question_id)
        assert err.value.code == "ACTIVITY_NOT_ACTIVE"
        second = activities.create_activity(owner, classroom, "demo-guided-notes", "1", "第二個")
        assert activities.student_state(token)["activity"]["id"] == second
        activities.start_activity(owner, classroom, second)
        assert activities.student_state(token)["activity"]["phase"] == "active"
        activities.close_classroom(owner, classroom)
        state = activities.student_state(token)
        assert state["classroom_ended"] is True
        assert state["activity"]["id"] == second
        assert state["activity"]["phase"] == "ended"
        assert get_db().execute("SELECT ended_seq FROM activities WHERE id=?", (second,)).fetchone()[0] is not None
        assert set(state) == {"classroom_name", "team_name", "classroom_status", "classroom_ended", "activity", "state_version"}
        with pytest.raises(AppError) as err:
            activities.create_activity(owner, classroom, "demo-guided-notes", "1")
        assert err.value.code == "CLASSROOM_CLOSED"
        with pytest.raises(AppError) as err:
            activities.start_activity(owner, classroom, second)
        assert err.value.code == "CLASSROOM_CLOSED"
        with pytest.raises(AppError):
            activities.join_classroom(code, "New team")


def test_preparing_activity_precedes_recently_ended(app):
    owner = teacher(app, "teacher")
    _, classroom, code = setup_catalog(app, owner)
    with app.app_context():
        token, _ = activities.join_classroom(code, "Alpha")
        ended = activities.create_activity(owner, classroom, "demo-guided-notes", "1", "ended")
        activities.start_activity(owner, classroom, ended)
        activities.end_activity(owner, classroom, ended)
        preparing = activities.create_activity(owner, classroom, "demo-guided-notes", "1", "preparing")
        assert activities.student_state(token)["activity"]["id"] == preparing


def test_latest_ended_activity_uses_end_sequence_when_timestamps_match(app):
    owner = teacher(app, "teacher")
    _, classroom, code = setup_catalog(app, owner)
    with app.app_context():
        token, _ = activities.join_classroom(code, "Alpha")
        activity_a = activities.create_activity(owner, classroom, "demo-guided-notes", "1", "A")
        activity_b = activities.create_activity(owner, classroom, "demo-guided-notes", "1", "B")

        activities.start_activity(owner, classroom, activity_b)
        activities.end_activity(owner, classroom, activity_b)
        activities.start_activity(owner, classroom, activity_a)
        activities.end_activity(owner, classroom, activity_a)

        # Force the timestamp collision that previously let rowid choose B.
        get_db().execute(
            "UPDATE activities SET ended_at='2026-01-01 12:00:00' WHERE id IN (?, ?)",
            (activity_a, activity_b),
        )
        rows = get_db().execute(
            "SELECT id, ended_seq FROM activities WHERE id IN (?, ?)", (activity_a, activity_b)
        ).fetchall()
        sequences = {row["id"]: row["ended_seq"] for row in rows}
        assert sequences[activity_a] > sequences[activity_b]
        assert activities.student_state(token)["activity"]["id"] == activity_a


def test_active_activity_precedes_newer_preparing_activity(app):
    owner = teacher(app, "teacher")
    _, classroom, code = setup_catalog(app, owner)
    with app.app_context():
        token, _ = activities.join_classroom(code, "Alpha")
        active = activities.create_activity(owner, classroom, "demo-guided-notes", "1", "active")
        activities.start_activity(owner, classroom, active)
        preparing = activities.create_activity(owner, classroom, "demo-guided-notes", "1", "newer preparing")
        state = activities.student_state(token)
        assert state["activity"]["id"] == active
        assert state["activity"]["phase"] == "active"
        assert preparing != active


def test_student_routes_proof_cookie_privacy_and_teacher_routes(app):
    owner = teacher(app, "teacher")
    _, classroom, code = setup_catalog(app, owner)
    client = app.test_client()
    response = client.get("/activities/join")
    assert response.status_code == 200
    import re
    token = re.search(rb'name="csrf_token" value="([^"]+)', response.data).group(1).decode()
    joined = client.post("/activities/join", data={"csrf_token": token, "join_code": code, "team_name": "Alpha"})
    assert joined.status_code == 302
    cookie_header = joined.headers.get("Set-Cookie", "")
    assert "HttpOnly" in cookie_header
    assert "guided_notes_join_proof" in cookie_header
    state = client.get("/activities/api/student/state")
    assert state.status_code == 200
    assert state.json["team_name"] == "Alpha"
    assert "teams" not in state.json and "answers" not in state.json
    client.get("/activities/student")
    client.delete_cookie("guided_notes_join_proof")
    assert client.get("/activities/api/student/state").status_code == 401
    bad = app.test_client()
    bad.set_cookie("guided_notes_join_proof", "tampered-proof")
    denied = bad.get("/activities/api/student/state")
    assert denied.status_code == 401
    assert "team_name" not in denied.json
    assert app.test_client().get("/activities/teacher/courses").status_code == 302


def test_teacher_routes_render_and_enforce_csrf(app):
    owner = teacher(app, "teacher")
    app.config["DEMO_CATALOG"] = True
    client = app.test_client()
    login_page = client.get("/login")
    import re
    csrf = re.search(rb'name="csrf_token" value="([^"]+)', login_page.data).group(1).decode()
    assert client.post("/login", data={"csrf_token": csrf, "username": "teacher", "password": "pw"}).status_code == 302
    courses = client.get("/activities/teacher/courses")
    assert courses.status_code == 200 and "建立課程" in courses.get_data(as_text=True)
    csrf = re.search(rb'name="csrf_token" value="([^"]+)', courses.data).group(1).decode()
    created = client.post("/activities/teacher/courses", data={"csrf_token": csrf, "name": "課程"})
    assert created.status_code == 302
    course_id = created.headers["Location"].rsplit("/", 1)[-1]
    course_page = client.get(created.headers["Location"])
    assert course_page.status_code == 200 and "示範用填空學習單" in course_page.get_data(as_text=True)
    csrf = re.search(rb'name="csrf_token" value="([^"]+)', course_page.data).group(1).decode()
    add_catalog = client.post(f"/activities/teacher/courses/{course_id}/catalogs", data={
        "csrf_token": csrf, "import_id": "demo-guided-notes", "import_version": "1"})
    assert add_catalog.status_code == 302
    no_csrf = client.post(f"/activities/teacher/courses/{course_id}/classrooms", data={"name": "課堂"})
    assert no_csrf.status_code == 400
    created_room = client.post(f"/activities/teacher/courses/{course_id}/classrooms", data={"csrf_token": csrf, "name": "課堂"})
    assert created_room.status_code == 302
    room_page = client.get(created_room.headers["Location"])
    assert room_page.status_code == 200 and "關閉課堂" in room_page.get_data(as_text=True)


def test_browser_app_errors_render_chinese_html_with_contextual_return_links(app):
    owner = teacher(app, "teacher")
    _, classroom, _ = setup_catalog(app, owner)
    client = app.test_client()
    import re

    join_page = client.get("/activities/join")
    csrf = re.search(rb'name="csrf_token" value="([^"]+)', join_page.data).group(1).decode()
    bad_join = client.post("/activities/join", data={
        "csrf_token": csrf, "join_code": "AAAAAA", "team_name": "Alpha"})
    bad_join_text = bad_join.get_data(as_text=True)
    assert bad_join.status_code == 404 and bad_join.content_type.startswith("text/html")
    assert "課堂不存在或已結束" in bad_join_text and "CLASSROOM_NOT_JOINABLE" in bad_join_text
    assert 'href="/activities/join"' in bad_join_text

    no_proof = client.get("/activities/student")
    no_proof_text = no_proof.get_data(as_text=True)
    assert no_proof.status_code == 401 and no_proof.content_type.startswith("text/html")
    assert "加入證明無效或已失效" in no_proof_text and "STUDENT_PROOF_INVALID" in no_proof_text
    assert 'href="/activities/join"' in no_proof_text

    app.config["DEMO_CATALOG"] = True
    with app.app_context():
        first = activities.create_activity(owner, classroom, "demo-guided-notes", "1", "第一個")
        second = activities.create_activity(owner, classroom, "demo-guided-notes", "1", "第二個")
        activities.start_activity(owner, classroom, first)
    login_page = client.get("/login")
    csrf = re.search(rb'name="csrf_token" value="([^"]+)', login_page.data).group(1).decode()
    assert client.post("/login", data={"csrf_token": csrf, "username": "teacher", "password": "pw"}).status_code == 302
    classroom_page = client.get(f"/activities/teacher/classrooms/{classroom}")
    csrf = re.search(rb'name="csrf_token" value="([^"]+)', classroom_page.data).group(1).decode()
    conflict = client.post(
        f"/activities/teacher/classrooms/{classroom}/activities/{second}/start",
        data={"csrf_token": csrf},
    )
    conflict_text = conflict.get_data(as_text=True)
    assert conflict.status_code == 409 and conflict.content_type.startswith("text/html")
    assert "此課堂已有搶答中的活動" in conflict_text and "ACTIVITY_ALREADY_ACTIVE" in conflict_text
    assert f'href="/activities/teacher/classrooms/{classroom}"' in conflict_text


def test_api_app_errors_remain_json(app):
    def fail_api():
        raise AppError("API_FAILURE", "API 錯誤。", 422)

    app.add_url_rule("/api/test-error", view_func=fail_api)
    app.add_url_rule("/notes/api/test-error", endpoint="notes.api_test_error", view_func=fail_api)
    client = app.test_client()
    response = client.get("/activities/api/student/state")
    assert response.status_code == 401
    assert response.is_json
    assert response.json["error"]["code"] == "STUDENT_PROOF_INVALID"
    api_response = client.get("/api/test-error")
    assert api_response.status_code == 422 and api_response.is_json
    assert api_response.json == {"error": {"code": "API_FAILURE", "message": "API 錯誤。"}}

    notes_api_response = client.get("/notes/api/test-error")
    assert notes_api_response.status_code == 422 and notes_api_response.is_json
    assert notes_api_response.json["error"]["code"] == "API_FAILURE"


def test_end_and_close_serialize_with_answer_transaction(app):
    owner = teacher(app, "teacher")
    _, classroom, code = setup_catalog(app, owner)
    with app.app_context():
        activity_id = activities.create_activity(owner, classroom, "demo-guided-notes", "1")
        activities.start_activity(owner, classroom, activity_id)
        token, _ = activities.join_classroom(code, "Alpha")
        team_id = get_db().execute("SELECT team_id FROM student_proofs").fetchone()[0]
        question_id = get_db().execute("SELECT question_id FROM activity_questions WHERE activity_id=? LIMIT 1", (activity_id,)).fetchone()[0]
    answer_locked = threading.Event()
    release_answer = threading.Event()
    result = []

    def answer_transaction():
        with app.app_context():
            db = get_db()
            with activities.immediate_transaction(db):
                activities.assert_submission_eligible(db, classroom, activity_id, team_id, question_id)
                db.execute("CREATE TEMP TABLE IF NOT EXISTS quiz_answer_probe(value TEXT)")
                db.execute("INSERT INTO quiz_answer_probe(value) VALUES ('accepted-before-close')")
                answer_locked.set()
                release_answer.wait(timeout=3)
            result.append("answer-committed")

    answer_thread = threading.Thread(target=answer_transaction)
    answer_thread.start()
    assert answer_locked.wait(timeout=2)

    def close_after_answer_lock():
        with app.app_context():
            activities.close_classroom(owner, classroom)
            result.append("closed")

    close_thread = threading.Thread(target=close_after_answer_lock)
    close_thread.start()
    release_answer.set()
    answer_thread.join(timeout=4)
    close_thread.join(timeout=4)
    assert result == ["answer-committed", "closed"]
    with app.app_context():
        with pytest.raises(AppError) as err:
            with activities.immediate_transaction(get_db()):
                activities.assert_submission_eligible(get_db(), classroom, activity_id, team_id, question_id)
        assert err.value.code == "CLASSROOM_CLOSED"
        assert activities.student_state(token)["classroom_ended"]


def test_concurrent_start_requests_allow_only_one_active_activity(app):
    owner = teacher(app, "teacher")
    _, classroom, _ = setup_catalog(app, owner)
    one = make_activity(app, owner, classroom, "one")
    two = make_activity(app, owner, classroom, "two")
    barrier = threading.Barrier(2)
    results = []

    def start(activity_id):
        with app.app_context():
            barrier.wait()
            try:
                activities.start_activity(owner, classroom, activity_id)
                results.append("ok")
            except AppError:
                results.append("rejected")

    threads = [threading.Thread(target=start, args=(activity_id,)) for activity_id in (one, two)]
    for thread in threads: thread.start()
    for thread in threads: thread.join()
    assert sorted(results) == ["ok", "rejected"]


def test_transaction_eligibility_requires_caller_transaction(app):
    with app.app_context(), pytest.raises(RuntimeError, match="active caller-owned"):
        activities.assert_submission_eligible(get_db(), "classroom", "activity", "team", "q")


def test_quiz_eligibility_rejects_foreign_team_and_unknown_question(app):
    owner = teacher(app, "teacher")
    _, classroom_one, code_one = setup_catalog(app, owner)
    with app.app_context():
        course_two = activities.create_course(owner, "第二課程")
        activities.add_course_catalog(owner, course_two, "demo-guided-notes", "1")
        classroom_two = activities.create_classroom(owner, course_two, "第二課堂")
        token, _ = activities.join_classroom(code_one, "Alpha")
        code_two = get_db().execute("SELECT join_code FROM classrooms WHERE id=?", (classroom_two,)).fetchone()[0]
        activities.join_classroom(code_two, "Beta")
        team_one = get_db().execute("SELECT team_id FROM student_proofs WHERE token_hash=?", (hashlib.sha256(token.encode()).hexdigest(),)).fetchone()[0]
        team_two = get_db().execute("SELECT id FROM teams WHERE classroom_id=?", (classroom_two,)).fetchone()[0]
        activity = activities.create_activity(owner, classroom_one, "demo-guided-notes", "1")
        activities.start_activity(owner, classroom_one, activity)
        question = get_db().execute("SELECT question_id FROM activity_questions WHERE activity_id=? LIMIT 1", (activity,)).fetchone()[0]
        with pytest.raises(AppError) as err:
            with activities.immediate_transaction(get_db()):
                activities.assert_submission_eligible(get_db(), classroom_one, activity, team_two, question)
        assert err.value.code == "TEAM_CLASSROOM_MISMATCH"
        with pytest.raises(AppError) as err:
            with activities.immediate_transaction(get_db()):
                activities.assert_submission_eligible(get_db(), classroom_one, activity, team_one, "unknown-question")
        assert err.value.code == "QUESTION_NOT_IN_ACTIVITY"


def test_state_poll_updates_within_two_seconds(app):
    import time
    owner = teacher(app, "teacher")
    _, classroom, code = setup_catalog(app, owner)
    with app.app_context():
        token, _ = activities.join_classroom(code, "Alpha")
        activity = activities.create_activity(owner, classroom, "demo-guided-notes", "1")
        before = activities.student_state(token)["state_version"]
        activities.start_activity(owner, classroom, activity)
    started = time.monotonic()
    with app.app_context():
        after = activities.student_state(token)
    assert time.monotonic() - started < 2
    assert after["state_version"] > before
    assert after["activity"]["phase"] == "active"
    with app.test_client() as client:
        student_token = token
        client.set_cookie(activities.PROOF_COOKIE, student_token)
        page = client.get("/activities/student").get_data(as_text=True)
    assert "if(s.state_version<=appliedVersion)return" in page
    assert "setInterval(refresh,1000)" in page
