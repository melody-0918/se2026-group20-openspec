"""SQLite connection management and schema initialization."""

import sqlite3
from pathlib import Path

import click
from flask import current_app, g


SCHEMA = """
CREATE TABLE IF NOT EXISTS teachers (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    username TEXT NOT NULL UNIQUE,
    password_hash TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS notes_versions (
    import_id TEXT NOT NULL,
    import_version INTEGER NOT NULL,
    teacher_id INTEGER NOT NULL REFERENCES teachers(id),
    course_id TEXT NOT NULL,
    spreadsheet_id TEXT NOT NULL,
    sheet_id INTEGER NOT NULL,
    title TEXT NOT NULL,
    layout TEXT NOT NULL,
    PRIMARY KEY (import_id, import_version)
);
CREATE INDEX IF NOT EXISTS notes_versions_teacher ON notes_versions (teacher_id, course_id, spreadsheet_id, sheet_id);

CREATE TABLE IF NOT EXISTS notes_import_previews (
    id TEXT PRIMARY KEY,
    teacher_id INTEGER NOT NULL REFERENCES teachers(id),
    course_id TEXT NOT NULL,
    spreadsheet_id TEXT NOT NULL,
    sheet_id INTEGER NOT NULL,
    title TEXT NOT NULL,
    layout TEXT NOT NULL,
    import_id TEXT,
    import_version INTEGER,
    FOREIGN KEY (import_id, import_version) REFERENCES notes_versions (import_id, import_version)
);

CREATE TABLE IF NOT EXISTS notes_writeback_plans (
    teacher_id INTEGER NOT NULL REFERENCES teachers(id),
    activity_id TEXT NOT NULL,
    id TEXT NOT NULL,
    data TEXT NOT NULL,
    attempted INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (teacher_id, activity_id)
);
"""


def connect_db() -> sqlite3.Connection:
    path = str(current_app.config["DATABASE"])
    if path != ":memory:":
        Path(path).expanduser().resolve().parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(path)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    return connection


def get_db() -> sqlite3.Connection:
    if "db" not in g:
        g.db = connect_db()
    return g.db


def close_db(_error: BaseException | None = None) -> None:
    connection = g.pop("db", None)
    if connection is not None:
        connection.close()


def init_db() -> None:
    connection = connect_db()
    try:
        connection.executescript(SCHEMA)
        connection.commit()
    finally:
        connection.close()


def init_app(app) -> None:
    app.teardown_appcontext(close_db)

    @app.cli.command("init-db")
    def init_db_command() -> None:
        """Initialize the configured SQLite database."""
        init_db()
        click.echo("資料庫初始化完成。")
