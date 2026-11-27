"""Course, classroom, student membership and activity lifecycle."""

from __future__ import annotations

import hashlib
import secrets
import sqlite3
import uuid
from contextlib import contextmanager

from flask import Blueprint, abort, current_app, jsonify, make_response, redirect, render_template, request, session, url_for

from .db import get_db
from .errors import AppError
from .notes import get_catalog, list_available_catalogs


bp = Blueprint("activities", __name__)
PROOF_COOKIE = "guided_notes_join_proof"
JOIN_ALPHABET = "23456789ABCDEFGHJKLMNPQRSTUVWXYZ"


def _id() -> str:
    return str(uuid.uuid4())


def _not_found() -> AppError:
    return AppError("RESOURCE_NOT_FOUND", "找不到可供此使用者存取的資源。", 404)


def _require_teacher_id(teacher_id: int | None) -> int:
    if teacher_id is None:
        raise AppError("TEACHER_REQUIRED", "請先登入教師帳號。", 401)
    row = get_db().execute("SELECT 1 FROM teachers WHERE id = ?", (teacher_id,)).fetchone()
    if row is None:
        raise AppError("TEACHER_REQUIRED", "請先登入教師帳號。", 401)
    return teacher_id


def _owned_course(connection: sqlite3.Connection, course_id: str, teacher_id: int):
    row = connection.execute(
        "SELECT * FROM courses WHERE id = ? AND teacher_id = ?", (course_id, teacher_id)
    ).fetchone()
    if row is None:
        raise _not_found()
    return row


def _owned_classroom(connection: sqlite3.Connection, classroom_id: str, teacher_id: int):
    row = connection.execute(
        """SELECT cl.*, c.teacher_id FROM classrooms cl
           JOIN courses c ON c.id = cl.course_id
           WHERE cl.id = ? AND c.teacher_id = ?""",
        (classroom_id, teacher_id),
    ).fetchone()
    if row is None:
        raise _not_found()
    return row


@contextmanager
def immediate_transaction(connection: sqlite3.Connection):
    """Serialize a state transition or quiz write with BEGIN IMMEDIATE."""
    if connection.in_transaction:
        raise RuntimeError("activities transaction must begin before any database statement")
    connection.execute("BEGIN IMMEDIATE")
    try:
        yield connection
        connection.commit()
    except BaseException:
        connection.rollback()
        raise


def create_course(teacher_id: int, name: str) -> str:
    teacher_id = _require_teacher_id(teacher_id)
    name = (name or "").strip()
    if not name:
        raise AppError("COURSE_NAME_REQUIRED", "請輸入課程名稱。")
    course_id = _id()
    connection = get_db()
    connection.execute("INSERT INTO courses(id, teacher_id, name) VALUES (?, ?, ?)", (course_id, teacher_id, name))
    connection.commit()
    return course_id


def list_courses(teacher_id: int) -> list[dict]:
    teacher_id = _require_teacher_id(teacher_id)
    return [dict(row) for row in get_db().execute(
        "SELECT id, name, created_at FROM courses WHERE teacher_id = ? ORDER BY created_at DESC, rowid DESC", (teacher_id,)
    ).fetchall()]


def add_course_catalog(teacher_id: int, course_id: str, import_id: str, import_version: str) -> None:
    teacher_id = _require_teacher_id(teacher_id)
    connection = get_db()
    _owned_course(connection, course_id, teacher_id)
    summary = next((item for item in list_available_catalogs(teacher_id)
                    if item["import_id"] == import_id and item["import_version"] == import_version), None)
    if summary is None:
        raise AppError("CATALOG_NOT_FOUND", "找不到可供此教師存取的題目清單。", 404)
    connection.execute(
        "INSERT OR IGNORE INTO course_catalogs(course_id, import_id, import_version, title, question_count) VALUES (?, ?, ?, ?, ?)",
        (course_id, import_id, import_version, summary["title"], summary["question_count"]),
    )
    connection.commit()


def list_course_catalogs(teacher_id: int, course_id: str) -> list[dict]:
    _require_teacher_id(teacher_id)
    connection = get_db()
    _owned_course(connection, course_id, teacher_id)
    return [dict(row) for row in connection.execute(
        "SELECT import_id, import_version, title, question_count FROM course_catalogs WHERE course_id = ? ORDER BY rowid", (course_id,)
    ).fetchall()]


