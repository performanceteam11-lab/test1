"""
10팀 TODO — 오늘의 할 일
실행(사이드바에 이 이름으로 표시됨): streamlit run "10팀 TODO.py"
※ 예전 app.py 엔트리는 제거되었습니다. 위 파일로 실행해 주세요.
"""
from __future__ import annotations

from collections import defaultdict
from datetime import date

import streamlit as st

st.set_page_config(
    page_title="10팀 TODO",
    layout="wide",
    initial_sidebar_state="collapsed",
)


def main() -> None:
    from db import (
        create_daily_memo,
        create_task,
        delete_category,
        delete_daily_memo,
        delete_task,
        init_db,
        list_categories_merged,
        list_daily_memos,
        list_users,
        migrate_legacy_categories,
        seed_if_empty,
        tasks_csv_for_date,
        tasks_for_date,
        update_task_complete,
        upsert_category,
    )
    from kst import today_kst
    from logic import display_category, rollover_incomplete_all

    init_db()
    seed_if_empty()
    migrate_legacy_categories()

    _, moved = rollover_incomplete_all()
    if moved > 0:
        st.success(f"어제 미완료 {moved}건을 오늘 일정으로 옮겼습니다. (전체 팀)")

    users = list_users()
    if not users:
        st.error("사용자 데이터가 없습니다. data 폴더를 지우고 다시 실행해 보세요.")
        return

    users_sorted = sorted(users, key=lambda u: u["name"])
    uid_list = [u["id"] for u in users_sorted]
    name_by_id = {u["id"]: u["name"] for u in users}
    id_by_name = {u["name"]: u["id"] for u in users}

    if "my_uid" not in st.session_state:
        st.session_state.my_uid = users[0]["id"]

    today = today_kst()
    st.title("오늘의 할 일 (전체)")
    st.caption(f"한국 시간 기준 오늘: {today} · 일정 날짜를 바꾸면 캘린더 해당 날짜에도 동일하게 반영됩니다.")

    sel_name = st.selectbox(
        "내 담당 (추가·수정)",
        options=[name_by_id[i] for i in uid_list],
        index=uid_list.index(st.session_state.my_uid)
        if st.session_state.my_uid in uid_list
        else 0,
    )
    st.session_state.my_uid = id_by_name[sel_name]
    my_uid = st.session_state.my_uid

    cat_rows = list_categories_merged()
    labels = [c["label"] for c in cat_rows]

    if "cat_quick" not in st.session_state:
        st.session_state.cat_quick = "기타 업무"

    st.subheader("새 업무 추가")
    st.caption('상단 "내 담당"으로 등록 주인이 정해집니다. 일정 날짜는 캘린더와 동일 DB에 저장됩니다.')

    if labels:
        st.markdown("**등록된 구분** — 클릭하면 아래 입력란에 반영됩니다.")
        n_cols = min(4, max(1, len(labels)))
        for row_start in range(0, len(labels), n_cols):
            chunk = labels[row_start : row_start + n_cols]
            cols = st.columns(len(chunk))
            for j, lab in enumerate(chunk):
                with cols[j]:
                    if st.button(lab, key=f"pick_{row_start}_{j}_{lab}", use_container_width=True):
                        st.session_state.cat_quick = lab
                        st.session_state.cat_field = lab
                        st.rerun()

    deletable = [l for l in labels if l != "기타 업무"]
    if deletable:
        with st.expander("구분 삭제 (해당 구분 일정은 「기타 업무」로 변경됩니다)"):
            pick_del = st.selectbox("삭제할 구분", deletable, key="del_cat_pick")
            if st.button("선택한 구분 삭제", type="primary"):
                try:
                    delete_category(pick_del)
                    if st.session_state.cat_quick == pick_del:
                        st.session_state.cat_quick = "기타 업무"
                    st.success("삭제했습니다.")
                    st.rerun()
                except ValueError as e:
                    st.error(str(e))

    if "cat_field" not in st.session_state:
        st.session_state.cat_field = st.session_state.cat_quick

    with st.form("add_task_form", clear_on_submit=False):
        task_day = st.date_input("일정 날짜", value=date.fromisoformat(today))
        cat_in = st.text_input("구분", key="cat_field")
        title = st.text_input("제목")
        detail = st.text_area("상세")
        col_a, col_b = st.columns(2)
        with col_a:
            save = st.form_submit_button("저장", type="primary")
        with col_b:
            add_cat_btn = st.form_submit_button("구분만 목록에 추가")

    if save:
        c = (cat_in or "").strip()
        if not c or not (title or "").strip():
            st.error("구분과 제목을 입력하세요.")
        else:
            create_task(my_uid, task_day.isoformat(), c, title.strip(), detail or "")
            st.session_state.cat_quick = c
            st.success("저장했습니다. (캘린더에서 같은 날짜를 보면 표시됩니다.)")
            st.rerun()

    if add_cat_btn:
        c = (cat_in or "").strip()
        if c:
            upsert_category(c)
            st.session_state.cat_quick = c
            st.info("구분을 목록에 반영했습니다.")
            st.rerun()

    st.divider()
    st.subheader("팀 일정 (오늘)")
    tasks = tasks_for_date(today)
    if not tasks:
        st.info("등록된 업무가 없습니다.")
    else:
        by_name: dict[str, list] = defaultdict(list)
        for t in tasks:
            by_name[t["user_name"]].append(t)

        names = sorted(by_name.keys(), key=lambda x: x)
        st.caption("이름별 가로 열")
        cols = st.columns(len(names))
        for i, nm in enumerate(names):
            with cols[i]:
                st.markdown(f"**{nm}**")
                for t in by_name[nm]:
                    rolled = t.get("completed") and t.get("completed_type") == "rolled"
                    with st.container(border=True):
                        st.caption(display_category(t["category"]))
                        if rolled:
                            st.caption("이월됨 (히스토리)")
                        elif t.get("rolled_from_id") and not t.get("completed"):
                            st.caption("어제에서 이월")
                        if t.get("completed") and not rolled:
                            st.markdown(f"~~{t['title']}~~")
                        else:
                            st.markdown(f"**{t['title']}**")
                        if t.get("detail"):
                            st.caption(t["detail"])
                        if not rolled and t["user_id"] == my_uid:
                            b1, b2 = st.columns(2)
                            with b1:
                                if t["completed"]:
                                    if st.button("완료 취소", key=f"unc_{t['id']}"):
                                        update_task_complete(t["id"], False)
                                        st.rerun()
                                else:
                                    if st.button("완료", key=f"co_{t['id']}"):
                                        update_task_complete(t["id"], True)
                                        st.rerun()
                            with b2:
                                if st.button("삭제", key=f"rm_{t['id']}"):
                                    delete_task(t["id"])
                                    st.rerun()
                        elif not rolled:
                            st.caption("담당자만 수정")

    st.markdown("##### 오늘 메모")
    st.caption("팀 공용 메모입니다. 추가할 때마다 카드 색이 달라집니다. 삭제는 각 카드에서 할 수 있습니다.")

    def _memo_esc(s: str) -> str:
        return (
            (s or "")
            .replace("&", "&amp;")
            .replace("<", "&lt;")
            .replace(">", "&gt;")
            .replace('"', "&quot;")
            .replace("\n", "<br/>")
        )

    memos = list_daily_memos(today)
    for m in memos:
        bg = m.get("color_hex") or "#E3F2FD"
        mcol1, mcol2 = st.columns([5, 1])
        with mcol1:
            st.markdown(
                f"""<div style="background:{bg};color:#1a1a1a;padding:14px 16px;border-radius:12px;
margin-bottom:10px;font-size:1.02rem;line-height:1.55;word-break:break-word;
box-shadow:0 1px 4px rgba(0,0,0,.08);">{_memo_esc(m.get("body") or "")}</div>""",
                unsafe_allow_html=True,
            )
        with mcol2:
            if st.button("삭제", key=f"memo_del_{m['id']}", use_container_width=True):
                delete_daily_memo(m["id"])
                st.rerun()

    with st.form("daily_memo_form", clear_on_submit=True):
        memo_txt = st.text_area(
            "새 메모",
            placeholder="자유롭게 입력하세요.",
            height=120,
        )
        memo_add = st.form_submit_button("메모 추가", type="primary")
    if memo_add:
        try:
            create_daily_memo(today, memo_txt or "")
            st.rerun()
        except ValueError as e:
            st.error(str(e))

    csv_data = tasks_csv_for_date(today)
    st.download_button(
        "전체 CSV 다운로드",
        data=csv_data.encode("utf-8-sig"),
        file_name=f"team_tasks_{today}.csv",
        mime="text/csv",
    )


if __name__ == "__main__":
    main()
