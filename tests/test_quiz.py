import pytest
import threading
from werkzeug.security import generate_password_hash

from guided_notes import activities, create_app, quiz
from guided_notes.db import get_db, init_db
from guided_notes.errors import AppError


def _setup(app):
    app.config["DEMO_CATALOG"] = True
    with app.app_context():
        db = get_db()
        db.execute("INSERT INTO teachers(username,password_hash) VALUES(?,?)", ("quiz-teacher", generate_password_hash("pw")))
        db.commit()
        teacher_id = db.execute("SELECT id FROM teachers WHERE username='quiz-teacher'").fetchone()[0]
        course = activities.create_course(teacher_id, "課程")
        activities.add_course_catalog(teacher_id, course, "demo-guided-notes", "1")
        classroom = activities.create_classroom(teacher_id, course, "課堂")
        code = db.execute("SELECT join_code FROM classrooms WHERE id=?", (classroom,)).fetchone()[0]
        token_a, _ = activities.join_classroom(code, "甲組")
        token_b, _ = activities.join_classroom(code, "乙組")
        activity = activities.create_activity(teacher_id, classroom, "demo-guided-notes", "1")
        question = "demo-q-01"
        activities.start_activity(teacher_id, classroom, activity)
        team_a = db.execute("SELECT team_id FROM student_proofs WHERE token_hash IS NOT NULL ORDER BY rowid LIMIT 1").fetchone()[0]
        team_b = db.execute("SELECT id FROM teams WHERE classroom_id=? ORDER BY rowid DESC LIMIT 1", (classroom,)).fetchone()[0]
        return teacher_id, classroom, activity, question, token_a, token_b, team_a, team_b


def test_submission_validation_replay_replacement_and_results(app):
    owner, room, activity, question, _, _, alpha, beta = _setup(app)
    answers_a = {"demo-q-01-item-1": "甲一", "demo-q-01-item-2": "甲二"}
    answers_b = {"demo-q-01-item-1": "乙一", "demo-q-01-item-2": "乙二"}
    with app.app_context():
        with pytest.raises(AppError) as error:
            quiz.submit_answer(room, activity, alpha, question, "partial", {"demo-q-01-item-1": "x"})
        assert error.value.code == "SUBMISSION_INVALID"
        with pytest.raises(AppError) as error:
            quiz.submit_answer(room, activity, alpha, question, "long", {
                "demo-q-01-item-1": "x" * 201, "demo-q-01-item-2": "ok"})
        assert error.value.code == "ANSWER_TOO_LONG"
        first = quiz.submit_answer(room, activity, alpha, question, "a1", answers_a)
        replay = quiz.submit_answer(room, activity, alpha, question, "a1", answers_a)
        assert first["accepted_sequence"] == replay["accepted_sequence"] and replay["replayed"]
        quiz.submit_answer(room, activity, beta, question, "b1", answers_b)
        quiz.submit_answer(room, activity, alpha, question, "a2", answers_a)
        with pytest.raises(AppError) as error:
            quiz.submit_answer(room, activity, alpha, question, "a1", answers_b)
        assert error.value.code == "SUBMISSION_ID_REUSED"
        activities.end_activity(owner, room, activity)
        data = quiz.get_activity_results(owner, activity)
        result = next(q for q in data["questions"] if q["question_id"] == question)
        assert result["winner_id"] == beta
        assert [(team["team_id"], team["rank"]) for team in result["teams"]] == [(beta, 1), (alpha, 2)]
        snapshot = quiz.get_ended_snapshot(owner, activity)
        assert snapshot.closed and snapshot.settled
        assert len(snapshot.questions) == 3
        assert snapshot.questions[0].winner_id == beta
        assert [a.item_id for a in snapshot.questions[0].answers] == list(answers_b)


def test_rejected_and_closed_submissions_do_not_replace_prior(app):
    owner, room, activity, question, _, _, alpha, _ = _setup(app)
    valid = {"demo-q-01-item-1": "keep", "demo-q-01-item-2": "me"}
    with app.app_context():
        quiz.submit_answer(room, activity, alpha, question, "first", valid)
        with pytest.raises(AppError) as error:
            quiz.submit_answer(room, activity, alpha, question, "blank", {**valid, "demo-q-01-item-1": "  "})
        assert error.value.code == "ANSWER_REQUIRED"
        activities.end_activity(owner, room, activity)
        with pytest.raises(AppError):
            quiz.submit_answer(room, activity, alpha, question, "later", valid)
        result = next(q for q in quiz.get_activity_results(owner, activity)["questions"] if q["question_id"] == question)
        assert result["teams"][0]["answers"][0]["text"] == "keep"


def test_student_and_teacher_quiz_endpoints_keep_authorization(app):
    owner, room, activity, _, token_a, token_b, _, _ = _setup(app)
    client = app.test_client()
    client.set_cookie(activities.PROOF_COOKIE, token_a)
    student = client.get("/quiz/api/student/state")
    assert student.status_code == 200
    assert all("teams" not in entry or entry["teams"] is None for entry in student.json["submissions"])
    content = client.get(f"/quiz/api/activity/{activity}/content")
    assert content.status_code == 200 and content.json["questions"]
    assert "source" not in content.get_data(as_text=True)
    assert "source_text" not in content.get_data(as_text=True)
    assert client.get(f"/quiz/api/classrooms/{room}/activities/{activity}/state").status_code == 401


