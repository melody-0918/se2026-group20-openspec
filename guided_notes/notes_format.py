"""Parse the Guided Notes format from Sheets grid data and merges."""

from dataclasses import dataclass
import re
from unicodedata import normalize

from .errors import AppError


_HEADERS = {"題號", "題目", "作答"}
_LABEL = re.compile(r"\(\s*([0-9]+)\s*\)")


@dataclass(frozen=True)
class Merge:
    row: int
    column: int
    end_row: int
    end_column: int

    def contains(self, row: int, column: int) -> bool:
        return self.row <= row < self.end_row and self.column <= column < self.end_column


@dataclass
class SheetGrid:
    title: str
    cells: dict[tuple[int, int], dict]
    merges: list[Merge]

    @classmethod
    def from_sheet(cls, sheet: dict):
        cells = {}
        for block in sheet.get("data", []):
            for row, values in enumerate(block.get("rowData", []), block.get("startRow", 0)):
                for column, cell in enumerate(values.get("values", []), block.get("startColumn", 0)):
                    if cell:
                        cells[row, column] = cell
        merges = [
            Merge(item.get("startRowIndex", 0), item.get("startColumnIndex", 0),
                  item["endRowIndex"], item["endColumnIndex"])
            for item in sheet.get("merges", [])
        ]
        return cls(sheet["properties"]["title"], cells, merges)

    def text(self, row: int, column: int) -> str:
        cell = self.cells.get((row, column), {})
        if "formattedValue" in cell:
            return cell["formattedValue"]
        value = cell.get("userEnteredValue") or {}
        return str(value.get("stringValue", value.get("numberValue", "")))

    def entered(self, row: int, column: int) -> dict:
        return self.cells.get((row, column), {}).get("userEnteredValue") or {}

    def span(self, row: int, column: int) -> Merge:
        for merge in self.merges:
            if merge.contains(row, column):
                return merge
        return Merge(row, column, row + 1, column + 1)


def _invalid(message: str) -> AppError:
    return AppError("NOTES_FORMAT_INVALID", message, 422)


def _header(grid: SheetGrid) -> dict[str, Merge]:
    rows = {}
    for row, column in grid.cells:
        name = grid.text(row, column).strip()
        if name in _HEADERS:
            rows.setdefault(row, []).append((name, column))
    matches = [(row, entries) for row, entries in rows.items() if {name for name, _ in entries} == _HEADERS]
    if not matches:
        raise _invalid("同一列須包含「題號」、「題目」及「作答」表頭。")
    if len(matches) != 1 or len(matches[0][1]) != len(_HEADERS):
        raise _invalid("講義有重複的必要表頭，請保留唯一一列表頭。")
    row, entries = matches[0]
    header = {name: grid.span(row, column) for name, column in entries}
    ordered = sorted(header.values(), key=lambda area: area.column)
    if any((header[name].row, header[name].column) != (row, column) for name, column in entries) or any(
        left.end_column > right.column for left, right in zip(ordered, ordered[1:])
    ):
        raise _invalid(f"第 {row + 1} 列的講義表頭欄區重疊或標題不在左上角。")
    return header


def _number(grid: SheetGrid, row: int, column: int) -> str | None:
    entered = grid.entered(row, column)
    if "numberValue" in entered:
        number = entered["numberValue"]
        if type(number) in (int, float) and number > 0 and number % 1 == 0:
            return str(int(number))
        return None
    value = entered.get("stringValue", "")
    digits = normalize("NFKC", value).strip()
    if re.fullmatch(r"[0-9]+", digits) and digits.strip("0"):
        return digits.lstrip("0")
    return None


def _item(grid: SheetGrid, answer: Merge, number: str, key: str, label: str, order: int) -> dict:
    return {
        "item_id": f"q-{number}-item-{key}",
        "label": label,
        "order": order,
        "row": answer.row,
        "column": answer.column,
        "end_row": answer.end_row,
        "end_column": answer.end_column,
        "entered": grid.entered(answer.row, answer.column),
        "display": grid.text(answer.row, answer.column),
    }


