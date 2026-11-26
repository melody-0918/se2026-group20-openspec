"""Quiz Blueprint extension point."""

from flask import Blueprint


bp = Blueprint("quiz", __name__)


@bp.get("/")
def placeholder():
    return "Quiz 模組掛載點尚未開放作答功能。"
