"""Render a settled activity result for a teacher's CSV download."""

import csv
from io import StringIO


def _spreadsheet_text(value: str) -> str:
    if value.startswith(("\t", "\r", "\n")) or value.lstrip().startswith(
        ("=", "+", "-", "@", "＝", "＋", "－", "＠")
    ):
        # Keep this tab inside the quoted field so Excel treats the value as text.
        return "\t" + value
    return value


def render_activity_results_csv(results: dict) -> bytes:
    output = StringIO(newline="")
    writer = csv.writer(output, quoting=csv.QUOTE_ALL)
    writer.writerow(("題號", "小題識別", "組別", "答案", "受理順位", "是否勝組"))

    for question in results["questions"]:
        number = _spreadsheet_text(question["display_number"])
        if not question["teams"]:
            writer.writerow((number, "", "", "", "", ""))
        for team in question["teams"]:
            name = _spreadsheet_text(team["team_name"])
            winner = "是" if team["is_winner"] else "否"
            for answer in team["answers"]:
                writer.writerow((
                    number, _spreadsheet_text(answer["item_id"]), name,
                    _spreadsheet_text(answer["text"]), team["rank"], winner,
                ))

    return output.getvalue().encode("utf-8-sig")
