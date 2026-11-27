"""Teacher-owned Notes versions, import previews and writeback plans."""

import json
from uuid import uuid4

from .db import get_db
from .errors import AppError
from .notes_format import catalog_questions


def teacher_versions(teacher_id: int, course_id: str | None = None) -> list:
    statement = "SELECT * FROM notes_versions WHERE teacher_id = ?"
    parameters = [teacher_id]
    if course_id is not None:
        statement += " AND course_id = ?"
        parameters.append(course_id)
    return get_db().execute(statement + " ORDER BY title, import_id, import_version DESC", parameters).fetchall()


def version_catalog(version, *, include_text: bool = False) -> dict:
    layout = json.loads(version["layout"])
    questions = catalog_questions(layout)
    if include_text:
        for question, source in zip(questions, layout):
            question["question_text"] = _display_text(source)
            if question["type"] == "group":
                for item, source_item in zip(question["items"], source["items"]):
                    item["item_text"] = _display_text(source_item)
    return {
        "import_id": version["import_id"],
        "import_version": str(version["import_version"]),
        "title": version["title"],
        "questions": questions,
    }


def _display_text(source: dict) -> str:
    return "\n".join(text for text in source.get("source_text", []) if text.strip())


def find_version(teacher_id: int, import_id: str, version: str):
    # Compare the string form so "01" cannot accidentally match version "1".
    return get_db().execute(
        "SELECT * FROM notes_versions WHERE teacher_id = ? AND import_id = ? AND CAST(import_version AS TEXT) = ?",
        (teacher_id, import_id, version),
    ).fetchone()


def find_writeback_activity(teacher_id: int, course_id: str, activity_id: str):
    """Read the activity's frozen version and phase through its owning course."""
    return get_db().execute(
        """SELECT a.import_id, a.import_version, a.status
           FROM activities AS a
           JOIN classrooms AS cl ON cl.id = a.classroom_id
           JOIN courses AS c ON c.id = cl.course_id
           WHERE a.id = ? AND c.id = ? AND c.teacher_id = ?""",
        (activity_id, course_id, teacher_id),
    ).fetchone()


def create_import_preview(teacher_id: int, course_id: str, spreadsheet_id: str, sheet_id: int,
                          title: str, layout: list[dict]) -> str:
    preview_id = uuid4().hex
    db = get_db()
    with db:
        db.execute(
            """INSERT INTO notes_import_previews (id, teacher_id, course_id, spreadsheet_id, sheet_id, title, layout)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (preview_id, teacher_id, course_id, spreadsheet_id, sheet_id, title, json.dumps(layout, ensure_ascii=False)),
        )
    return preview_id


def save_import(teacher_id: int, course_id: str, preview_id: str) -> tuple[str, str]:
    db = get_db()
    with db:
        # Reserve the version number and consume the preview in the same transaction.
        db.execute("BEGIN IMMEDIATE")
        preview = db.execute(
            "SELECT * FROM notes_import_previews WHERE id = ? AND teacher_id = ? AND course_id = ?",
            (preview_id, teacher_id, course_id),
        ).fetchone()
        if preview is None:
            raise AppError("NOTES_PREVIEW_NOT_FOUND", "找不到可保存的講義預覽。", 404)
        if preview["import_id"] is not None:
            return preview["import_id"], str(preview["import_version"])
        source = (teacher_id, course_id, preview["spreadsheet_id"], preview["sheet_id"])
        previous = db.execute(
            """SELECT import_id, import_version FROM notes_versions
               WHERE teacher_id = ? AND course_id = ? AND spreadsheet_id = ? AND sheet_id = ?
               ORDER BY import_version DESC LIMIT 1""",
            source,
        ).fetchone()
        import_id = previous["import_id"] if previous else uuid4().hex
        version = previous["import_version"] + 1 if previous else 1
        db.execute(
            """INSERT INTO notes_versions
               (import_id, import_version, teacher_id, course_id, spreadsheet_id, sheet_id, title, layout)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (import_id, version, *source, preview["title"], preview["layout"]),
        )
        db.execute(
            "UPDATE notes_import_previews SET import_id = ?, import_version = ? WHERE id = ?",
            (import_id, version, preview_id),
        )
        return import_id, str(version)


def load_writeback(teacher_id: int, activity_id: str):
    return get_db().execute(
        "SELECT id, data, attempted FROM notes_writeback_plans WHERE teacher_id = ? AND activity_id = ?",
        (teacher_id, activity_id),
    ).fetchone()


def save_writeback(teacher_id: int, activity_id: str, plan: dict, attempted: bool) -> str:
    preview_id = uuid4().hex
    db = get_db()
    with db:
        db.execute(
            """INSERT INTO notes_writeback_plans (teacher_id, activity_id, id, data, attempted) VALUES (?, ?, ?, ?, ?)
               ON CONFLICT (teacher_id, activity_id) DO UPDATE
               SET id = excluded.id, data = excluded.data, attempted = excluded.attempted""",
            (teacher_id, activity_id, preview_id, json.dumps(plan, ensure_ascii=False), attempted),
        )
    return preview_id


def mark_writeback_attempted(teacher_id: int, activity_id: str) -> None:
    db = get_db()
    with db:
        db.execute(
            "UPDATE notes_writeback_plans SET attempted = 1 WHERE teacher_id = ? AND activity_id = ?",
            (teacher_id, activity_id),
        )


def update_writeback_plan(teacher_id: int, activity_id: str, plan: dict) -> None:
    db = get_db()
    with db:
        db.execute(
            "UPDATE notes_writeback_plans SET data = ? WHERE teacher_id = ? AND activity_id = ?",
            (json.dumps(plan, ensure_ascii=False), teacher_id, activity_id),
        )
