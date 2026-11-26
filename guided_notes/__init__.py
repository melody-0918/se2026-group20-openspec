"""Flask application factory for the local Guided Notes quiz project."""

from flask import Flask, jsonify
from werkzeug.exceptions import HTTPException

from .activities import bp as activities_bp
from .auth import bp as auth_bp
from .config import load_config
from .db import init_app as init_db_app
from .errors import AppError
from .notes import bp as notes_bp
from .pages import bp as pages_bp
from .quiz import bp as quiz_bp


def create_app(test_config: dict | None = None) -> Flask:
    app = Flask(__name__)
    app.config.update(load_config())
    if test_config:
        app.config.update(test_config)

    init_db_app(app)
    app.register_blueprint(pages_bp)
    app.register_blueprint(auth_bp)
    app.register_blueprint(notes_bp, url_prefix="/notes")
    app.register_blueprint(activities_bp, url_prefix="/activities")
    app.register_blueprint(quiz_bp, url_prefix="/quiz")

    @app.errorhandler(AppError)
    def handle_app_error(error: AppError):
        return jsonify({"error": {"code": error.code, "message": error.message}}), error.status_code

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
