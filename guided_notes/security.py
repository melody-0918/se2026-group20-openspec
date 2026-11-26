"""Session-based CSRF protection for state-changing requests."""

import hmac
import secrets

from flask import abort, request, session


SAFE_METHODS = {"GET", "HEAD", "OPTIONS", "TRACE"}


def get_csrf_token() -> str:
    token = session.get("csrf_token")
    if token is None:
        token = secrets.token_urlsafe(32)
        session["csrf_token"] = token
    return token


def validate_request_token() -> None:
    if request.method in SAFE_METHODS:
        return
    expected = session.get("csrf_token")
    provided = request.form.get("csrf_token") or request.headers.get("X-CSRF-Token")
    if not expected or not provided or not hmac.compare_digest(expected, provided):
        abort(400, description="CSRF token 缺少或無效。")