def _new_join_code(connection: sqlite3.Connection) -> str:
    for _ in range(100):
        candidate = "".join(secrets.choice(JOIN_ALPHABET) for _ in range(6))
        if connection.execute("SELECT 1 FROM classrooms WHERE join_code = ? AND status = 'open'", (candidate,)).fetchone() is None:
            return candidate
    raise AppError("JOIN_CODE_UNAVAILABLE", "目前無法產生加入碼，請稍後再試。", 503)


def create_classroom(teacher_id: int, course_id: str, name: str) -> str:
    _require_teacher_id(teacher_id)
    name = (name or "").strip()
    if not name:
        raise AppError("CLASSROOM_NAME_REQUIRED", "請輸入課堂名稱。")
    connection = get_db()
    classroom_id = _id()
    with immediate_transaction(connection):
        _owned_course(connection, course_id, teacher_id)
        code = _new_join_code(connection)
        connection.execute(
            "INSERT INTO classrooms(id, course_id, name, join_code) VALUES (?, ?, ?, ?)",
            (classroom_id, course_id, name, code),
        )
    return classroom_id


def _normalize_team_name(name: str) -> tuple[str, str]:
    display = " ".join((name or "").split())
    if not 1 <= len(display) <= 20:
        raise AppError("TEAM_NAME_INVALID", "組名長度須為 1 至 20 字。")
    return display, display.casefold()


def join_classroom(join_code: str, team_name: str) -> tuple[str, str]:
    display, name_key = _normalize_team_name(team_name)
    connection = get_db()
    token = secrets.token_urlsafe(32)
    with immediate_transaction(connection):
        classroom = connection.execute(
            "SELECT id FROM classrooms WHERE join_code = ? AND status = 'open'", ((join_code or "").strip().upper(),)
        ).fetchone()
        if classroom is None:
            raise AppError("CLASSROOM_NOT_JOINABLE", "課堂不存在或已結束，無法加入。", 404)
        team = connection.execute(
            "SELECT id FROM teams WHERE classroom_id = ? AND name_key = ?", (classroom["id"], name_key)
        ).fetchone()
        team_id = team["id"] if team else _id()
        if team is None:
            connection.execute(
                "INSERT INTO teams(id, classroom_id, name, name_key) VALUES (?, ?, ?, ?)",
                (team_id, classroom["id"], display, name_key),
            )
        connection.execute(
            "INSERT INTO student_proofs(id, classroom_id, team_id, token_hash) VALUES (?, ?, ?, ?)",
            (_id(), classroom["id"], team_id, hashlib.sha256(token.encode()).hexdigest()),
        )
        connection.execute("UPDATE classrooms SET state_version = state_version + 1 WHERE id = ?", (classroom["id"],))
    return token, classroom["id"]


def _proof(connection: sqlite3.Connection, token: str | None):
    if not token:
        raise AppError("STUDENT_PROOF_INVALID", "加入證明無效或已失效。", 401)
    token_hash = hashlib.sha256(token.encode()).hexdigest()
    row = connection.execute(
        """SELECT p.classroom_id, p.team_id, t.name AS team_name, cl.name AS classroom_name,
                  cl.status AS classroom_status, cl.state_version
           FROM student_proofs p JOIN teams t ON t.id = p.team_id
           JOIN classrooms cl ON cl.id = p.classroom_id
           WHERE p.token_hash = ? AND p.revoked_at IS NULL AND t.classroom_id = p.classroom_id""",
        (token_hash,),
    ).fetchone()
    if row is None:
        raise AppError("STUDENT_PROOF_INVALID", "加入證明無效或已失效。", 401)
    return row


def _selected_activity(connection: sqlite3.Connection, classroom_id: str):
    # Preparing rows use created_at, then SQLite's implicit rowid. Activities are
    # append-only (there is no delete operation), so rowid preserves insert order
    # when several activities share the same second-precision created_at value.
    return connection.execute(
        """SELECT * FROM activities WHERE classroom_id = ?
           ORDER BY CASE status WHEN 'active' THEN 0 WHEN 'preparing' THEN 1 ELSE 2 END,
                    CASE status WHEN 'preparing' THEN created_at END DESC,
                    CASE status WHEN 'ended' THEN ended_seq END DESC,
                    rowid DESC LIMIT 1""",
        (classroom_id,),
    ).fetchone()


def _question_numbers(connection: sqlite3.Connection, activity_id: str) -> list[str]:
    return [row[0] for row in connection.execute(
        "SELECT display_number FROM activity_questions WHERE activity_id = ? ORDER BY question_order", (activity_id,)
    ).fetchall()]


