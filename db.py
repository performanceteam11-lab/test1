"""SQLite DB 초기화 및 CRUD."""
from __future__ import annotations

import os
import random
import sqlite3
import uuid
from datetime import datetime
from typing import Any

from kst import today_kst

DB_DIR = os.path.join(os.path.dirname(__file__), "data")
DB_PATH = os.path.join(DB_DIR, "team.db")

MEMBERS = [
    ("seodakyeong@team.local", "서다경"),
    ("noeunji@team.local", "노은지"),
    ("gohaeil@team.local", "고해일"),
    ("josebin@team.local", "조세빈"),
    ("gochangwoong@team.local", "고창웅"),
    ("haminsoo@team.local", "하민수"),
    ("yujimin@team.local", "유지민"),
]

DEFAULT_CATEGORIES = ["광고주 요청", "셋팅", "소재기획", "기타 업무"]
LEGACY_LABELS = {
    "AD_REQUEST": "광고주 요청",
    "SETTING": "셋팅",
    "MATERIAL_PLAN": "소재기획",
    "OTHER": "기타 업무",
}

# 캘린더 프로모션 등록 시마다 랜덤 선택 (가독성 있는 색)
PROMO_COLOR_PALETTE = [
    "#C2185B",
    "#7B1FA2",
    "#512DA8",
    "#303F9F",
    "#1976D2",
    "#0288D1",
    "#0097A7",
    "#00796B",
    "#388E3C",
    "#689F38",
    "#F9A825",
    "#F57C00",
    "#E64A19",
    "#5D4037",
    "#455A64",
    "#D32F2F",
]

# 오늘 메모 카드 배경 (가독성 위해 연한 톤)
MEMO_CARD_COLORS = [
    "#E3F2FD",
    "#FCE4EC",
    "#E8F5E9",
    "#FFF3E0",
    "#F3E5F5",
    "#E0F7FA",
    "#FFF9C4",
    "#FFEBEE",
    "#E8EAF6",
    "#F1F8E9",
    "#EDE7F6",
    "#E1F5FE",
]


def _conn() -> sqlite3.Connection:
    os.makedirs(DB_DIR, exist_ok=True)
    c = sqlite3.connect(DB_PATH, check_same_thread=False)
    c.row_factory = sqlite3.Row
    return c


def init_db() -> None:
    c = _conn()
    try:
        c.executescript(
            """
            CREATE TABLE IF NOT EXISTS users (
                id TEXT PRIMARY KEY,
                email TEXT UNIQUE NOT NULL,
                name TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS team_categories (
                id TEXT PRIMARY KEY,
                label TEXT UNIQUE NOT NULL,
                sort_order INTEGER DEFAULT 0
            );
            CREATE TABLE IF NOT EXISTS tasks (
                id TEXT PRIMARY KEY,
                user_id TEXT NOT NULL,
                scheduled_for TEXT NOT NULL,
                category TEXT NOT NULL,
                title TEXT NOT NULL,
                detail TEXT DEFAULT '',
                completed INTEGER DEFAULT 0,
                completed_at TEXT,
                completed_type TEXT,
                rolled_from_id TEXT,
                created_at TEXT,
                updated_at TEXT,
                FOREIGN KEY (user_id) REFERENCES users(id)
            );
            CREATE INDEX IF NOT EXISTS idx_tasks_user_date ON tasks(user_id, scheduled_for);
            CREATE TABLE IF NOT EXISTS calendar_promotions (
                id TEXT PRIMARY KEY,
                title TEXT NOT NULL,
                date_start TEXT NOT NULL,
                date_end TEXT NOT NULL,
                detail TEXT DEFAULT '',
                color_hex TEXT NOT NULL,
                created_at TEXT,
                source TEXT DEFAULT 'manual',
                sheet_row INTEGER
            );
            CREATE TABLE IF NOT EXISTS daily_memos (
                id TEXT PRIMARY KEY,
                memo_date TEXT NOT NULL,
                body TEXT NOT NULL,
                color_hex TEXT NOT NULL,
                created_at TEXT
            );
            CREATE INDEX IF NOT EXISTS idx_daily_memos_date ON daily_memos(memo_date);
            """
        )
        c.commit()
    finally:
        c.close()
    migrate_task_extra_columns()
    migrate_calendar_promotions_dates()
    migrate_calendar_promotions_source()
    _ensure_calendar_promotions_index()


