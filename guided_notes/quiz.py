"""Quiz submissions, ranking, authorized result views, and Notes adapter."""

from __future__ import annotations

import hashlib
import json

from flask import Blueprint, current_app, jsonify, request, session

from . import activities
from .db import get_db
from .errors import AppError
from .notes import get_catalog, get_course_catalog
from .notes_writeback import Answer, EndedSnapshot, QuestionResult

bp = Blueprint("quiz", __name__)


def _activity(connection, activity_id: str):
    row = connection.execute(
        """SELECT a.*, cl.course_id, cl.status AS classroom_status, c.teacher_id
           FROM activities a JOIN classrooms cl ON cl.id=a.classroom_id
           JOIN courses c ON c.id=cl.course_id WHERE a.id=?""", (activity_id,)
    ).fetchone()
    return row


def _catalog(activity):
    teacher_id = activity["teacher_id"]
    if current_app.config.get("DEMO_CATALOG"):
        return get_catalog(teacher_id, activity["import_id"], activity["import_version"])
    return get_course_catalog(teacher_id, activity["course_id"], activity["import_id"], activity["import_version"])


def _question_map(activity):
    connection = get_db()
    rows = connection.execute(
        "SELECT question_id, display_number, question_order FROM activity_questions WHERE activity_id=? ORDER BY question_order",
        (activity["id"],),
    ).fetchall()
    catalog = _catalog(activity)
    by_id = {q["question_id"]: q for q in catalog["questions"]}
    result = []
    for row in rows:
        question = by_id.get(row["question_id"])
        if question is None:
            raise AppError("CATALOG_NOT_FOUND", "活動固定版本的題目資料無法讀取。", 404)
        result.append({**question, "display_number": row["display_number"], "question_order": row["question_order"]})
    return result


def _validate_answers(question, answers):
    if not isinstance(answers, dict):
        raise AppError("SUBMISSION_INVALID", "請提供有效的答案資料。", 400)
    expected = [item["item_id"] for item in question["items"]]
    if set(answers) != set(expected) or len(answers) != len(expected):
        raise AppError("SUBMISSION_INVALID", "答案小題與活動題目不符。", 400)
    cleaned = {}
    for item_id in expected:
        value = answers[item_id]
        if not isinstance(value, str):
            raise AppError("SUBMISSION_INVALID", "答案必須是文字。", 400)
        if not value.strip():
            raise AppError("ANSWER_REQUIRED", "每個小題都必須填寫答案。", 400)
        if len(value) > 200:
            raise AppError("ANSWER_TOO_LONG", "每個小題答案不可超過 200 字。", 400)
        cleaned[item_id] = value.strip()
    return cleaned


