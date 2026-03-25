"""미완료 이월 (KST 어제 → 오늘)."""
from __future__ import annotations

import uuid
from datetime import datetime

from kst import add_days_kst, today_kst

from db import _conn, list_users


def rollover_incomplete_all() -> tuple[int, int]:
    """(유저 수, 이월된 태스크 수)"""
    today = today_kst()
    yesterday = add_days_kst(today, -1)
    users = list_users()
    moved_total = 0
    for u in users:
        moved_total += _rollover_user(u["id"], yesterday, today)
    return len(users), moved_total


def _rollover_user(user_id: str, yesterday: str, today: str) -> int:
    c = _conn()
    moved = 0
    try:
        stale = c.execute(
            """SELECT id FROM tasks WHERE user_id = ? AND scheduled_for = ? AND completed = 0""",
            (user_id, yesterday),
        ).fetchall()
        for (tid,) in stale:
            exists = c.execute(
                """SELECT id FROM tasks WHERE user_id = ? AND scheduled_for = ? AND rolled_from_id = ?""",
                (user_id, today, tid),
            ).fetchone()
            if exists:
                continue
            row = c.execute("SELECT * FROM tasks WHERE id = ?", (tid,)).fetchone()
            if not row:
                continue
            d = dict(row)
            now = datetime.utcnow().isoformat() + "Z"
            new_id = str(uuid.uuid4())
            c.execute(
                """UPDATE tasks SET completed = 1, completed_at = ?, completed_type = 'rolled', updated_at = ? WHERE id = ?""",
                (now, now, tid),
            )
            c.execute(
                """INSERT INTO tasks (id, user_id, scheduled_for, category, title, detail,
                   promotion_name, brand, completed,
                   completed_at, completed_type, rolled_from_id, created_at, updated_at)
                   VALUES (?,?,?,?,?,?,?,?,0,NULL,NULL,?,?,?)""",
                (
                    new_id,
                    d["user_id"],
                    today,
                    d["category"],
                    d["title"],
                    d.get("detail") or "",
                    d.get("promotion_name") or "",
                    d.get("brand") or "",
                    tid,
                    now,
                    now,
                ),
            )
            moved += 1
        c.commit()
    finally:
        c.close()
    return moved


def display_category(stored: str) -> str:
    from db import LEGACY_LABELS

    return LEGACY_LABELS.get(stored, stored)
