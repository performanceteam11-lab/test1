"""구글 시트(프로모션 운영 및 업무 요청) CSV 가져오기."""
from __future__ import annotations

import csv
import io
import re
from datetime import date
from typing import Any

import requests

# [프로모션 운영 및 업무 요청] 탭 — 링크에 있는 gid와 동일
DEFAULT_SHEET_ID = "1XRzecgC4E_kejFFlendXcw-HttB7J0HC29GKiswvXh0"
DEFAULT_GID = "1218471148"

# 열: E=시작, F=종료, H=프로모션명, I~Q=상세
COL_START = 4
COL_END = 5
COL_PROMO = 7
COL_I = 8
COL_Q = 16  # 포함 (I~Q → 9열)

DEFAULT_DETAIL_LABELS = [
    "주력 상품",
    "제품 코드",
    "정상가 (MSRP)",
    "실제 판매가 (ASP)",
    "할인율",
    "USP",
    "상세 특징",
    "상세 스킴",
    "MKT 요청 포인트 (컨셉)",
]


def _empty_note(s: str) -> str:
    s = (s or "").strip()
    return s if s else "공란(확인 필요)"


def parse_sheet_date(raw: str, default_year: int) -> date | None:
    raw = (raw or "").strip()
    if not raw:
        return None
    raw = raw.replace(".", "/").replace("-", "/")
    # YYYY/M/D
    m = re.match(r"^(\d{4})/(\d{1,2})/(\d{1,2})$", raw)
    if m:
        y, mo, d = int(m.group(1)), int(m.group(2)), int(m.group(3))
        return date(y, mo, d)
    # M/D/YYYY
    m = re.match(r"^(\d{1,2})/(\d{1,2})/(\d{4})$", raw)
    if m:
        mo, d, y = int(m.group(1)), int(m.group(2)), int(m.group(3))
        return date(y, mo, d)
    # M/D
    m = re.match(r"^(\d{1,2})/(\d{1,2})$", raw)
    if m:
        mo, d = int(m.group(1)), int(m.group(2))
        return date(default_year, mo, d)
    try:
        return date.fromisoformat(raw[:10])
    except ValueError:
        return None


def build_detail_block(
    row: list[str],
    header_labels: list[str] | None,
) -> str:
    labels = header_labels or DEFAULT_DETAIL_LABELS
    lines: list[str] = []
    for i, col_idx in enumerate(range(COL_I, COL_Q + 1)):
        cell = row[col_idx] if len(row) > col_idx else ""
        lab = labels[i] if i < len(labels) else f"열{col_idx + 1}"
        lines.append(f"- {lab}: {_empty_note(cell)}")
    return "\n".join(lines)


def parse_promotion_rows_from_csv(
    text: str,
    default_year: int | None = None,
) -> tuple[list[dict[str, Any]], list[str]]:
    """
    반환: (rows, header_labels_for_I_Q)
    각 row: title, date_start, date_end, detail, sheet_row (1-based 엑셀 행)
    """
    if default_year is None:
        default_year = date.today().year

    warnings: list[str] = []
    f = io.StringIO(text)
    reader = csv.reader(f)
    rows_list = list(reader)

    header_idx = None
    header_row: list[str] = []
    for i, row in enumerate(rows_list):
        if len(row) <= COL_START:
            continue
        h = (row[COL_START] or "").strip().lower()
        if "start" in h and "date" in h:
            header_idx = i
            header_row = row
            break
    if header_idx is None:
        raise ValueError(
            "CSV에서 E열 'Start date' 헤더 행을 찾지 못했습니다. "
            "시트를 '링크가 있는 모든 사용자 보기'로 공개했는지 확인해 주세요."
        )

    labels_iq: list[str] = []
    for idx, j in enumerate(range(COL_I, COL_Q + 1)):
        default = (
            DEFAULT_DETAIL_LABELS[idx]
            if idx < len(DEFAULT_DETAIL_LABELS)
            else f"열{j + 1}"
        )
        if j < len(header_row) and (header_row[j] or "").strip():
            labels_iq.append((header_row[j] or "").strip())
        else:
            labels_iq.append(default)

    out: list[dict[str, Any]] = []
    for line_no, row in enumerate(rows_list[header_idx + 1 :], start=header_idx + 2):
        if len(row) <= max(COL_PROMO, COL_END):
            continue
        if len(row) > 1 and (row[1] or "").strip() == "예시":
            continue
        start_s = row[COL_START].strip() if len(row) > COL_START else ""
        end_s = row[COL_END].strip() if len(row) > COL_END else ""
        raw_title = row[COL_PROMO] if len(row) > COL_PROMO else ""
        title = " ".join((raw_title or "").split())
        if not start_s and not end_s:
            continue
        ds = parse_sheet_date(start_s, default_year)
        de = parse_sheet_date(end_s, default_year)
        if ds is None or de is None:
            warnings.append(f"{line_no}행: 시작일/종료일을 해석하지 못함 (시작={start_s!r}, 종료={end_s!r})")
            continue
        if not title:
            title = f"(제목없음·{line_no}행)"
        detail = build_detail_block(row, labels_iq)
        out.append(
            {
                "title": title,
                "date_start": ds.isoformat(),
                "date_end": de.isoformat(),
                "detail": detail,
                "sheet_row": line_no,
            }
        )

    return out, warnings


def fetch_sheet_csv(sheet_id: str, gid: str, timeout: int = 45) -> str:
    url = f"https://docs.google.com/spreadsheets/d/{sheet_id}/export?format=csv&gid={gid}"
    r = requests.get(url, timeout=timeout)
    r.raise_for_status()
    raw = r.content
    try:
        return raw.decode("utf-8-sig")
    except UnicodeDecodeError:
        return raw.decode("utf-8", errors="replace")


def load_promotions_from_google_sheet(
    sheet_id: str | None = None,
    gid: str | None = None,
    default_year: int | None = None,
) -> tuple[list[dict[str, Any]], list[str]]:
    """
    시트를 CSV로 받아 파싱.
    공개(링크가 있는 모든 사용자 보기 가능)여야 합니다.
    """
    sid = sheet_id or DEFAULT_SHEET_ID
    g = gid or DEFAULT_GID
    text = fetch_sheet_csv(sid, g)
    rows, warns = parse_promotion_rows_from_csv(text, default_year=default_year)
    return rows, warns
