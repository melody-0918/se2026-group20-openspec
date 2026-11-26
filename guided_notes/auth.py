"""Teacher authentication routes and command line account creation."""

import click
from flask import Blueprint, flash, redirect, render_template, request, session, url_for
from werkzeug.security import check_password_hash, generate_password_hash

from .db import get_db


bp = Blueprint("auth", __name__)
GENERIC_LOGIN_ERROR = "帳號或密碼錯誤。"


@bp.get("/login")
def login():
    return render_template("login.html")


@bp.post("/login")
def login_post():
    username = request.form.get("username", "").strip()
    password = request.form.get("password", "")
    teacher = get_db().execute(
        "SELECT id, password_hash FROM teachers WHERE username = ?", (username,)
    ).fetchone()
    if teacher is None or not check_password_hash(teacher["password_hash"], password):
        return render_template(
            "login.html", error=GENERIC_LOGIN_ERROR, error_code="LOGIN_FAILED"
        ), 401

    session.clear()
    session["teacher_id"] = teacher["id"]
    return redirect(url_for("pages.teacher_home"))


@bp.post("/logout")
def logout():
    session.clear()
    return redirect(url_for("pages.index"))


@bp.cli.command("create-teacher")
@click.argument("username")
def create_teacher_command(username: str) -> None:
    """Create a teacher; password is prompted without echo and never an argument."""
    username = username.strip()
    if not username:
        raise click.ClickException("教師帳號不可為空。")

    password = click.prompt("請輸入教師密碼", hide_input=True, confirmation_prompt=False)
    confirmation = click.prompt("請再次輸入教師密碼", hide_input=True, confirmation_prompt=False)
    if password != confirmation:
        raise click.ClickException("兩次密碼不一致，請重新執行建立教師帳號指令。")
    if not password:
        raise click.ClickException("密碼不可為空，請重新執行建立教師帳號指令。")

    connection = get_db()
    try:
        connection.execute(
            "INSERT INTO teachers (username, password_hash) VALUES (?, ?)",
            (username, generate_password_hash(password)),
        )
        connection.commit()
    except Exception as error:
        connection.rollback()
        if "UNIQUE constraint failed" in str(error):
            raise click.ClickException("此教師帳號已存在。") from error
        raise
    click.echo(f"教師帳號 {username} 建立完成。")