def submit_answer(classroom_id: str, activity_id: str, team_id: str, question_id: str,
                  submission_id: str, answers: dict) -> dict:
    """Accept an answer set within the activities write-serialization transaction."""
    if not all(isinstance(value, str) and value.strip() for value in
               (classroom_id, activity_id, team_id, question_id, submission_id)):
        raise AppError("SUBMISSION_INVALID", "送出資料不完整。", 400)
    activity = _activity(get_db(), activity_id)
    if activity is None or activity["classroom_id"] != classroom_id:
        raise AppError("ACTIVITY_CLASSROOM_MISMATCH", "活動或課堂不可用。", 404)
    question = next((q for q in _question_map(activity) if q["question_id"] == question_id), None)
    cleaned = _validate_answers(question, answers) if question else None
    if question is None:
        # Eligibility performs the authoritative fixed question check under the write lock.
        cleaned = answers
    connection = get_db()
    try:
        with activities.immediate_transaction(connection):
            # This MUST be the first eligibility action and precede writes.
            try:
                activities.assert_submission_eligible(connection, classroom_id, activity_id, team_id, question_id)
            except AppError:
                prior = connection.execute(
                    """SELECT id, accepted_sequence FROM quiz_submissions WHERE team_id=? AND activity_id=?
                       AND question_id=? AND submission_id=?""",
                    (team_id, activity_id, question_id, submission_id),
                ).fetchone()
                if prior is None:
                    raise
                prior_answers = {r["item_id"]: r["text"] for r in connection.execute(
                    "SELECT item_id,text FROM quiz_answers WHERE submission_pk=? ORDER BY item_order", (prior["id"],))}
                if prior_answers != cleaned:
                    raise AppError("SUBMISSION_ID_REUSED", "此送出識別碼已用於不同答案。", 409)
                return {"accepted": True, "replayed": True, "accepted_sequence": prior["accepted_sequence"]}
            prior = connection.execute(
                """SELECT id, accepted_sequence FROM quiz_submissions WHERE team_id=? AND activity_id=?
                   AND question_id=? AND submission_id=?""",
                (team_id, activity_id, question_id, submission_id),
            ).fetchone()
            if prior:
                prior_answers = {r["item_id"]: r["text"] for r in connection.execute(
                    "SELECT item_id,text FROM quiz_answers WHERE submission_pk=? ORDER BY item_order", (prior["id"],))}
                if prior_answers != cleaned:
                    raise AppError("SUBMISSION_ID_REUSED", "此送出識別碼已用於不同答案。", 409)
                return {"accepted": True, "replayed": True, "accepted_sequence": prior["accepted_sequence"]}
            connection.execute(
                "UPDATE quiz_submissions SET is_current=0 WHERE team_id=? AND activity_id=? AND question_id=? AND is_current=1",
                (team_id, activity_id, question_id),
            )
            sequence = connection.execute(
                "SELECT COALESCE(MAX(accepted_sequence),0)+1 FROM quiz_submissions"
            ).fetchone()[0]
            cursor = connection.execute(
                "INSERT INTO quiz_submissions(activity_id,team_id,question_id,submission_id,accepted_sequence) VALUES(?,?,?,?,?)",
                (activity_id, team_id, question_id, submission_id, sequence),
            )
            submission_pk = cursor.lastrowid
            connection.executemany(
                "INSERT INTO quiz_answers(submission_pk,item_id,text,item_order) VALUES(?,?,?,?)",
                [(submission_pk, item["item_id"], cleaned[item["item_id"]], order)
                 for order, item in enumerate(question["items"], 1)],
            )
            return {"accepted": True, "replayed": False, "accepted_sequence": sequence}
    except AppError:
        raise


def _results_for_activity(activity, allow_active=False):
    questions = _question_map(activity)
    connection = get_db()
    output = []
    for question in questions:
        submissions = connection.execute(
            """SELECT s.id,s.team_id,t.name AS team_name,s.accepted_sequence FROM quiz_submissions s
               JOIN teams t ON t.id=s.team_id WHERE s.activity_id=? AND s.question_id=? AND s.is_current=1
               ORDER BY s.accepted_sequence""", (activity["id"], question["question_id"])
        ).fetchall()
        teams = []
        for rank, submission in enumerate(submissions, 1):
            answers = [dict(r) for r in connection.execute(
                "SELECT item_id,text FROM quiz_answers WHERE submission_pk=? ORDER BY item_order", (submission["id"],))]
            teams.append({"team_id": submission["team_id"], "team_name": submission["team_name"],
                          "answers": answers, "accepted_sequence": submission["accepted_sequence"],
                          "rank": rank, "is_winner": rank == 1})
        winner = teams[0] if teams else None
        output.append({"question_id": question["question_id"], "display_number": question["display_number"],
                       "winner_id": winner["team_id"] if winner else None,
                       "winner_name": winner["team_name"] if winner else None, "teams": teams})
    return output


def get_activity_results(teacher_id: int, activity_id: str) -> dict:
    """Return fixed-version result fields for an ended activity owned by teacher_id."""
    row = _activity(get_db(), activity_id)
    if row is None or row["teacher_id"] != teacher_id:
        raise AppError("ACTIVITY_NOT_FOUND", "找不到此活動或無權存取。", 404)
    if row["status"] != "ended":
        raise AppError("RESULT_NOT_READY", "活動尚未結束，結果尚未產生。", 409)
    return {"activity_id": activity_id, "import_id": row["import_id"], "import_version": row["import_version"],
            "questions": _results_for_activity(row)}