def student_state(token: str | None) -> dict:
    connection = get_db()
    proof = _proof(connection, token)
    activity = _selected_activity(connection, proof["classroom_id"])
    result = {
        "classroom_name": proof["classroom_name"], "team_name": proof["team_name"],
        "classroom_status": proof["classroom_status"], "classroom_ended": proof["classroom_status"] == "closed",
        "activity": None, "state_version": proof["state_version"],
    }
    if activity is not None:
        result["activity"] = {
            "id": activity["id"], "name": activity["title"], "phase": activity["status"],
            "question_numbers": _question_numbers(connection, activity["id"]),
        }
    return result


def create_activity(teacher_id: int, classroom_id: str, import_id: str, import_version: str, title: str | None = None) -> str:
    _require_teacher_id(teacher_id)
    connection = get_db()
    classroom = _owned_classroom(connection, classroom_id, teacher_id)
    if classroom["status"] != "open":
        raise AppError("CLASSROOM_CLOSED", "課堂已結束，不能建立活動。", 409)
    catalog_link = connection.execute(
        """SELECT cc.title FROM course_catalogs cc JOIN classrooms cl ON cl.course_id = cc.course_id
           WHERE cl.id = ? AND cc.import_id = ? AND cc.import_version = ?""",
        (classroom_id, import_id, import_version),
    ).fetchone()
    if catalog_link is None:
        raise AppError("CATALOG_NOT_IN_COURSE", "此題目清單尚未加入課程。", 404)
    catalog = get_catalog(teacher_id, import_id, import_version)
    activity_id = _id()
    activity_title = (title or "").strip() or catalog_link["title"]
    with immediate_transaction(connection):
        # Recheck under the write lock to serialize with close-classroom.
        classroom = _owned_classroom(connection, classroom_id, teacher_id)
        if classroom["status"] != "open":
            raise AppError("CLASSROOM_CLOSED", "課堂已結束，不能建立活動。", 409)
        connection.execute(
            "INSERT INTO activities(id, classroom_id, import_id, import_version, title) VALUES (?, ?, ?, ?, ?)",
            (activity_id, classroom_id, import_id, import_version, activity_title),
        )
        connection.executemany(
            "INSERT INTO activity_questions(activity_id, question_id, display_number, question_order) VALUES (?, ?, ?, ?)",
            [(activity_id, q["question_id"], q["display_number"], index)
             for index, q in enumerate(catalog["questions"], 1)],
        )
        connection.execute("UPDATE classrooms SET state_version = state_version + 1 WHERE id = ?", (classroom_id,))
    return activity_id


def _transition_activity(teacher_id: int, classroom_id: str, activity_id: str, transition: str) -> None:
    _require_teacher_id(teacher_id)
    connection = get_db()
    with immediate_transaction(connection):
        classroom = _owned_classroom(connection, classroom_id, teacher_id)
        if classroom["status"] != "open":
            raise AppError("CLASSROOM_CLOSED", "課堂已結束。", 409)
        activity = connection.execute(
            "SELECT status FROM activities WHERE id = ? AND classroom_id = ?", (activity_id, classroom_id)
        ).fetchone()
        if activity is None:
            raise _not_found()
        if transition == "start":
            if activity["status"] != "preparing":
                raise AppError("ACTIVITY_NOT_PREPARING", "只有準備中的活動可以開始。", 409)
            if connection.execute("SELECT 1 FROM activities WHERE classroom_id = ? AND status = 'active'", (classroom_id,)).fetchone():
                raise AppError("ACTIVITY_ALREADY_ACTIVE", "此課堂已有搶答中的活動。", 409)
            connection.execute("UPDATE activities SET status='active', started_at=CURRENT_TIMESTAMP WHERE id=?", (activity_id,))
            connection.execute("UPDATE classrooms SET state_version = state_version + 1 WHERE id = ?", (classroom_id,))
        else:
            if activity["status"] != "active":
                raise AppError("ACTIVITY_NOT_ACTIVE", "只有搶答中的活動可以結束。", 409)
            connection.execute("UPDATE classrooms SET state_version = state_version + 1 WHERE id = ?", (classroom_id,))
            end_sequence = connection.execute(
                "SELECT state_version FROM classrooms WHERE id = ?", (classroom_id,)
            ).fetchone()[0]
            connection.execute(
                "UPDATE activities SET status='ended', ended_at=CURRENT_TIMESTAMP, ended_seq=? WHERE id=?",
                (end_sequence, activity_id),
            )


