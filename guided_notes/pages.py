"""Shared landing and teacher pages."""

from functools import wraps

from flask import Blueprint, redirect, render_template, session, url_for


bp = Blueprint("pages", __name__)


def teacher_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if "teacher_id" not in session:
            return redirect(url_for("auth.login"))
        return view(*args, **kwargs)

    return wrapped


@bp.get("/")
def index():
    return render_template("index.html")


@bp.get("/teacher")
@teacher_required
def teacher_home():
    return render_template("teacher.html")
