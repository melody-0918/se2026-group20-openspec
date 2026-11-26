"""Environment-backed application configuration."""

import os


class ConfigurationError(RuntimeError):
    """Raised when required local environment configuration is missing."""


def load_config(environ: dict[str, str] | None = None) -> dict[str, object]:
    values = os.environ if environ is None else environ
    required = ("GUIDED_NOTES_SECRET_KEY", "GUIDED_NOTES_DATABASE")
    missing = [name for name in required if not values.get(name)]
    if missing:
        joined = ", ".join(missing)
        raise ConfigurationError(
            f"缺少必要環境變數：{joined}。請在 Windows cmd 使用 set \"{missing[0]}=範例值\" 設定後再啟動。"
        )

    demo_value = values.get("GUIDED_NOTES_DEMO_CATALOG", "0")
    return {
        "SECRET_KEY": values["GUIDED_NOTES_SECRET_KEY"],
        "DATABASE": values["GUIDED_NOTES_DATABASE"],
        "DEMO_CATALOG": demo_value == "1",
        "SESSION_COOKIE_HTTPONLY": True,
        "SESSION_COOKIE_SAMESITE": "Lax",
    }