def start_activity(teacher_id: int, classroom_id: str, activity_id: str) -> None:
    _transition_activity(teacher_id, classroom_id, activity_id, "start")


def end_activity(teacher_id: int, classroom_id: str, activity_id: str) -> None:
    _transition_activity(teacher_id, classroom_id, activity_id, "end")


def close_classroom(teacher_id: int, classroom_id: str) -> None:
    _require_teacher_id(teacher_id)
    connection = get_db()
    with immediate_transaction(connection):
        classroom = _owned_classroom(connection, classroom_id, teacher_id)
        if classroom["status"] == "closed":
            return
        connection.execute("UPDATE classrooms SET status='closed', closed_at=CURRENT_TIMESTAMP, state_version=state_version+1 WHERE id=?", (classroom_id,))
        end_sequence = connection.execute(
            "SELECT state_version FROM classrooms WHERE id = ?", (classroom_id,)
        ).fetchone()[0]
        connection.execute(
            "UPDATE activities SET status='ended', ended_at=CURRENT_TIMESTAMP, ended_seq=? WHERE classroom_id=? AND status='active'",
            (end_sequence, classroom_id),
        )


def assert_submission_eligible(connection: sqlite3.Connection, classroom_id: str, activity_id: str,
                               team_id: str, question_id: str) -> None:
    """Raise AppError unless a quiz submission is eligible inside the caller's transaction.

    The caller must execute BEGIN IMMEDIATE before calling, write the answer on
    this same connection, and commit/rollback the entire transaction itself.
    This function never starts, commits, or rolls back a transaction.
    """
    if not connection.in_transaction:
        raise RuntimeError("assert_submission_eligible requires an active caller-owned transaction")
    classroom = connection.execute("SELECT status FROM classrooms WHERE id=?", (classroom_id,)).fetchone()
    if classroom is None:
        raise AppError("ACTIVITY_CLASSROOM_MISMATCH", "活動或課堂不可用。", 404)
    if classroom["status"] != "open":
        raise AppError("CLASSROOM_CLOSED", "課堂已結束，不能送出答案。", 409)
    activity = connection.execute(
        "SELECT status FROM activities WHERE id=? AND classroom_id=?", (activity_id, classroom_id)
    ).fetchone()
    if activity is None:
        raise AppError("ACTIVITY_CLASSROOM_MISMATCH", "活動或課堂不可用。", 404)
    if activity["status"] != "active":
        raise AppError("ACTIVITY_NOT_ACTIVE", "活動目前不接受答案。", 409)
    team = connection.execute("SELECT 1 FROM teams WHERE id=? AND classroom_id=?", (team_id, classroom_id)).fetchone()
    if team is None:
        raise AppError("TEAM_CLASSROOM_MISMATCH", "組別不屬於此課堂。", 404)
    question = connection.execute(
        "SELECT 1 FROM activity_questions WHERE activity_id=? AND question_id=?", (activity_id, question_id)
    ).fetchone()
    if question is None:
        raise AppError("QUESTION_NOT_IN_ACTIVITY", "題目不屬於此活動。", 404)


def _teacher_classrooms(teacher_id: int, course_id: str) -> list[dict]:
    connection = get_db()
    _owned_course(connection, course_id, teacher_id)
    rows = connection.execute("SELECT * FROM classrooms WHERE course_id=? ORDER BY created_at DESC, rowid DESC", (course_id,)).fetchall()
    return [dict(row) for row in rows]


def _teacher_classroom_data(teacher_id: int, classroom_id: str) -> dict:
    connection = get_db()
    classroom = dict(_owned_classroom(connection, classroom_id, teacher_id))
    classroom["teams"] = [dict(r) for r in connection.execute(
        "SELECT id, name FROM teams WHERE classroom_id=? ORDER BY created_at, rowid", (classroom_id,)
    ).fetchall()]
    classroom["activities"] = []
    for row in connection.execute("SELECT * FROM activities WHERE classroom_id=? ORDER BY created_at, rowid", (classroom_id,)).fetchall():
        activity = dict(row)
        activity["question_numbers"] = _question_numbers(connection, activity["id"])
        classroom["activities"].append(activity)
    return classroom


@bp.get("/")
def placeholder():
    return redirect(url_for("activities.teacher_courses")) if session.get("teacher_id") else render_template("activities_join.html")


@bp.get("/teacher/courses")
def teacher_courses():
    if not session.get("teacher_id"):
        return redirect(url_for("auth.login"))
    return render_template("activities_courses.html", courses=list_courses(session["teacher_id"]))


