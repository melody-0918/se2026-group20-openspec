"""Notes Blueprint and teacher-scoped catalog interface."""

from flask import Blueprint, current_app, jsonify, render_template, request, session

from .db import get_db
from .errors import AppError
from .notes_format import catalog_questions, parse_layout
from .notes_sheets import GoogleSheets, authorize_sheets, google_credentials_paths, source_from_link
from .notes_store import create_import_preview, save_import, teacher_versions, version_catalog
from .notes_writeback import process_writeback
from .pages import teacher_required


bp = Blueprint("notes", __name__)
bp.cli.add_command(authorize_sheets)

_DEMO_CATALOG = {
    "import_id": "demo-guided-notes",
    "import_version": "1",
    "title": "示範用填空學習單",
    "questions": [
        {
            "question_id": "demo-q-01",
            "display_number": "1",
            "type": "group",
            "items": [
                {"item_id": "demo-q-01-item-1", "label": "(1)", "order": 1},
                {"item_id": "demo-q-01-item-2", "label": "(2)", "order": 2},
            ],
        },
        {
            "question_id": "demo-q-02",
            "display_number": "2",
            "type": "single",
            "items": [{"item_id": "demo-q-02-item-1", "label": "", "order": 1}],
        },
        {
            "question_id": "demo-q-03",
            "display_number": "3",
            "type": "single",
            "items": [{"item_id": "demo-q-03-item-1", "label": "", "order": 1}],
        },
    ],
}


@bp.get("/")
def placeholder():
    return "Notes 模組掛載點尚未開放實際匯入功能。"


def _demo_enabled() -> bool:
    return bool(current_app.config.get("DEMO_CATALOG"))


def _catalogs_for_teacher(teacher_id: int) -> list[dict]:
    return [version_catalog(version) for version in teacher_versions(teacher_id)]


def _require_teacher(teacher_id: int) -> None:
    if teacher_id is None:
        raise AppError("TEACHER_REQUIRED", "需要有效的教師身分才能讀取題目清單。", 401)
    teacher = get_db().execute("SELECT 1 FROM teachers WHERE id = ?", (teacher_id,)).fetchone()
    if teacher is None:
        raise AppError("TEACHER_REQUIRED", "需要有效的教師身分才能讀取題目清單。", 401)


def list_available_catalogs(teacher_id: int) -> list[dict]:
    """List catalogs available to a teacher (demo data is shared to logged-in callers)."""
    _require_teacher(teacher_id)
    if _demo_enabled():
        return [
            {
                "import_id": _DEMO_CATALOG["import_id"],
                "import_version": _DEMO_CATALOG["import_version"],
                "title": _DEMO_CATALOG["title"],
                "question_count": len(_DEMO_CATALOG["questions"]),
            }
        ]
    return [
        {
            "import_id": catalog["import_id"],
            "import_version": catalog["import_version"],
            "title": catalog["title"],
            "question_count": len(catalog["questions"]),
        }
        for catalog in _catalogs_for_teacher(teacher_id)
    ]


def get_catalog(teacher_id: int, import_id: str, import_version: str) -> dict:
    """Get one teacher-accessible catalog without exposing another owner's data."""
    _require_teacher(teacher_id)
    if _demo_enabled():
        available = [_DEMO_CATALOG]
    else:
        available = _catalogs_for_teacher(teacher_id)
    for catalog in available:
        if catalog["import_id"] == import_id and catalog["import_version"] == import_version:
            return {
                "import_id": catalog["import_id"],
                "import_version": catalog["import_version"],
                "questions": [
                    {
                        **question,
                        "items": [dict(item) for item in question["items"]],
                    }
                    for question in catalog["questions"]
                ],
            }
    raise AppError("CATALOG_NOT_FOUND", "找不到可供此教師存取的題目清單。", 404)


def _course_teacher(course_id: str) -> int:
    teacher_id = session.get("teacher_id")
    _require_teacher(teacher_id)
    check_access = current_app.config.get("NOTES_COURSE_ACCESS")
    if check_access is None:
        raise AppError("NOTES_INTEGRATION_PENDING", "尚未接入課程授權。", 503)
    if not check_access(teacher_id, course_id):
        raise AppError("COURSE_FORBIDDEN", "無法存取這門課程的講義。", 403)
    return teacher_id


def _sheets():
    return current_app.config.get("NOTES_SHEETS_FACTORY", GoogleSheets)()


def _form() -> dict:
    data = request.get_json(silent=True) if request.is_json else request.form
    if isinstance(data, dict):
        return data
    raise AppError("NOTES_REQUEST_INVALID", "請提供有效的操作資料。", 400)