def _ensure_calendar_promotions_index() -> None:
    """기존 DB 마이그레이션 후 date_start 인덱스 생성."""
    import sqlite3 as sq

    c = _conn()
    try:
        try:
            c.execute(
                "CREATE INDEX IF NOT EXISTS idx_cal_promo_start ON calendar_promotions(date_start)"
            )
            c.commit()
        except sq.OperationalError:
            pass
    finally:
        c.close()


def migrate_calendar_promotions_dates() -> None:
    """기존 단일일(scheduled_for) 프로모션을 기간(date_start~date_end)으로 이전."""
    import sqlite3 as sq

    c = _conn()
    try:
        row = c.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='calendar_promotions'"
        ).fetchone()
        if not row:
            return
        info = c.execute("PRAGMA table_info(calendar_promotions)").fetchall()
        cols = {r[1] for r in info}
        if "date_start" not in cols:
            try:
                c.execute("ALTER TABLE calendar_promotions ADD COLUMN date_start TEXT")
                c.execute("ALTER TABLE calendar_promotions ADD COLUMN date_end TEXT")
                c.commit()
            except sq.OperationalError:
                pass
            cols.add("date_start")
            cols.add("date_end")
        if "scheduled_for" in cols:
            c.execute(
                """UPDATE calendar_promotions
                   SET date_start = scheduled_for, date_end = scheduled_for
                   WHERE date_start IS NULL OR TRIM(date_start) = ''
                      OR date_end IS NULL OR TRIM(date_end) = ''"""
            )
            c.commit()
    finally:
        c.close()


def migrate_calendar_promotions_source() -> None:
    """source(sheet/manual), sheet_row 컬럼 추가."""
    import sqlite3 as sq

    c = _conn()
    try:
        row = c.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='calendar_promotions'"
        ).fetchone()
        if not row:
            return
        info = c.execute("PRAGMA table_info(calendar_promotions)").fetchall()
        cols = {r[1] for r in info}
        if "source" not in cols:
            try:
                c.execute(
                    "ALTER TABLE calendar_promotions ADD COLUMN source TEXT DEFAULT 'manual'"
                )
                c.commit()
            except sq.OperationalError:
                pass
        if "sheet_row" not in cols:
            try:
                c.execute("ALTER TABLE calendar_promotions ADD COLUMN sheet_row INTEGER")
                c.commit()
            except sq.OperationalError:
                pass
        c.execute(
            """UPDATE calendar_promotions SET source = 'manual'
               WHERE source IS NULL OR TRIM(source) = ''"""
        )
        c.commit()
    finally:
        c.close()


def migrate_task_extra_columns() -> None:
    """기존 DB에 promotion_name, brand 컬럼 추가."""
    import sqlite3 as sq

    c = _conn()
    try:
        for col in ("promotion_name", "brand"):
            try:
                c.execute(f"ALTER TABLE tasks ADD COLUMN {col} TEXT DEFAULT ''")
                c.commit()
            except sq.OperationalError:
                pass
    finally:
        c.close()


def seed_if_empty() -> None:
    c = _conn()
    try:
        n = c.execute("SELECT COUNT(*) FROM users").fetchone()[0]
        if n > 0:
            return
        for i, (email, name) in enumerate(MEMBERS):
            uid = str(uuid.uuid4())
            c.execute(
                "INSERT INTO users (id, email, name) VALUES (?, ?, ?)",
                (uid, email, name),
            )
        for i, label in enumerate(DEFAULT_CATEGORIES):
            cid = str(uuid.uuid4())
            c.execute(
                "INSERT INTO team_categories (id, label, sort_order) VALUES (?, ?, ?)",
                (cid, label, i),
            )
        # 데모 일정 (서다경 첫 유저)
        row = c.execute(
            "SELECT id FROM users WHERE email = ?", ("seodakyeong@team.local",)
        ).fetchone()
        if row:
            tid = str(uuid.uuid4())
            now = datetime.utcnow().isoformat() + "Z"
            c.execute(
                """INSERT INTO tasks (id, user_id, scheduled_for, category, title, detail,
                   completed, created_at, updated_at) VALUES (?,?,?,?,?,?,0,?,?)""",
                (
                    tid,
                    row[0],
                    today_kst(),
                    "기타 업무",
                    "[데모] Streamlit 대시보드",
                    "구분·이월·캘린더를 사용해 보세요.",
                    now,
                    now,
                ),
            )
        c.commit()
    finally:
        c.close()