@bp.post("/teacher/courses")
def teacher_create_course():
    course_id = create_course(session.get("teacher_id"), request.form.get("name", ""))
    return redirect(url_for("activities.teacher_course", course_id=course_id))


@bp.get("/teacher/courses/<course_id>")
def teacher_course(course_id):
    teacher_id = session.get("teacher_id")
    if not teacher_id:
        return redirect(url_for("auth.login"))
    connection = get_db()
    course = dict(_owned_course(connection, course_id, teacher_id))
    catalogs = list_course_catalogs(teacher_id, course_id)
    available = list_available_catalogs(teacher_id)
    classrooms = _teacher_classrooms(teacher_id, course_id)
    return render_template("activities_course.html", course=course, catalogs=catalogs,
                           available=available, classrooms=classrooms)


@bp.post("/teacher/courses/<course_id>/catalogs")
def teacher_add_catalog(course_id):
    add_course_catalog(session.get("teacher_id"), course_id, request.form.get("import_id", ""), request.form.get("import_version", ""))
    return redirect(url_for("activities.teacher_course", course_id=course_id))


@bp.post("/teacher/courses/<course_id>/classrooms")
def teacher_create_classroom(course_id):
    classroom_id = create_classroom(session.get("teacher_id"), course_id, request.form.get("name", ""))
    return redirect(url_for("activities.teacher_classroom", classroom_id=classroom_id))


@bp.get("/teacher/classrooms/<classroom_id>")
def teacher_classroom(classroom_id):
    teacher_id = session.get("teacher_id")
    if not teacher_id:
        return redirect(url_for("auth.login"))
    classroom = _teacher_classroom_data(teacher_id, classroom_id)
    catalogs = list_course_catalogs(teacher_id, classroom["course_id"])
    return render_template("activities_classroom.html", classroom=classroom, catalogs=catalogs)


@bp.post("/teacher/classrooms/<classroom_id>/activities")
def teacher_create_activity(classroom_id):
    activity_id = create_activity(session.get("teacher_id"), classroom_id,
                                  request.form.get("import_id", ""), request.form.get("import_version", ""),
                                  request.form.get("title"))
    return redirect(url_for("activities.teacher_classroom", classroom_id=classroom_id))


@bp.post("/teacher/classrooms/<classroom_id>/activities/<activity_id>/<action>")
def teacher_transition_activity(classroom_id, activity_id, action):
    if action == "start":
        start_activity(session.get("teacher_id"), classroom_id, activity_id)
    elif action == "end":
        end_activity(session.get("teacher_id"), classroom_id, activity_id)
    else:
        abort(404)
    return redirect(url_for("activities.teacher_classroom", classroom_id=classroom_id))


@bp.post("/teacher/classrooms/<classroom_id>/close")
def teacher_close_classroom(classroom_id):
    close_classroom(session.get("teacher_id"), classroom_id)
    return redirect(url_for("activities.teacher_classroom", classroom_id=classroom_id))


@bp.get("/api/classrooms/<classroom_id>/state")
def teacher_state_api(classroom_id):
    teacher_id = session.get("teacher_id")
    if not teacher_id:
        raise AppError("TEACHER_REQUIRED", "請先登入教師帳號。", 401)
    classroom = _owned_classroom(get_db(), classroom_id, teacher_id)
    activity = _selected_activity(get_db(), classroom_id)
    return jsonify(_teacher_state(classroom, activity))


def _teacher_state(classroom, activity):
    result = {"classroom_id": classroom["id"], "classroom_name": classroom["name"],
              "classroom_status": classroom["status"], "state_version": classroom["state_version"], "activity": None}
    if activity:
        result["activity"] = {"id": activity["id"], "name": activity["title"], "phase": activity["status"],
                              "question_numbers": _question_numbers(get_db(), activity["id"])}
    return result


@bp.get("/join")
def student_join_page():
    return render_template("activities_join.html")


@bp.post("/join")
def student_join():
    token, _classroom_id = join_classroom(request.form.get("join_code", ""), request.form.get("team_name", ""))
    response = make_response(redirect(url_for("activities.student_page")))
    response.set_cookie(PROOF_COOKIE, token, httponly=True, samesite="Lax", secure=bool(request.is_secure), path="/")
    return response


@bp.get("/student")
def student_page():
    state = student_state(request.cookies.get(PROOF_COOKIE))
    return render_template("activities_student.html", state=state)


@bp.get("/api/student/state")
def student_state_api():
    return jsonify(student_state(request.cookies.get(PROOF_COOKIE)))