def get_ended_snapshot(teacher_id: int, activity_id: str) -> EndedSnapshot | None:
    """Adapt authorized quiz results to Notes writeback's frozen DTO contract."""
    row = _activity(get_db(), activity_id)
    if row is None or row["teacher_id"] != teacher_id:
        return None
    questions = _question_map(row)
    if row["status"] != "ended":
        return EndedSnapshot(activity_id, teacher_id, row["import_id"], row["import_version"], False, False,
                             tuple(QuestionResult(q["question_id"], None, ()) for q in questions))
    data = _results_for_activity(row)
    results = []
    for question in data:
        winner = question["teams"][0] if question["teams"] else None
        answers = tuple(Answer(a["item_id"], a["text"]) for a in winner["answers"]) if winner else ()
        results.append(QuestionResult(question["question_id"], winner["team_id"] if winner else None, answers))
    return EndedSnapshot(activity_id, teacher_id, row["import_id"], row["import_version"], True, True, tuple(results))


def _student_activity(token):
    proof = activities._proof(get_db(), token)
    if proof["classroom_status"] == "closed":
        return proof, None
    selected = activities._selected_activity(get_db(), proof["classroom_id"])
    row = _activity(get_db(), selected["id"]) if selected is not None else None
    return proof, row


@bp.get("/api/activity/<activity_id>/content")
def student_activity_content(activity_id):
    proof, row = _student_activity(request.cookies.get(activities.PROOF_COOKIE))
    if row is None or row["id"] != activity_id:
        raise AppError("ACTIVITY_NOT_FOUND", "找不到此活動。", 404)
    questions = []
    for q in _question_map(row):
        questions.append({"question_id": q["question_id"], "display_number": q["display_number"],
                          "question_text": q.get("question_text", ""),
                          "items": [{"item_id": item["item_id"], "label": item.get("label", ""),
                                     "item_text": item.get("item_text", "")} for item in q["items"]]})
    return jsonify({"activity_id": activity_id, "questions": questions})


@bp.get("/api/student/state")
def student_quiz_state():
    proof, activity = _student_activity(request.cookies.get(activities.PROOF_COOKIE))
    if proof["classroom_status"] == "closed":
        return jsonify({"classroom_ended": True})
    state = {"classroom_id": proof["classroom_id"], "classroom_ended": False, "activity_id": activity["id"] if activity else None,
             "phase": activity["status"] if activity else None, "submissions": []}
    if activity is not None:
        for q in _results_for_activity(activity):
            mine = next((team for team in q["teams"] if team["team_id"] == proof["team_id"]), None)
            if activity["status"] == "ended":
                winner = q["teams"][0] if q["teams"] else None
                state["submissions"].append({"question_id": q["question_id"], "display_number": q["display_number"],
                    "winner": ({"team_name": winner["team_name"], "answers": winner["answers"]} if winner else None),
                    "mine": ({"answers": mine["answers"], "rank": mine["rank"]} if mine else None)})
            else:
                state["submissions"].append({"question_id": q["question_id"], "display_number": q["display_number"],
                    "submitted": mine is not None,
                    "answers": mine["answers"] if mine else []})
    return jsonify(state)


@bp.get("/api/classrooms/<classroom_id>/activities/<activity_id>/state")
def teacher_quiz_state(classroom_id, activity_id):
    teacher_id = session.get("teacher_id")
    row = _activity(get_db(), activity_id)
    if not teacher_id:
        raise AppError("TEACHER_REQUIRED", "請先登入教師帳號。", 401)
    if row is None or row["teacher_id"] != teacher_id or row["classroom_id"] != classroom_id:
        raise AppError("ACTIVITY_NOT_FOUND", "找不到此活動或無權存取。", 404)
    return jsonify({"activity_id": activity_id, "phase": row["status"],
                    "questions": _results_for_activity(row)})


@bp.post("/api/classrooms/<classroom_id>/activities/<activity_id>/submissions")
def submit_api(classroom_id, activity_id):
    proof = activities._proof(get_db(), request.cookies.get(activities.PROOF_COOKIE))
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        raise AppError("SUBMISSION_INVALID", "請提供有效的送出資料。", 400)
    result = submit_answer(classroom_id, activity_id, proof["team_id"], data.get("question_id"),
                           data.get("submission_id"), data.get("answers"))
    return jsonify(result)


@bp.get("/api/results/<activity_id>")
def results_api(activity_id):
    teacher_id = session.get("teacher_id")
    if not teacher_id:
        raise AppError("TEACHER_REQUIRED", "請先登入教師帳號。", 401)
    return jsonify(get_activity_results(teacher_id, activity_id))


@bp.get("/")
def placeholder():
    return "Quiz 作答與結果 API 已啟用。"
