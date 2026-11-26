"""Notes Blueprint and teacher-scoped catalog interface."""

from flask import Blueprint, current_app

from .db import get_db
from .errors import AppError


bp = Blueprint("notes", __name__)

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
    """Storage seam for the later notes import change; no real imports exist yet."""
    return []


def _require_teacher(teacher_id: int) -> None:
    if teacher_id is None:
        raise AppError("TEACHER_REQUIRED", "需要有效的教師身分才能讀取題目清單。", 401)
    teacher = get_db().execute("SELECT 1 FROM teachers WHERE id = ?", (teacher_id,)).fetchone()
    if teacher is None:
        raise AppError("TEACHER_REQUIRED", "需要有效的教師身分才能讀取題目清單。", 401)


def google_credentials_paths() -> tuple[str, str]:
    """Validate Google OAuth paths only when a notes Google operation is invoked."""
    import os

    client_path = os.environ.get("NOTES_GOOGLE_CLIENT_SECRETS", "").strip()
    token_path = os.environ.get("NOTES_GOOGLE_TOKEN", "").strip()
    missing = []
    if not client_path:
        missing.append("NOTES_GOOGLE_CLIENT_SECRETS")
    if not token_path:
        missing.append("NOTES_GOOGLE_TOKEN")
    if missing:
        names = "、".join(missing)
        raise AppError(
            "GOOGLE_CREDENTIALS_REQUIRED",
            f"使用 Google Sheets 功能前，請設定環境變數 {names}，並將憑證檔放在 repo 外。",
            500,
        )
    return client_path, token_path


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
