"""Parse the Guided Notes format from Sheets grid data and merges."""

from dataclasses import dataclass
import re
from unicodedata import normalize

from .errors import AppError


_HEADERS = {"題號", "題目", "作答"}
_LABEL = re.compile(r"\(([0-9]+)\)")


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
    return {name: grid.span(row, column) for name, column in entries}


def _number(grid: SheetGrid, row: int, column: int) -> str | None:
    shown = normalize("NFKC", grid.text(row, column)).strip()
    if re.fullmatch(r"[0-9]+", shown) and shown.strip("0"):
        return shown.lstrip("0")
    number = grid.entered(row, column).get("numberValue")
    if isinstance(number, (int, float)) and number > 0 and number % 1 == 0:
        return str(int(number))
    return None


def _answer(grid: SheetGrid, row: int, start: int, end: int, number: str) -> Merge:
    ranges = {grid.span(row, column) for column in range(start, end)}
    if len(ranges) != 1:
        raise _invalid(f"第 {number} 題無法唯一辨識答案格。")
    answer = ranges.pop()
    if answer.row != row or answer.end_row != row + 1 or answer.column < start or answer.end_column > end:
        raise _invalid(f"第 {number} 題的答案格跨出作答位置。")
    return answer


def _item(grid: SheetGrid, answer: Merge, number: str, key: str, label: str, order: int) -> dict:
    return {
        "item_id": f"q-{number}-item-{key}",
        "label": label,
        "order": order,
        "row": answer.row,
        "column": answer.column,
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
            label = grid.text(row, column).strip()
            match = _LABEL.fullmatch(normalize("NFKC", label))
            if match and match[1].strip("0"):
                break
            if label:
                raise _invalid(f"第 {number} 題第 {row + 1} 列的小題標號位置有歧義。")
        else:
            raise _invalid(f"第 {number} 題第 {row + 1} 列缺少小題標號。")
        key = match[1].lstrip("0")
        if key in seen:
            raise _invalid(f"第 {number} 題的小題標號重複。")
        seen.add(key)
        answer = _answer(grid, row, span.end_column, area.end_column, number)
        items.append(_item(grid, answer, number, key, label, len(items) + 1))
    return items


def parse_layout(grid: SheetGrid) -> list[dict]:
    header = _header(grid)
    number_area, text_area, answer_area = (header[name] for name in ("題號", "題目", "作答"))
    first_topic_row = max(area.end_row for area in header.values())
    questions = []
    seen = set()
    for row, column in sorted(grid.cells):
        if column != number_area.column or row < first_topic_row:
            continue
        topic = grid.span(row, column)
        if (topic.row, topic.column) != (row, column):
            continue
        number = _number(grid, row, column)
        if number is None:
            continue
        if number in seen:
            raise _invalid(f"題號 {number} 重複。")
        seen.add(number)
        is_group = topic.end_row > row + 1
        if is_group:
            items = _group_items(grid, topic, answer_area, number)
        else:
            answer = _answer(grid, row, answer_area.column, answer_area.end_column, number)
            items = [_item(grid, answer, number, "1", "", 1)]
        for item in items:
            item["source_text"] = [
                grid.text(item["row"], text_column) for text_column in range(text_area.column, text_area.end_column)
            ]
        questions.append({
            "question_id": f"q-{number}",
            "display_number": grid.text(row, column),
            "type": "group" if is_group else "single",
            "items": items,
            "source_row": row,
            "source_text": [
                grid.text(text_row, text_column)
                for text_row in range(row, topic.end_row)
                for text_column in range(text_area.column, text_area.end_column)
            ],
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