def _text(data: dict, field: str) -> str:
    value = data.get(field, "")
    if not isinstance(value, str):
        raise AppError("NOTES_REQUEST_INVALID", "講義、活動與預覽欄位必須為文字。", 400)
    return value.strip()


def _workspace(course_id: str, teacher_id: int, status_code: int = 200, **data):
    if request.is_json or request.accept_mimetypes.best == "application/json":
        return jsonify(data), status_code
    return render_template(
        "notes.html", course_id=course_id, versions=teacher_versions(teacher_id, course_id), **data
    ), status_code


@bp.get("/courses/<course_id>")
@teacher_required
def workspace(course_id: str):
    teacher_id = _course_teacher(course_id)
    summaries = [
        {**{key: catalog[key] for key in ("import_id", "import_version", "title")},
         "question_count": len(catalog["questions"])}
        for catalog in map(version_catalog, teacher_versions(teacher_id, course_id))
    ]
    return _workspace(course_id, teacher_id, catalogs=summaries)


@bp.post("/courses/<course_id>/import/preview")
@teacher_required
def import_preview(course_id: str):
    teacher_id = _course_teacher(course_id)
    data = _form()
    source = _text(data, "source")
    spreadsheet_id, sheet_id = source_from_link(source)
    name = _text(data, "title")
    selection = data.get("sheet_id")
    if selection is not None and selection != "":
        if type(selection) not in (str, int) or not str(selection).isascii() or not str(selection).isdecimal():
            raise AppError("NOTES_SOURCE_INVALID", "請選擇有效的分頁。", 400)
        try:
            sheet_id = int(selection)
        except ValueError:
            raise AppError("NOTES_SOURCE_INVALID", "請選擇有效的分頁。", 400) from None
        if sheet_id > 2_147_483_647:
            raise AppError("NOTES_SOURCE_INVALID", "請選擇有效的分頁。", 400)
    sheets = _sheets()
    if sheet_id is None:
        tabs = sheets.tabs(spreadsheet_id)
        if not tabs:
            raise AppError("NOTES_SOURCE_INVALID", "試算表沒有可讀取的分頁。", 422)
        if len(tabs) > 1:
            return _workspace(course_id, teacher_id, tabs=tabs, source=source, requested_title=name)
        sheet_id = tabs[0]["sheetId"]
    grid = sheets.read(spreadsheet_id, sheet_id)
    layout = parse_layout(grid)
    title = name or grid.title
    preview_id = create_import_preview(teacher_id, course_id, spreadsheet_id, sheet_id, title, layout)
    return _workspace(
        course_id, teacher_id, import_review={
            "preview_id": preview_id, "title": title, "source_title": grid.title,
            "question_count": len(layout), "submission_count": len(layout),
            "item_count": sum(len(question["items"]) for question in layout),
            "questions": catalog_questions(layout),
        },
    )


@bp.post("/courses/<course_id>/import/save")
@teacher_required
def import_save(course_id: str):
    teacher_id = _course_teacher(course_id)
    import_id, import_version = save_import(teacher_id, course_id, _text(_form(), "preview_id"))
    return _workspace(course_id, teacher_id, saved_version={"import_id": import_id, "import_version": import_version})


def _writeback(course_id: str, *, confirm: bool):
    teacher_id = _course_teacher(course_id)
    data = _form()
    activity_id = _text(data, "activity_id")
    if not activity_id:
        raise AppError("NOTES_REQUEST_INVALID", "請提供活動識別碼。", 400)
    preview_id = _text(data, "preview_id") if confirm else None
    if preview_id == "":
        raise AppError("SOURCE_PREVIEW_STALE", "請先建立並確認回填預覽。", 409)
    get_snapshot = current_app.config.get("NOTES_ENDED_SNAPSHOT")
    if get_snapshot is None:
        raise AppError("NOTES_INTEGRATION_PENDING", "尚未接入活動結算。", 503)
    snapshot = get_snapshot(teacher_id, activity_id)
    if snapshot is None or snapshot.teacher_id != teacher_id or snapshot.activity_id != activity_id:
        raise AppError("ACTIVITY_NOT_FOUND", "找不到可供此教師回填的活動。", 404)
    result = process_writeback(_sheets, snapshot, course_id, preview_id)
    status_code = {"source_changed": 409, "conflict": 409, "unverified": 502}.get(result["status"], 200)
    return _workspace(course_id, teacher_id, status_code, writeback_review=result, activity_id=activity_id)


@bp.post("/courses/<course_id>/writeback/preview")
@teacher_required
def writeback_preview(course_id: str):
    return _writeback(course_id, confirm=False)


@bp.post("/courses/<course_id>/writeback/confirm")
@teacher_required
def writeback_confirm(course_id: str):
    return _writeback(course_id, confirm=True)