def test_result_errors_and_closed_student_short_circuit(app):
    owner, room, activity, _, token_a, _, _, _ = _setup(app)
    with app.app_context():
        with pytest.raises(AppError) as error:
            quiz.get_activity_results(owner, activity)
        assert error.value.code == "RESULT_NOT_READY"
        with pytest.raises(AppError) as error:
            quiz.get_activity_results(owner + 100, activity)
        assert error.value.code == "ACTIVITY_NOT_FOUND"
        pending = quiz.get_ended_snapshot(owner, activity)
        assert pending.closed is False and pending.settled is False
        activities.close_classroom(owner, room)
        client = app.test_client()
        client.set_cookie(activities.PROOF_COOKIE, token_a)
        response = client.get("/quiz/api/student/state")
        assert response.json == {"classroom_ended": True}


def test_empty_result_questions_are_present_without_winners(app):
    owner, room, activity, _, _, _, _, _ = _setup(app)
    with app.app_context():
        activities.end_activity(owner, room, activity)
        result = quiz.get_activity_results(owner, activity)
        assert len(result["questions"]) == 3
        assert all(q["winner_id"] is None and q["winner_name"] is None and q["teams"] == [] for q in result["questions"])
        snapshot = quiz.get_ended_snapshot(owner, activity)
        assert all(q.winner_id is None and q.answers == () for q in snapshot.questions)


def test_quiz_schema_is_idempotent_and_does_not_change_activity_rows(app):
    owner, room, activity, _, _, _, _, _ = _setup(app)
    with app.app_context():
        before = [tuple(row) for row in get_db().execute("SELECT * FROM activities WHERE id=?", (activity,))]
        init_db()
        init_db()
        after = [tuple(row) for row in get_db().execute("SELECT * FROM activities WHERE id=?", (activity,))]
        tables = {row[0] for row in get_db().execute("SELECT name FROM sqlite_master WHERE type='table'")}
        assert {"quiz_submissions", "quiz_answers"} <= tables
        assert before == after


def test_concurrent_submissions_receive_unique_sequences(app):
    _, room, activity, question, _, _, alpha, beta = _setup(app)
    answers_a = {"demo-q-01-item-1": "甲", "demo-q-01-item-2": "甲"}
    answers_b = {"demo-q-01-item-1": "乙", "demo-q-01-item-2": "乙"}
    barrier = threading.Barrier(2)
    results = []
    errors = []

    def submit(team, identity, answers):
        try:
            with app.app_context():
                barrier.wait(timeout=3)
                results.append(quiz.submit_answer(room, activity, team, question, identity, answers))
        except Exception as error:  # surface thread failures in the test thread
            errors.append(error)

    threads = [threading.Thread(target=submit, args=(alpha, "a", answers_a)),
               threading.Thread(target=submit, args=(beta, "b", answers_b))]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=8)
    assert not errors
    assert all(not thread.is_alive() for thread in threads)
    assert len({result["accepted_sequence"] for result in results}) == 2


def test_submission_and_activity_end_race_is_serialized(app):
    owner, room, activity, question, _, _, alpha, _ = _setup(app)
    barrier = threading.Barrier(2)
    accepted = []
    rejected = []

    def submit():
        try:
            with app.app_context():
                barrier.wait(timeout=3)
                accepted.append(quiz.submit_answer(room, activity, alpha, question, "racing-id", {
                    "demo-q-01-item-1": "one", "demo-q-01-item-2": "two"}))
        except AppError as error:
            rejected.append(error.code)

    def end():
        with app.app_context():
            barrier.wait(timeout=3)
            activities.end_activity(owner, room, activity)

    threads = [threading.Thread(target=submit), threading.Thread(target=end)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=8)
    assert all(not thread.is_alive() for thread in threads)
    assert not rejected or rejected == ["ACTIVITY_NOT_ACTIVE"]
    with app.app_context():
        question_result = next(q for q in quiz.get_activity_results(owner, activity)["questions"]
                               if q["question_id"] == question)
    assert bool(question_result["teams"]) is bool(accepted)


def test_production_factory_registers_notes_snapshot_adapter(tmp_path, monkeypatch):
    monkeypatch.setenv("GUIDED_NOTES_SECRET_KEY", "pytest-production-factory-key")
    monkeypatch.setenv("GUIDED_NOTES_DATABASE", str(tmp_path / "production.sqlite3"))
    app = create_app({"DATABASE": str(tmp_path / "production.sqlite3")})
    assert app.config["NOTES_ENDED_SNAPSHOT"] is quiz.get_ended_snapshot


def test_student_template_guards_poll_order_and_overlapping_requests(app):
    _, _, _, _, token_a, _, _, _ = _setup(app)
    client = app.test_client()
    client.set_cookie(activities.PROOF_COOKIE, token_a)
    page = client.get("/activities/student").get_data(as_text=True)
    assert "let nextRequestSequence=0, appliedRequestSequence=0, pollInFlight=false" in page
    assert "if(pollInFlight)return" in page
    assert "if(requestSequence<=appliedRequestSequence)return" in page
    assert "Promise.all([" in page
    assert "if(s.state_version<=appliedVersion)return" in page
    assert "refreshClassroomVersion" not in page

