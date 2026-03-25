"""샤크닌자 캘린더 — 구글 시트 연동, 주 단위 이어진 프로모션 막대, 팀 할 일"""
from __future__ import annotations

import calendar as cal_module
from collections import defaultdict
from datetime import date

import streamlit as st


def _apply_selection(ymd: str) -> None:
    st.session_state.selected_ymd = ymd
    y, m, _ = map(int, ymd.split("-"))
    st.session_state.view_year = y
    st.session_state.view_month = m


def _escape_html(s: str) -> str:
    return (
        (s or "")
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


def _week_promo_bars_html(week_dates: list[date], promo_rows: list[dict]) -> str:
    """한 주(일~토) 안에서 기간 막대를 한 줄로 이어서 표시. 이름은 시작 구간에만."""
    from kst import promo_range_label_mdy

    if not week_dates or len(week_dates) != 7:
        return ""
    week_start, week_end = week_dates[0], week_dates[-1]
    ws, we = week_start.isoformat(), week_end.isoformat()
    overlapping = [p for p in promo_rows if p["date_start"] <= we and p["date_end"] >= ws]
    if not overlapping:
        return ""

    rows_html: list[str] = []
    for p in sorted(overlapping, key=lambda x: (x["date_start"], x["title"])):
        ds = date.fromisoformat(p["date_start"])
        de = date.fromisoformat(p["date_end"])
        seg_start = max(ds, week_start)
        seg_end = min(de, week_end)
        if seg_start > seg_end:
            continue
        start_col = next(i for i, d in enumerate(week_dates) if d == seg_start)
        end_col = next(i for i, d in enumerate(week_dates) if d == seg_end)
        col_span = end_col - start_col + 1
        grid_start = start_col + 1
        grid_end_excl = start_col + col_span + 1
        color = p["color_hex"]
        title = _escape_html(p["title"])
        rng = promo_range_label_mdy(p["date_start"], p["date_end"])
        show_text = (seg_start == ds) or (ds < week_start and seg_start == week_start)
        text = f"★ {title} · {rng}" if show_text else ""
        min_h = "36px" if text else "14px"
        fz = "0.92rem" if text else "0"
        fw = "700" if text else "400"
        rows_html.append(
            f"""<div style="display:grid;grid-template-columns:repeat(7,minmax(0,1fr));gap:4px;margin-bottom:8px;">
<div style="grid-column:{grid_start} / {grid_end_excl};background:{color};color:#fff;border-radius:12px;padding:6px 10px;font-size:{fz};font-weight:{fw};line-height:1.3;min-height:{min_h};overflow:hidden;text-overflow:ellipsis;white-space:nowrap;display:flex;align-items:center;justify-content:center;box-shadow:0 2px 6px rgba(0,0,0,.18);">{text}</div>
</div>"""
        )
    return "".join(rows_html)


def main() -> None:
    from db import (
        calendar_promotions_for_date,
        calendar_promotions_in_month,
        create_calendar_promotion,
        create_task,
        delete_calendar_promotion,
        replace_sheet_promotions,
        distinct_task_dates_in_month,
        init_db,
        list_categories_merged,
        list_users,
        migrate_legacy_categories,
        seed_if_empty,
        tasks_csv_for_date,
        tasks_for_date,
        update_task_complete,
        upsert_category,
    )
    from kst import promo_range_label_mdy, today_kst
    from logic import display_category, rollover_incomplete_all

    init_db()
    seed_if_empty()
    migrate_legacy_categories()
    rollover_incomplete_all()

    today = today_kst()
    if "selected_ymd" not in st.session_state:
        st.session_state.selected_ymd = today
    if "view_year" not in st.session_state:
        y, m, _ = map(int, st.session_state.selected_ymd.split("-"))
        st.session_state.view_year = y
        st.session_state.view_month = m

    users = list_users()
    if not users:
        st.error("사용자 데이터가 없습니다.")
        return

    users_sorted = sorted(users, key=lambda u: u["name"])
    uid_list = [u["id"] for u in users_sorted]
    name_by_id = {u["id"]: u["name"] for u in users}
    id_by_name = {u["name"]: u["id"] for u in users}

    if "cal_my_uid" not in st.session_state:
        st.session_state.cal_my_uid = users[0]["id"]

    d_in = st.date_input(
        "기준 날짜 (팀 할 일·달력 선택)",
        value=date.fromisoformat(st.session_state.selected_ymd),
    )
    if d_in.isoformat() != st.session_state.selected_ymd:
        _apply_selection(d_in.isoformat())
        st.rerun()

    ymd = st.session_state.selected_ymd
    tasks = tasks_for_date(ymd)

    head_l, head_r = st.columns([3, 1])
    with head_l:
        st.title("샤크닌자 캘린더")
        st.caption(
            "주 단위로 프로모션 기간이 색 막대로 이어집니다. "
            "구글 시트에서 가져오기 + 수동 등록을 함께 사용할 수 있습니다."
        )
    with head_r:
        csv_data = tasks_csv_for_date(ymd)
        st.download_button(
            "이 날짜 전체 CSV",
            data=csv_data.encode("utf-8-sig"),
            file_name=f"team_tasks_{ymd}.csv",
            mime="text/csv",
            use_container_width=True,
        )

    col_left, col_right = st.columns([1.85, 1])

    vy = st.session_state.view_year
    vm = st.session_state.view_month
    dates_with = distinct_task_dates_in_month(vy, vm)
    promo_rows = calendar_promotions_in_month(vy, vm)
    cal_sun = cal_module.Calendar(firstweekday=cal_module.SUNDAY)
    weeks = cal_sun.monthdatescalendar(vy, vm)

    with col_left:
        nav1, nav2, nav3 = st.columns([1, 2, 1])
        with nav1:
            if st.button("◀ 이전", use_container_width=True, key="cal_prev"):
                if vm == 1:
                    st.session_state.view_year = vy - 1
                    st.session_state.view_month = 12
                else:
                    st.session_state.view_month = vm - 1
                st.rerun()
        with nav2:
            st.markdown(
                f"<div style='text-align:center;font-size:1.55rem;font-weight:700;padding:0.45rem 0'>{vy}년 {vm}월</div>",
                unsafe_allow_html=True,
            )
        with nav3:
            if st.button("다음 ▶", use_container_width=True, key="cal_next"):
                if vm == 12:
                    st.session_state.view_year = vy + 1
                    st.session_state.view_month = 1
                else:
                    st.session_state.view_month = vm + 1
                st.rerun()

        st.markdown("##### 구글 시트 동기화")
        st.caption(
            "[매드업 x 샤크닌자 프로모션 전달](https://docs.google.com/spreadsheets/d/1XRzecgC4E_kejFFlendXcw-HttB7J0HC29GKiswvXh0/edit?gid=1218471148) "
            "탭 **프로모션 운영 및 업무 요청** — 시트를 **링크가 있는 모든 사용자 보기**로 공개해야 CSV로 읽습니다."
        )
        if st.button("시트에서 프로모션 가져오기 (E~F·H·I~Q)", type="primary", key="btn_sheet_sync"):
            try:
                from sheet_sync import load_promotions_from_google_sheet

                rows, warns = load_promotions_from_google_sheet()
                n = replace_sheet_promotions(rows)
                msg = f"반영 완료: {n}건 (기존 시트 연동분은 덮어씀)"
                st.success(msg)
                if warns:
                    st.warning("일부 행 스킵:\n" + "\n".join(warns[:25]))
                st.rerun()
            except Exception as e:
                st.error(f"가져오기 실패: {e}")

        wcols = st.columns(7)
        for i, lab in enumerate(["일", "월", "화", "수", "목", "금", "토"]):
            with wcols[i]:
                st.markdown(f"<div style='text-align:center;font-weight:700;font-size:1.05rem'>{lab}</div>", unsafe_allow_html=True)

        for wi, week_dates in enumerate(weeks):
            bar_html = _week_promo_bars_html(list(week_dates), promo_rows)
            if bar_html:
                st.markdown(
                    f"<div style='margin:4px 0 8px 0'>{bar_html}</div>",
                    unsafe_allow_html=True,
                )
            else:
                st.markdown("<div style='height:4px'></div>", unsafe_allow_html=True)

            day_cols = st.columns(7)
            for i, d in enumerate(week_dates):
                with day_cols[i]:
                    if d.month != vm:
                        st.markdown(
                            f"<div style='text-align:center;color:#bbb;font-size:1.05rem;padding:0.5rem 0'>{d.day}</div>",
                            unsafe_allow_html=True,
                        )
                    else:
                        cell_ymd = d.isoformat()
                        active = [
                            p
                            for p in promo_rows
                            if p["date_start"] <= cell_ymd <= p["date_end"]
                        ]
                        has_task = cell_ymd in dates_with
                        is_sel = cell_ymd == st.session_state.selected_ymd
                        star_here = any(cell_ymd == p["date_start"] for p in active)
                        parts = [str(d.day)]
                        if star_here:
                            parts.append("★")
                        if has_task:
                            parts.append("·")
                        label = " ".join(parts)
                        btn_type = "primary" if is_sel else "secondary"
                        if st.button(
                            label,
                            key=f"calday_{cell_ymd}_{wi}_{i}",
                            use_container_width=True,
                            type=btn_type,
                        ):
                            _apply_selection(cell_ymd)
                            st.rerun()

        st.caption(
            f"선택: **{st.session_state.selected_ymd}**  ·  "
            "**★** 프로모션 시작일  ·  **·** 할 일  ·  다른 달 날짜는 회색"
        )

        st.markdown("---")
        st.markdown("**프로모션 수동 등록** (시작~종료)")
        with st.form("promo_form", clear_on_submit=True):
            p_title = st.text_input("프로모션 이름", placeholder="필수")
            c1, c2 = st.columns(2)
            with c1:
                p_start = st.date_input(
                    "시작일",
                    value=date.fromisoformat(st.session_state.selected_ymd),
                    key="promo_start",
                )
            with c2:
                p_end = st.date_input(
                    "종료일",
                    value=date.fromisoformat(st.session_state.selected_ymd),
                    key="promo_end",
                )
            p_detail = st.text_area("상세사항", placeholder="선택")
            p_save = st.form_submit_button("프로모션 반영", type="primary")
        if p_save:
            try:
                create_calendar_promotion(
                    p_title,
                    p_start.isoformat(),
                    p_end.isoformat(),
                    p_detail or "",
                )
                _apply_selection(p_start.isoformat())
                st.success("달력에 반영했습니다.")
                st.rerun()
            except ValueError as e:
                st.error(str(e))

    with col_right:
        promos_today = calendar_promotions_for_date(ymd)
        st.subheader("선택한 날짜의 프로모션")
        st.markdown(f"**{ymd}**")
        if not promos_today:
            st.caption("이 날짜에 해당하는 프로모션이 없습니다.")
        else:
            for p in promos_today:
                cc = p.get("color_hex") or "#888"
                rng = promo_range_label_mdy(p["date_start"], p["date_end"])
                src = (p.get("source") or "manual").strip()
                badge = "시트" if src == "sheet" else "직접"
                with st.container(border=True):
                    st.caption(f"[{badge}]")
                    st.markdown(
                        f"<span style='color:{cc};font-weight:700'>★</span> **{_escape_html(p['title'])}**",
                        unsafe_allow_html=True,
                    )
                    st.caption(f"기간: {rng}")
                    if p.get("detail"):
                        st.caption(p["detail"])
                    if st.button("삭제", key=f"del_prm_{p['id']}"):
                        delete_calendar_promotion(p["id"])
                        st.rerun()

    st.divider()
    st.subheader(f"{ymd} · 팀 할 일")

    cat_rows = list_categories_merged()
    labels = [c["label"] for c in cat_rows]

    sel_name = st.selectbox(
        "담당자 (할 일 추가·완료/삭제 기준)",
        options=[name_by_id[i] for i in uid_list],
        index=uid_list.index(st.session_state.cal_my_uid)
        if st.session_state.cal_my_uid in uid_list
        else 0,
        key="cal_assignee",
    )
    st.session_state.cal_my_uid = id_by_name[sel_name]
    my_uid = st.session_state.cal_my_uid

    with st.expander("할 일 추가 (담당·구분·제목) — 10팀 TODO와 같은 날짜에 반영됩니다", expanded=False):
        with st.form("task_add_form", clear_on_submit=True):
            cat_in = st.text_input("구분", value="기타 업무" if labels else "")
            title = st.text_input("제목 (할 일)", placeholder="필수")
            detail = st.text_area("상세", placeholder="선택")
            brand = st.text_input("브랜드", placeholder="선택")
            tsave = st.form_submit_button("할 일 저장", type="primary")
        if tsave:
            c = (cat_in or "").strip()
            tit = (title or "").strip()
            if not c or not tit:
                st.error("구분과 제목을 입력하세요.")
            else:
                create_task(
                    my_uid,
                    ymd,
                    c,
                    tit,
                    detail or "",
                    promotion_name="",
                    brand=brand or "",
                )
                upsert_category(c)
                st.success("저장했습니다.")
                st.rerun()

    if not tasks:
        st.info("이 날짜에 등록된 업무가 없습니다.")
    else:
        by_name: dict[str, list] = defaultdict(list)
        for t in tasks:
            by_name[t["user_name"]].append(t)

        for nm in sorted(by_name.keys()):
            st.markdown(f"##### {nm}")
            for t in by_name[nm]:
                rolled = t.get("completed") and t.get("completed_type") == "rolled"
                with st.container(border=True):
                    st.write(f"**{display_category(t['category'])}**")
                    pn = (t.get("promotion_name") or "").strip()
                    br = (t.get("brand") or "").strip()
                    if pn or br:
                        st.caption(f"프로모션: {pn or '—'}  ·  브랜드: {br or '—'}")
                    if rolled:
                        st.caption("이월됨")
                    elif t.get("rolled_from_id") and not t.get("completed"):
                        st.caption("어제에서 이월")
                    title_txt = t["title"]
                    if t.get("completed") and not rolled:
                        st.markdown(f"~~{title_txt}~~")
                    else:
                        st.markdown(f"**{title_txt}**")
                    if t.get("detail"):
                        st.caption(t["detail"])
                    if not rolled and t["user_id"] == my_uid:
                        b1, b2 = st.columns(2)
                        with b1:
                            if t["completed"]:
                                if st.button("완료 취소", key=f"cal_unc_{t['id']}"):
                                    update_task_complete(t["id"], False)
                                    st.rerun()
                            else:
                                if st.button("완료", key=f"cal_co_{t['id']}"):
                                    update_task_complete(t["id"], True)
                                    st.rerun()
                        with b2:
                            if st.button("삭제", key=f"cal_rm_{t['id']}"):
                                delete_task(t["id"])
                                st.rerun()
                    elif not rolled:
                        st.caption("담당자만 수정")


main()
