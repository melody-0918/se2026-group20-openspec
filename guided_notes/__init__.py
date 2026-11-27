"""Flask application factory for the local Guided Notes quiz project."""

from flask import Flask, jsonify, render_template, request, session, url_for
from werkzeug.exceptions import HTTPException

from .activities import bp as activities_bp, notes_course_access
from .auth import bp as auth_bp
from .config import load_config
from .db import init_app as init_db_app
from .errors import AppError
from .notes import bp as notes_bp
from .pages import bp as pages_bp
from .quiz import bp as quiz_bp, get_ended_snapshot


def create_app(test_config: dict | None = None) -> Flask:
    app = Flask(__name__)
    app.config.update(load_config())
    if test_config:
        app.config.update(test_config)
    app.config.setdefault("NOTES_COURSE_ACCESS", notes_course_access)
    # Keep tests that explicitly exercise Notes' unconnected fallback isolated;
    # production apps always expose the quiz adapter.
    if not app.config.get("TESTING"):
        app.config.setdefault("NOTES_ENDED_SNAPSHOT", get_ended_snapshot)

    init_db_app(app)
    app.register_blueprint(pages_bp)
    app.register_blueprint(auth_bp)
    app.register_blueprint(notes_bp, url_prefix="/notes")
    app.register_blueprint(activities_bp, url_prefix="/activities")
    app.register_blueprint(quiz_bp, url_prefix="/quiz")

    @app.errorhandler(AppError)
    def handle_app_error(error: AppError):
        is_api = request.path.startswith("/api/") or "/api/" in request.path
        is_activities_page = (request.endpoint or "").startswith("activities.") and not is_api
        is_notes_page = (request.endpoint or "").startswith("notes.") and not is_api
        is_notes_json_request = is_notes_page and (
            request.is_json or request.accept_mimetypes.best == "application/json"
        )
        if is_api or is_notes_json_request or not (is_activities_page or is_notes_page):
            return jsonify({"error": {"code": error.code, "message": error.message}}), error.status_code

        endpoint = request.endpoint or ""
        view_args = request.view_args or {}
        if is_notes_page:
            course_id = view_args.get("course_id")
            if error.code == "COURSE_FORBIDDEN":
                return_url = url_for("activities.teacher_courses")
                return_label = "返回課程列表"
            else:
                course_access = app.config.get("NOTES_COURSE_ACCESS")
                teacher_id = session.get("teacher_id")
                if course_id and teacher_id is not None and callable(course_access) and course_access(teacher_id, course_id):
                    return_url = url_for("notes.workspace", course_id=course_id)
                    return_label = "返回課程講義管理頁"
                else:
                    return_url = url_for("activities.teacher_courses")
                    return_label = "返回課程列表"
        elif endpoint in {"activities.student_join", "activities.student_join_page", "activities.student_page"}:
            return_url = url_for("activities.student_join_page")
            return_label = "返回學生加入頁"
        elif endpoint in {"activities.teacher_courses", "activities.teacher_create_course"}:
            return_url = url_for("activities.teacher_courses")
            return_label = "返回課程列表"
        elif "course_id" in view_args:
            return_url = url_for("activities.teacher_course", course_id=view_args["course_id"])
            return_label = "返回課程頁"
        elif "classroom_id" in view_args:
            return_url = url_for("activities.teacher_classroom", classroom_id=view_args["classroom_id"])
            return_label = "返回課堂控制頁"
        else:
            return_url = url_for("pages.index")
            return_label = "返回首頁"

        return render_template(
            "error.html", error_code=error.code, error_message=error.message,
            return_url=return_url, return_label=return_label,
        ), error.status_code

    @app.errorhandler(HTTPException)
    def handle_http_error(error: HTTPException):
        return jsonify({"error": {"code": f"HTTP_{error.code}", "message": error.description}}), error.code

    @app.errorhandler(Exception)
    def handle_unexpected_error(error: Exception):
        app.logger.exception("Unhandled application error", exc_info=error)
        return jsonify({"error": {"code": "INTERNAL_ERROR", "message": "系統發生錯誤，請稍後再試。"}}), 500

    @app.before_request
    def validate_csrf():
        from .security import validate_request_token

        validate_request_token()

    @app.context_processor
    def inject_csrf_token():
        from .security import get_csrf_token

        return {"csrf_token": get_csrf_token}

    return app
