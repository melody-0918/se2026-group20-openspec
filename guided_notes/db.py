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

CREATE TABLE IF NOT EXISTS courses (
    id TEXT PRIMARY KEY,
    teacher_id INTEGER NOT NULL REFERENCES teachers(id),
    name TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_courses_teacher ON courses(teacher_id, created_at);

CREATE TABLE IF NOT EXISTS course_catalogs (
    course_id TEXT NOT NULL REFERENCES courses(id),
    import_id TEXT NOT NULL,
    import_version TEXT NOT NULL,
    title TEXT NOT NULL,
    question_count INTEGER NOT NULL CHECK (question_count >= 0),
    PRIMARY KEY (course_id, import_id, import_version)
);

CREATE TABLE IF NOT EXISTS classrooms (
    id TEXT PRIMARY KEY,
    course_id TEXT NOT NULL REFERENCES courses(id),
    name TEXT NOT NULL,
    join_code TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'open' CHECK (status IN ('open', 'closed')),
    state_version INTEGER NOT NULL DEFAULT 1 CHECK (state_version >= 1),
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    closed_at TEXT
);
CREATE INDEX IF NOT EXISTS idx_classrooms_course ON classrooms(course_id, created_at);
CREATE UNIQUE INDEX IF NOT EXISTS idx_open_classroom_join_code
    ON classrooms(join_code) WHERE status = 'open';

CREATE TABLE IF NOT EXISTS teams (
    id TEXT PRIMARY KEY,
    classroom_id TEXT NOT NULL REFERENCES classrooms(id),
    name TEXT NOT NULL,
    name_key TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (classroom_id, name_key)
);

CREATE TABLE IF NOT EXISTS student_proofs (
    id TEXT PRIMARY KEY,
    classroom_id TEXT NOT NULL REFERENCES classrooms(id),
    team_id TEXT NOT NULL REFERENCES teams(id),
    token_hash TEXT NOT NULL UNIQUE,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    revoked_at TEXT
);

CREATE TABLE IF NOT EXISTS activities (
    id TEXT PRIMARY KEY,
    classroom_id TEXT NOT NULL REFERENCES classrooms(id),
    import_id TEXT NOT NULL,
    import_version TEXT NOT NULL,
    title TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'preparing' CHECK (status IN ('preparing', 'active', 'ended')),
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    started_at TEXT,
    ended_at TEXT,
    ended_seq INTEGER
);
CREATE INDEX IF NOT EXISTS idx_activities_classroom ON activities(classroom_id, created_at);
CREATE UNIQUE INDEX IF NOT EXISTS idx_one_active_activity_per_classroom
    ON activities(classroom_id) WHERE status = 'active';

CREATE TABLE IF NOT EXISTS activity_questions (
    activity_id TEXT NOT NULL REFERENCES activities(id),
    question_id TEXT NOT NULL,
    display_number TEXT NOT NULL,
    question_order INTEGER NOT NULL,
    PRIMARY KEY (activity_id, question_id),
    UNIQUE (activity_id, question_order)
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

SCHEMA_VERSION = 1


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
        _ensure_activity_end_sequence(connection)
        connection.execute("CREATE TABLE IF NOT EXISTS schema_meta (version INTEGER NOT NULL)")
        connection.execute(
            "INSERT INTO schema_meta(version) SELECT ? WHERE NOT EXISTS (SELECT 1 FROM schema_meta)",
            (SCHEMA_VERSION,),
        )
        connection.commit()
    finally:
        connection.close()


def _ensure_activity_end_sequence(connection: sqlite3.Connection) -> None:
    """Add and backfill the activities-only end ordering column on old databases."""
    columns = {row["name"] for row in connection.execute("PRAGMA table_info(activities)")}
    if "ended_seq" not in columns:
        connection.execute("ALTER TABLE activities ADD COLUMN ended_seq INTEGER")

    classroom_ids = [row[0] for row in connection.execute("SELECT id FROM classrooms")]
    for classroom_id in classroom_ids:
        current_version = connection.execute(
            "SELECT state_version FROM classrooms WHERE id = ?", (classroom_id,)
        ).fetchone()[0]
        current_max = connection.execute(
            "SELECT COALESCE(MAX(ended_seq), 0) FROM activities WHERE classroom_id = ?", (classroom_id,)
        ).fetchone()[0]
        missing = connection.execute(
            """SELECT id FROM activities
               WHERE classroom_id = ? AND status = 'ended' AND ended_seq IS NULL
               ORDER BY ended_at, rowid""",
            (classroom_id,),
        ).fetchall()
        for row in missing:
            current_max += 1
            connection.execute("UPDATE activities SET ended_seq = ? WHERE id = ?", (current_max, row["id"]))
        if current_max > current_version:
            connection.execute(
                "UPDATE classrooms SET state_version = ? WHERE id = ?", (current_max, classroom_id)
            )
    connection.execute(
        "CREATE INDEX IF NOT EXISTS idx_activities_ended_sequence ON activities(classroom_id, ended_seq)"
    )


def init_app(app) -> None:
    app.teardown_appcontext(close_db)

    @app.cli.command("init-db")
    def init_db_command() -> None:
        """Initialize the configured SQLite database."""
        init_db()
        click.echo("資料庫初始化完成。")
