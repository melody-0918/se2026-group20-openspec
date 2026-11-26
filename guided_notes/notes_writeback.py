"""Plan, confirm and verify writes against a frozen Notes catalog."""

from dataclasses import dataclass
import json
from threading import Lock

from .errors import AppError
from .notes_format import parse_layout
from .notes_store import find_version, load_writeback, mark_writeback_attempted, save_writeback, update_writeback_plan


_lock = Lock()


@dataclass(frozen=True)
class Answer:
    item_id: str
    text: str


@dataclass(frozen=True)
class QuestionResult:
    question_id: str
    winner_id: str | None
    answers: tuple[Answer, ...] = ()


@dataclass(frozen=True)
class EndedSnapshot:
    """Internal input for Notes; a future B adapter translates its own result to this."""

    activity_id: str
    teacher_id: int
    import_id: str
    import_version: str
    closed: bool
    settled: bool
    questions: tuple[QuestionResult, ...]


def _result_mismatch() -> AppError:
    return AppError("RESULT_CATALOG_MISMATCH", "結算結果與活動固定的講義版本、題目或填空不符。", 409)


def _result_targets(layout: list[dict], snapshot: EndedSnapshot) -> tuple[list[dict], int]:
    results = {result.question_id: result for result in snapshot.questions}
    if len(results) != len(snapshot.questions) or set(results) != {q["question_id"] for q in layout}:
        raise _result_mismatch()
    targets = []
    skipped = 0
    for question in layout:
        result = results[question["question_id"]]
        if result.winner_id is None:
            if result.answers:
                raise _result_mismatch()
            skipped += 1
            continue
        answers = {answer.item_id: answer.text for answer in result.answers}
        if len(answers) != len(result.answers) or set(answers) != {item["item_id"] for item in question["items"]}:
            raise _result_mismatch()
        for item in question["items"]:
            answer = answers[item["item_id"]]
            if not isinstance(answer, str):
                raise _result_mismatch()
            targets.append({
                "question_id": question["question_id"],
                "item_id": item["item_id"],
                "winner_id": result.winner_id,
                "answer": answer,
            })
    return targets, skipped


def _signature(layout: list[dict]) -> dict:
    return {
        question["question_id"]: (question["type"], {item["item_id"] for item in question["items"]})
        for question in layout
    }


def _current_plan(sheets, source, saved_layout: list[dict], targets: list[dict]) -> dict:
    try:
        grid = sheets.read(source["spreadsheet_id"], source["sheet_id"])
        layout = parse_layout(grid)
    except AppError as error:
        if error.code not in {"NOTES_FORMAT_INVALID", "NOTES_SOURCE_INVALID"}:
            raise
        raise AppError("SOURCE_REIMPORT_REQUIRED", "無法辨識原講義，請重新匯入並核對活動結果。", 409) from None
    if _signature(saved_layout) != _signature(layout):
        raise AppError("SOURCE_REIMPORT_REQUIRED", "原講義題目或填空集合已變更，請重新匯入並核對活動結果。", 409)

    lookup = {item["item_id"]: (question, item) for question in layout for item in question["items"]}
    entries = []
    for target in targets:
        question, item = lookup[target["item_id"]]
        entries.append({
            **target,
            **{key: item[key] for key in ("label", "row", "column")},
            "display_number": question["display_number"],
            "original": item["entered"],
            "original_display": item["display"],
        })
    return {
        "title": grid.title,
        "structure": [
            {**question, "items": [
                {key: value for key, value in item.items() if key not in ("entered", "display")}
                for item in question["items"]
            ]}
            for question in layout
        ],
        "entries": entries,
    }


def _matches(raw: dict, answer: str) -> bool:
    return raw == {"stringValue": answer} or (answer == "" and not raw)


def _with_originals(current: dict, saved: dict) -> dict:
    originals = {entry["item_id"]: entry for entry in saved["entries"]}
    for entry in current["entries"]:
        previous = originals[entry["item_id"]]
        entry.update(original=previous["original"], original_display=previous["original_display"])
    current["verified"] = saved.get("verified", [])
    return current


def _review(plan: dict, preview_id: str, status: str, results: dict | None = None,
            issue: AppError | None = None) -> dict:
    return {
        "status": status,
        "preview_id": preview_id,
        "title": plan["title"],
        "skipped_count": plan["skipped_count"],
        "issue": {"code": issue.code, "message": issue.message} if issue else None,
        "targets": [
            {
                **{key: entry[key] for key in ("question_id", "item_id", "display_number", "label", "answer",
                                               "original_display", "row", "column")},
                "status": (results or {}).get(entry["item_id"], "pending"),
            }
            for entry in plan["entries"]
        ],
    }


