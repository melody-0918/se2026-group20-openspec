"""Google OAuth and the narrow Sheets operations used by Notes."""

import json
import os
from pathlib import Path
import re
from tempfile import NamedTemporaryFile
from urllib.parse import parse_qs, urlsplit

import click
from google.auth.exceptions import GoogleAuthError, TransportError
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from httplib2 import HttpLib2Error
from oauthlib.oauth2 import OAuth2Error

from .errors import AppError
from .notes_format import SheetGrid


_SCOPES = ("https://www.googleapis.com/auth/spreadsheets",)
_GRID_FIELDS = (
    "sheets(properties(sheetId,title),merges,"
    "data(startRow,startColumn,rowData(values(userEnteredValue,formattedValue))))"
)
_SHEET_ID = re.compile(r"[A-Za-z0-9_-]+")


def google_credentials_paths() -> tuple[str, str]:
    names = ("NOTES_GOOGLE_CLIENT_SECRETS", "NOTES_GOOGLE_TOKEN")
    client_path, token_path = (os.environ.get(name, "").strip() for name in names)
    missing = [name for name, value in zip(names, (client_path, token_path)) if not value]
    if missing:
        raise AppError(
            "GOOGLE_CREDENTIALS_REQUIRED",
            f"使用 Google Sheets 功能前，請設定環境變數 {'、'.join(missing)}，並將憑證檔放在 repo 外。",
            500,
        )
    return client_path, token_path


def _oauth_paths() -> tuple[Path, Path]:
    paths = tuple(Path(value).expanduser().resolve() for value in google_credentials_paths())
    project_root = Path(__file__).resolve().parents[1]
    if paths[0] == paths[1] or any(path.is_relative_to(project_root) for path in paths):
        raise AppError("GOOGLE_CREDENTIALS_REQUIRED", "請在 repo 外分別設定 OAuth client 與 token 路徑。", 500)
    return paths


def _save_token(path: Path, credentials: Credentials) -> None:
    temporary = None
    try:
        with NamedTemporaryFile(mode="w", encoding="utf-8", dir=path.parent, delete=False) as stream:
            temporary = Path(stream.name)
            stream.write(credentials.to_json())
        temporary.replace(path)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


@click.command("authorize-sheets")
def authorize_sheets() -> None:
    """Open the Desktop OAuth flow and save the authorized-user token."""
    try:
        client_path, token_path = _oauth_paths()
        flow = InstalledAppFlow.from_client_secrets_file(client_path, scopes=_SCOPES)
        credentials = flow.run_local_server(host="127.0.0.1", port=0, timeout_seconds=180)
        if not credentials.valid or not credentials.has_scopes(_SCOPES):
            raise _auth_required()
        _save_token(token_path, credentials)
    except AppError as error:
        raise click.ClickException(error.message) from None
    except (OSError, ValueError, AttributeError, GoogleAuthError, OAuth2Error):
        raise click.ClickException("Google 授權未完成。請檢查 Desktop OAuth 設定、測試帳號及檔案路徑，再重試。") from None
    click.echo("Google Sheets 授權完成，token 已儲存至設定的外部檔案。")


def _auth_required() -> AppError:
    return AppError("SHEETS_AUTH_REQUIRED", "Google Sheets 授權無效，請重新執行 notes authorize-sheets。", 401)


def _request_failed(writing: bool) -> AppError:
    if writing:
        return AppError("SHEETS_WRITE_UNVERIFIED", "無法確認 Google Sheets 寫入結果，請回讀後再試。", 502)
    return AppError("SHEETS_READ_FAILED", "目前無法讀取 Google Sheets，請稍後重試。", 502)


def _credentials() -> Credentials:
    try:
        _, token_path = _oauth_paths()
        token = json.loads(token_path.read_text(encoding="utf-8"))
        token_scopes = token.get("scopes")
        if not isinstance(token_scopes, list) or _SCOPES[0] not in token_scopes:
            raise _auth_required()
        credentials = Credentials.from_authorized_user_info(token)
        if not credentials.valid:
            credentials.refresh(Request())
            _save_token(token_path, credentials)
    except TransportError:
        raise _request_failed(False) from None
    except (OSError, ValueError, AttributeError, TypeError, GoogleAuthError):
        raise _auth_required() from None
    if not credentials.valid or not credentials.has_scopes(_SCOPES):
        raise _auth_required()
    return credentials


def source_from_link(link: str) -> tuple[str, int | None]:
    """Resolve a Sheets link or ID without requesting the supplied URL."""
    value = link.strip()
    if _SHEET_ID.fullmatch(value):
        return value, None
    try:
        url = urlsplit(value)
        match = re.fullmatch(r"/spreadsheets/d/([A-Za-z0-9_-]+)(?:/.*)?", url.path)
        if url.scheme == "https" and url.netloc == "docs.google.com" and match:
            parameters = parse_qs(url.query) | parse_qs(url.fragment)
            gid = parameters.get("gid", [None])[0]
            if gid is None:
                return match[1], None
            if re.fullmatch(r"[0-9]{1,10}", gid) and int(gid) <= 2_147_483_647:
                return match[1], int(gid)
    except ValueError:
        pass
    raise AppError("NOTES_SOURCE_INVALID", "請輸入有效的 Google Sheets 連結或試算表 ID。", 400)


class GoogleSheets:
    def __init__(self) -> None:
        self.api = build("sheets", "v4", credentials=_credentials(), cache_discovery=False).spreadsheets()

    def _execute(self, request, *, writing: bool = False) -> dict:
        try:
            return request.execute(num_retries=0)
        except HttpError as error:
            status = error.resp.status
            if status == 401:
                raise _auth_required() from None
            if status in (403, 404):
                raise AppError("SHEETS_ACCESS_DENIED", "請檢查試算表是否存在及 Google 帳號的讀寫權限。", 403) from None
            raise _request_failed(writing) from None
        except (OSError, HttpLib2Error, TransportError):
            raise _request_failed(writing) from None
        except GoogleAuthError:
            raise _auth_required() from None

    def tabs(self, spreadsheet_id: str) -> list[dict]:
        result = self._execute(self.api.get(spreadsheetId=spreadsheet_id, fields="sheets(properties(sheetId,title,sheetType))"))
        return [sheet["properties"] for sheet in result.get("sheets", []) if sheet["properties"].get("sheetType", "GRID") == "GRID"]

    def read(self, spreadsheet_id: str, sheet_id: int) -> SheetGrid:
        request = self.api.getByDataFilter(
            spreadsheetId=spreadsheet_id,
            body={"dataFilters": [{"gridRange": {"sheetId": sheet_id}}]},
            fields=_GRID_FIELDS,
        )
        for sheet in self._execute(request).get("sheets", []):
            if sheet["properties"].get("sheetId") == sheet_id:
                return SheetGrid.from_sheet(sheet)
        raise AppError("NOTES_SOURCE_INVALID", "找不到指定分頁，請重新選擇來源。", 404)

    def write(self, spreadsheet_id: str, sheet_id: int, targets: list[dict]) -> None:
        # Use sheet IDs and a field mask so names, formatting and merges are left alone.
        requests = [
            {"updateCells": {
                "start": {"sheetId": sheet_id, "rowIndex": target["row"], "columnIndex": target["column"]},
                "rows": [{"values": [{"userEnteredValue": {"stringValue": target["answer"]}}]}],
                "fields": "userEnteredValue",
            }}
            for target in targets
        ]
        self._execute(self.api.batchUpdate(spreadsheetId=spreadsheet_id, body={"requests": requests}), writing=True)