def migrate_legacy_categories() -> None:
    c = _conn()
    try:
        for old, new in LEGACY_LABELS.items():
            c.execute(
                "UPDATE tasks SET category = ? WHERE category = ?", (new, old)
            )
        c.commit()
    finally:
        c.close()


def list_users() -> list[dict[str, Any]]:
    c = _conn()
    try:
        rows = c.execute(
            "SELECT id, email, name FROM users ORDER BY name COLLATE NOCASE"
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        c.close()


def list_categories_merged() -> list[dict[str, Any]]:
    c = _conn()
    try:
        from_table = c.execute(
            "SELECT id, label, sort_order FROM team_categories ORDER BY sort_order, label COLLATE NOCASE"
        ).fetchall()
        seen: dict[str, dict] = {}
        for r in from_table:
            seen[r["label"]] = {
                "id": r["id"],
                "label": r["label"],
                "sort_order": r["sort_order"],
            }
        task_cats = c.execute(
            "SELECT DISTINCT category FROM tasks WHERE category IS NOT NULL AND category != ''"
        ).fetchall()
        syn = 0
        for (lab,) in task_cats:
            if lab not in seen:
                seen[lab] = {
                    "id": f"task-{syn}-{lab[:20]}",
                    "label": lab,
                    "sort_order": 9999,
                }
                syn += 1
        out = sorted(seen.values(), key=lambda x: (x["sort_order"], x["label"]))
        return out
    finally:
        c.close()


def upsert_category(label: str) -> None:
    label = label.strip()
    if not label:
        return
    c = _conn()
    try:
        row = c.execute(
            "SELECT id FROM team_categories WHERE label = ?", (label,)
        ).fetchone()
        if not row:
            cid = str(uuid.uuid4())
            c.execute(
                "INSERT INTO team_categories (id, label, sort_order) VALUES (?,?,999)",
                (cid, label),
            )
            c.commit()
    finally:
        c.close()


def delete_category(label: str) -> None:
    fallback = "기타 업무"
    if label == fallback:
        raise ValueError(f'"{fallback}"은(는) 삭제할 수 없습니다.')
    c = _conn()
    try:
        c.execute("DELETE FROM team_categories WHERE label = ?", (label,))
        c.execute(
            "UPDATE tasks SET category = ? WHERE category = ?", (fallback, label)
        )
        row = c.execute(
            "SELECT id FROM team_categories WHERE label = ?", (fallback,)
        ).fetchone()
        if not row:
            cid = str(uuid.uuid4())
            c.execute(
                "INSERT INTO team_categories (id, label, sort_order) VALUES (?,?,99)",
                (cid, fallback),
            )
        c.commit()
    finally:
        c.close()


def tasks_for_date(ymd: str) -> list[dict[str, Any]]:
    c = _conn()
    try:
        rows = c.execute(
            """
            SELECT t.*, u.name AS user_name
            FROM tasks t
            JOIN users u ON u.id = t.user_id
            WHERE t.scheduled_for = ?
            ORDER BY u.name COLLATE NOCASE, t.completed ASC, t.created_at ASC
            """,
            (ymd,),
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        c.close()


def create_task(
    user_id: str,
    scheduled_for: str,
    category: str,
    title: str,
    detail: str,
    promotion_name: str = "",
    brand: str = "",
) -> str:
    tid = str(uuid.uuid4())
    now = datetime.utcnow().isoformat() + "Z"
    pn = (promotion_name or "").strip()
    br = (brand or "").strip()
    c = _conn()
    try:
        c.execute(
            """INSERT INTO tasks (id, user_id, scheduled_for, category, title, detail,
               promotion_name, brand, completed, created_at, updated_at)
               VALUES (?,?,?,?,?,?,?,?,0,?,?)""",
            (
                tid,
                user_id,
                scheduled_for,
                category.strip(),
                title.strip(),
                detail.strip(),
                pn,
                br,
                now,
                now,
            ),
        )
        c.commit()
        upsert_category(category.strip())
        return tid
    finally:
        c.close()


def update_task_complete(task_id: str, completed: bool) -> None:
    now = datetime.utcnow().isoformat() + "Z"
    c = _conn()
    try:
        if completed:
            c.execute(
                "UPDATE tasks SET completed = 1, completed_at = ?, completed_type = 'done', updated_at = ? WHERE id = ?",
                (now, now, task_id),
            )
        else:
            c.execute(
                "UPDATE tasks SET completed = 0, completed_at = NULL, completed_type = NULL, updated_at = ? WHERE id = ?",
                (now, task_id),
            )
        c.commit()
    finally:
        c.close()


def delete_task(task_id: str) -> None:
    c = _conn()
    try:
        c.execute("DELETE FROM tasks WHERE id = ?", (task_id,))
        c.commit()
    finally:
        c.close()


def get_task(task_id: str) -> dict[str, Any] | None:
    c = _conn()
    try:
        r = c.execute("SELECT * FROM tasks WHERE id = ?", (task_id,)).fetchone()
        return dict(r) if r else None
    finally:
        c.close()


def tasks_csv_for_date(ymd: str) -> str:
    rows = tasks_for_date(ymd)
    lines = ["날짜,담당자,카테고리,프로모션,브랜드,제목,상세,완료,비고"]
    for t in rows:
        status = (
            "이월됨"
            if t.get("completed") and t.get("completed_type") == "rolled"
            else ("완료" if t.get("completed") else "미완료")
        )
        cat = LEGACY_LABELS.get(t["category"], t["category"])
        def esc(s: str) -> str:
            s = str(s).replace('"', '""')
            return f'"{s}"' if "," in s or "\n" in s else s

        pn = t.get("promotion_name") or ""
        br = t.get("brand") or ""
        lines.append(
            f'{ymd},{esc(t["user_name"])},{esc(cat)},{esc(pn)},{esc(br)},{esc(t["title"])},{esc(t.get("detail") or "")},{"Y" if t.get("completed") else "N"},{esc(status)}'
        )
    return "\ufeff" + "\n".join(lines)


def distinct_task_dates_in_month(year: int, month: int) -> set[str]:
    """해당 연·월에 일정이 있는 날짜(YYYY-MM-DD) 집합."""
    prefix = f"{year}-{month:02d}-"
    c = _conn()
    try:
        rows = c.execute(
            "SELECT DISTINCT scheduled_for FROM tasks WHERE scheduled_for LIKE ?",
            (prefix + "%",),
        ).fetchall()
        return {r[0] for r in rows}
    finally:
        c.close()


def _insert_calendar_promotion(
    c: sqlite3.Connection,
    tid: str,
    title: str,
    ds: str,
    de: str,
    detail_s: str,
    color: str,
    now: str,
    *,
    source: str = "manual",
    sheet_row: int | None = None,
) -> None:
    col_names = {r[1] for r in c.execute("PRAGMA table_info(calendar_promotions)").fetchall()}
    if "scheduled_for" in col_names:
        cols = [
            "id",
            "title",
            "scheduled_for",
            "date_start",
            "date_end",
            "detail",
            "color_hex",
            "created_at",
        ]
        vals: list[Any] = [tid, title, ds, ds, de, detail_s, color, now]
    else:
        cols = [
            "id",
            "title",
            "date_start",
            "date_end",
            "detail",
            "color_hex",
            "created_at",
        ]
        vals = [tid, title, ds, de, detail_s, color, now]
    if "source" in col_names:
        cols.append("source")
        vals.append(source)
    if "sheet_row" in col_names:
        cols.append("sheet_row")
        vals.append(sheet_row)
    ph = ",".join(["?"] * len(vals))
    c.execute(
        f"INSERT INTO calendar_promotions ({','.join(cols)}) VALUES ({ph})",
        vals,
    )


def create_calendar_promotion(
    title: str,
    date_start: str,
    date_end: str,
    detail: str = "",
    *,
    source: str = "manual",
    sheet_row: int | None = None,
) -> str:
    """캘린더 전용 프로모션(기간). 등록마다 팔레트에서 색을 랜덤 지정."""
    tid = str(uuid.uuid4())
    now = datetime.utcnow().isoformat() + "Z"
    t = (title or "").strip()
    if not t:
        raise ValueError("프로모션 이름을 입력하세요.")
    ds = (date_start or "").strip()
    de = (date_end or "").strip()
    if not ds or not de:
        raise ValueError("시작일과 종료일을 모두 선택하세요.")
    if ds > de:
        raise ValueError("시작일이 종료일보다 늦을 수 없습니다.")
    color = random.choice(PROMO_COLOR_PALETTE)
    detail_s = (detail or "").strip()
    c = _conn()
    try:
        _insert_calendar_promotion(
            c,
            tid,
            t,
            ds,
            de,
            detail_s,
            color,
            now,
            source=source,
            sheet_row=sheet_row,
        )
        c.commit()
        return tid
    finally:
        c.close()


def replace_sheet_promotions(rows: list[dict[str, Any]]) -> int:
    """시트 동기화: 기존 source=sheet 삭제 후 일괄 삽입."""
    c = _conn()
    try:
        col_names = {r[1] for r in c.execute("PRAGMA table_info(calendar_promotions)").fetchall()}
        if "source" in col_names:
            c.execute("DELETE FROM calendar_promotions WHERE source = 'sheet'")
            c.commit()
        now = datetime.utcnow().isoformat() + "Z"
        n = 0
        for it in rows:
            tid = str(uuid.uuid4())
            color = random.choice(PROMO_COLOR_PALETTE)
            _insert_calendar_promotion(
                c,
                tid,
                (it.get("title") or "").strip() or "(제목없음)",
                it["date_start"],
                it["date_end"],
                (it.get("detail") or "").strip(),
                color,
                now,
                source="sheet",
                sheet_row=it.get("sheet_row"),
            )
            n += 1
        c.commit()
        return n
    finally:
        c.close()


def calendar_promotions_in_month(year: int, month: int) -> list[dict[str, Any]]:
    import calendar as cal_module

    last_d = cal_module.monthrange(year, month)[1]
    first_s = f"{year}-{month:02d}-01"
    last_s = f"{year}-{month:02d}-{last_d:02d}"
    c = _conn()
    try:
        rows = c.execute(
            """SELECT * FROM calendar_promotions
               WHERE date_start <= ? AND date_end >= ?
               ORDER BY date_start, created_at""",
            (last_s, first_s),
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        c.close()


def calendar_promotions_for_date(ymd: str) -> list[dict[str, Any]]:
    c = _conn()
    try:
        rows = c.execute(
            """SELECT * FROM calendar_promotions
               WHERE date_start <= ? AND date_end >= ?
               ORDER BY date_start, created_at""",
            (ymd, ymd),
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        c.close()


def delete_calendar_promotion(promo_id: str) -> None:
    c = _conn()
    try:
        c.execute("DELETE FROM calendar_promotions WHERE id = ?", (promo_id,))
        c.commit()
    finally:
        c.close()


def create_daily_memo(memo_date: str, body: str) -> str:
    """오늘(또는 지정일) 팀 메모. 작성마다 카드 색 랜덤."""
    b = (body or "").strip()
    if not b:
        raise ValueError("메모 내용을 입력하세요.")
    mid = str(uuid.uuid4())
    now = datetime.utcnow().isoformat() + "Z"
    color = random.choice(MEMO_CARD_COLORS)
    c = _conn()
    try:
        c.execute(
            """INSERT INTO daily_memos (id, memo_date, body, color_hex, created_at)
               VALUES (?,?,?,?,?)""",
            (mid, memo_date, b, color, now),
        )
        c.commit()
        return mid
    finally:
        c.close()


def list_daily_memos(memo_date: str) -> list[dict[str, Any]]:
    c = _conn()
    try:
        rows = c.execute(
            """SELECT id, memo_date, body, color_hex, created_at
               FROM daily_memos WHERE memo_date = ?
               ORDER BY created_at DESC""",
            (memo_date,),
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        c.close()


def delete_daily_memo(memo_id: str) -> None:
    c = _conn()
    try:
        c.execute("DELETE FROM daily_memos WHERE id = ?", (memo_id,))
        c.commit()
    finally:
        c.close()