def _group_items(grid: SheetGrid, topic: Merge, area: Merge, number: str) -> list[dict]:
    items = []
    seen = set()
    for row in range(topic.row, topic.end_row):
        for column in range(area.column, area.end_column):
            span = grid.span(row, column)
            if (row, column) != (span.row, span.column):
                continue
            label = grid.text(row, column)
            if label.strip():
                break
        else:
            continue
        match = _LABEL.fullmatch(normalize("NFKC", label).strip())
        if not match or not match[1].strip("0") or span.end_row != row + 1:
            raise _invalid(f"第 {number} 題第 {row + 1} 列的小題標號位置有歧義。")
        key = match[1].lstrip("0")
        if key in seen:
            raise _invalid(f"第 {number} 題的小題標號重複。")
        seen.add(key)
        answer = Merge(row, span.end_column, row + 1, area.end_column)
        if answer.column >= answer.end_column or grid.span(row, answer.column) != answer:
            raise _invalid(f"第 {number} 題第 {row + 1} 列無法唯一辨識答案格。")
        items.append(_item(grid, answer, number, key, label, len(items) + 1))
    if len(items) < 2:
        raise _invalid(f"第 {number} 題須有至少兩個小題，或一個涵蓋全題的作答格。")
    return items


def _question_text(grid: SheetGrid, area: Merge, start_row: int, end_row: int) -> list[str]:
    text = []
    for row in range(start_row, end_row):
        for column in range(area.column, area.end_column):
            span = grid.span(row, column)
            if (row, column) == (span.row, span.column) and span.end_column <= area.end_column:
                text.append(grid.text(row, column))
    return text


def parse_layout(grid: SheetGrid) -> list[dict]:
    header = _header(grid)
    number_area, text_area, answer_area = (header[name] for name in ("題號", "題目", "作答"))
    first_topic_row = max(area.end_row for area in header.values())
    questions = []
    seen = set()
    previous_end_row = first_topic_row
    for row, column in sorted(grid.cells):
        if not number_area.column <= column < number_area.end_column or row < first_topic_row:
            continue
        topic = grid.span(row, column)
        if (topic.row, topic.column) != (row, column):
            continue
        number = _number(grid, row, column)
        if number is None:
            continue
        if row < previous_end_row or topic.end_column > number_area.end_column:
            raise _invalid(f"第 {number} 題的題號與其他題目或表頭欄區重疊。")
        previous_end_row = topic.end_row
        if number in seen:
            raise _invalid(f"題號 {number} 重複。")
        seen.add(number)
        answer = Merge(row, answer_area.column, topic.end_row, answer_area.end_column)
        is_single = grid.span(row, answer.column) == answer
        if is_single:
            items = [_item(grid, answer, number, "1", "", 1)]
        else:
            items = _group_items(grid, topic, answer_area, number)
        text_ends = [item["row"] for item in items[1:]] + [topic.end_row]
        for item, end_row in zip(items, text_ends):
            item["source_text"] = _question_text(grid, text_area, item["row"], end_row)
        questions.append({
            "question_id": f"q-{number}",
            "display_number": grid.text(row, column),
            "type": "single" if is_single else "group",
            "items": items,
            "source_row": row,
            "source_text": _question_text(grid, text_area, row, topic.end_row),
        })
    if not questions:
        raise _invalid("題號欄找不到正整數題號。")
    return questions


def catalog_questions(layout: list[dict]) -> list[dict]:
    """Project only fields in the existing Foundation contract."""
    return [
        {
            **{key: question[key] for key in ("question_id", "display_number", "type")},
            "items": [
                {key: item[key] for key in ("item_id", "label", "order")}
                for item in question["items"]
            ],
        }
        for question in layout
    ]