def process_writeback(sheets_factory, snapshot: EndedSnapshot, course_id: str, preview_id: str | None = None) -> dict:
    if not snapshot.closed or not snapshot.settled:
        raise AppError("RESULT_NOT_READY", "活動尚未結束並完成結算。", 409)
    source = find_version(snapshot.teacher_id, snapshot.import_id, snapshot.import_version)
    if source is None or source["course_id"] != course_id:
        raise _result_mismatch()
    saved_layout = json.loads(source["layout"])
    targets, skipped = _result_targets(saved_layout, snapshot)
    binding = {
        "import_id": snapshot.import_id, "import_version": snapshot.import_version,
        "targets": targets, "skipped_count": skipped,
    }
    with _lock:
        return _process(sheets_factory, snapshot, source, saved_layout, binding, preview_id)


def _process(sheets_factory, snapshot, source, saved_layout, binding, preview_id):
    teacher_id, activity_id = snapshot.teacher_id, snapshot.activity_id
    previous = load_writeback(teacher_id, activity_id)
    if preview_id is not None and (previous is None or previous["id"] != preview_id):
        raise AppError("SOURCE_PREVIEW_STALE", "回填預覽已失效，請先取得目前的預覽。", 409)
    saved = json.loads(previous["data"]) if previous else None
    if saved and any(saved[key] != value for key, value in binding.items()):
        raise _result_mismatch()

    sheets = sheets_factory()
    current = {**_current_plan(sheets, source, saved_layout, binding["targets"]), **binding}
    attempted = bool(previous and previous["attempted"])
    changed = saved is not None and (
        saved["structure"] != current["structure"] or saved["title"] != current["title"]
        or (not attempted and [entry["original"] for entry in saved["entries"]]
            != [entry["original"] for entry in current["entries"]])
    )
    if saved is None or changed:
        plan = _with_originals(current, saved) if attempted else current
        new_id = save_writeback(teacher_id, activity_id, plan, attempted)
        return _review(plan, new_id, "source_changed" if changed else "preview")
    if preview_id is None:
        results = _readback(saved, current, writing_failed=True) if attempted else None
        if results is not None:
            _remember_verified(teacher_id, activity_id, saved, results)
        return _review(saved, previous["id"], "preview", results)

    writes = []
    statuses = {}
    verified = set(saved.get("verified", []))
    for original, entry in zip(saved["entries"], current["entries"]):
        key = entry["item_id"]
        if _matches(entry["original"], entry["answer"]):
            statuses[key] = "verified"
        elif key in verified or entry["original"] != original["original"]:
            statuses[key] = "conflict"
        else:
            writes.append(entry)
    if "conflict" in statuses.values():
        _remember_verified(teacher_id, activity_id, saved, statuses)
        return _review(saved, preview_id, "conflict", statuses)

    mark_writeback_attempted(teacher_id, activity_id)
    _remember_verified(teacher_id, activity_id, saved, statuses)
    if not writes:
        return _review(saved, preview_id, "verified", statuses)
    writing_failed = False
    try:
        sheets.write(source["spreadsheet_id"], source["sheet_id"], writes)
    except AppError as error:
        if error.code != "SHEETS_WRITE_UNVERIFIED":
            raise
        writing_failed = True

    try:
        readback = _current_plan(sheets, source, saved_layout, binding["targets"])
    except AppError as error:
        return _review(
            saved, preview_id, "unverified", {entry["item_id"]: "unverified" for entry in saved["entries"]}, error
        )
    if readback["structure"] != saved["structure"] or readback["title"] != saved["title"]:
        return _review(saved, preview_id, "unverified", {entry["item_id"]: "unverified" for entry in saved["entries"]})
    statuses = _readback(saved, readback, writing_failed)
    _remember_verified(teacher_id, activity_id, saved, statuses)
    status = "verified"
    if "conflict" in statuses.values():
        status = "conflict"
    elif "unverified" in statuses.values():
        status = "unverified"
    return _review(saved, preview_id, status, statuses)


def _readback(saved: dict, current: dict, writing_failed: bool) -> dict:
    statuses = {}
    verified = set(saved.get("verified", []))
    for original, entry in zip(saved["entries"], current["entries"]):
        if _matches(entry["original"], entry["answer"]):
            status = "verified"
        elif writing_failed and entry["item_id"] not in verified and entry["original"] == original["original"]:
            status = "unverified"
        else:
            status = "conflict"
        statuses[entry["item_id"]] = status
    return statuses


def _remember_verified(teacher_id: int, activity_id: str, plan: dict, statuses: dict) -> None:
    previous = set(plan.get("verified", []))
    verified = previous | {item_id for item_id, status in statuses.items() if status == "verified"}
    if verified != previous:
        plan["verified"] = sorted(verified)
        update_writeback_plan(teacher_id, activity_id, plan)
