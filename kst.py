"""한국 시간(KST) 기준 날짜 문자열."""
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

KST = ZoneInfo("Asia/Seoul")


def today_kst() -> str:
    return datetime.now(KST).strftime("%Y-%m-%d")


def add_days_kst(ymd: str, days: int) -> str:
    d = date.fromisoformat(ymd) + timedelta(days=days)
    return d.isoformat()


def promo_range_label_mdy(date_start: str, date_end: str) -> str:
    """예: 4/1~4/5 (같은 날이면 4/1)."""
    a = date.fromisoformat(date_start)
    b = date.fromisoformat(date_end)

    def md(d: date) -> str:
        return f"{d.month}/{d.day}"

    if a == b:
        return md(a)
    return f"{md(a)}~{md(b)}"
