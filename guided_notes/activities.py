"""Activities Blueprint extension point."""

from flask import Blueprint


bp = Blueprint("activities", __name__)


@bp.get("/")
def placeholder():
    return "Activities 模組掛載點尚未開放活動功能。"
