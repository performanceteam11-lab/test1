"""
마케팅 SQLite DB 기반 Streamlit 대시보드
실행: streamlit run app.py
"""
from __future__ import annotations

import hashlib
import sqlite3
import time
from pathlib import Path

import pandas as pd
import streamlit as st

BASE_DIR = Path(__file__).resolve().parent
DB_PATH = BASE_DIR / "marketing.db"

ADMIN_ID = "admin"
# SHA-256("admin1234")
PASSWORD_SHA256 = "ac9689e2272427085e35b9d3e3e8bed88cb3434828b43b86fc0596cad4c6e270"

MAX_FAILED = 3
LOCKOUT_SEC = 300


def _hash_pw(plain: str) -> str:
    return hashlib.sha256(plain.encode("utf-8")).hexdigest()


def _init_state() -> None:
    if "authenticated" not in st.session_state:
        st.session_state.authenticated = False
    if "failed_attempts" not in st.session_state:
        st.session_state.failed_attempts = 0
    if "lock_until" not in st.session_state:
        st.session_state.lock_until = 0.0


def _clear_lock_if_expired() -> None:
    if st.session_state.lock_until and time.time() >= st.session_state.lock_until:
        st.session_state.lock_until = 0.0
        st.session_state.failed_attempts = 0


def _locked_remaining_sec() -> float:
    _clear_lock_if_expired()
    if not st.session_state.lock_until:
        return 0.0
    return max(0.0, st.session_state.lock_until - time.time())


def _load_df() -> pd.DataFrame:
    if not DB_PATH.is_file():
        st.error(f"DB 파일을 찾을 수 없습니다: {DB_PATH}\nsetup_data.py를 먼저 실행하세요.")
        st.stop()
    conn = sqlite3.connect(DB_PATH)
    df = pd.read_sql_query("SELECT * FROM daily_report", conn)
    conn.close()
    df["date"] = pd.to_datetime(df["date"])
    return df


def _login_form() -> None:
    st.markdown("### 마케팅 대시보드 로그인")
    remaining = _locked_remaining_sec()
    if remaining > 0:
        mins = int(remaining // 60)
        secs = int(remaining % 60)
        st.warning(f"로그인이 {MAX_FAILED}회 이상 실패했습니다. {mins}분 {secs}초 후에 다시 시도하세요.")
        st.stop()

    with st.form("login_form"):
        uid = st.text_input("아이디")
        pw = st.text_input("비밀번호", type="password")
        submitted = st.form_submit_button("로그인")

    if submitted:
        if uid != ADMIN_ID:
            st.session_state.failed_attempts += 1
            if st.session_state.failed_attempts >= MAX_FAILED:
                st.session_state.lock_until = time.time() + LOCKOUT_SEC
                st.error("로그인에 실패했습니다. 5분간 시도가 제한됩니다.")
                st.rerun()
            st.error("아이디 또는 비밀번호가 올바르지 않습니다.")
            return

        if _hash_pw(pw) != PASSWORD_SHA256:
            st.session_state.failed_attempts += 1
            if st.session_state.failed_attempts >= MAX_FAILED:
                st.session_state.lock_until = time.time() + LOCKOUT_SEC
                st.error("로그인에 실패했습니다. 5분간 시도가 제한됩니다.")
                st.rerun()
            st.error("아이디 또는 비밀번호가 올바르지 않습니다.")
            return

        st.session_state.authenticated = True
        st.session_state.failed_attempts = 0
        st.session_state.lock_until = 0.0
        st.success("로그인되었습니다.")
        st.rerun()


def _kpi_row(df: pd.DataFrame) -> None:
    imp = int(df["impressions"].sum())
    clk = int(df["clicks"].sum())
    cost = int(df["cost"].sum())
    conv = int(df["conversions"].sum())
    rev = int(df["revenue"].sum())
    roas = rev / cost if cost else 0.0
    ctr = clk / imp if imp else 0.0
    cpc = cost / clk if clk else 0.0

    c1, c2, c3, c4, c5 = st.columns(5)
    c1.metric("노출", f"{imp:,}")
    c2.metric("클릭", f"{clk:,}")
    c3.metric("비용", f"{cost:,}원")
    c4.metric("매출", f"{rev:,}원")
    c5.metric("ROAS", f"{roas:.2f}")

    c6, c7 = st.columns(2)
    c6.metric("CTR", f"{ctr * 100:.2f}%")
    c7.metric("평균 CPC", f"{cpc:,.0f}원")


def _dashboard() -> None:
    df_all = _load_df()
    dmin = df_all["date"].min().date()
    dmax = df_all["date"].max().date()

    with st.sidebar:
        st.header("필터")
        dr = st.date_input(
            "기간",
            value=(dmin, dmax),
            min_value=dmin,
            max_value=dmax,
        )
        if isinstance(dr, tuple) and len(dr) == 2:
            date_from, date_to = dr
        else:
            date_from = date_to = dr

        channels = sorted(df_all["channel"].unique().tolist())
        sel_ch = st.multiselect("채널", options=channels, default=channels)

        sub = df_all[df_all["channel"].isin(sel_ch)] if sel_ch else df_all
        camp_opts = sorted(sub["campaign"].unique().tolist())
        sel_camp = st.multiselect("캠페인", options=camp_opts, default=camp_opts)

        st.divider()
        if st.button("로그아웃"):
            st.session_state.authenticated = False
            st.session_state.failed_attempts = 0
            st.session_state.lock_until = 0.0
            st.rerun()

    mask_date = (df_all["date"].dt.date >= date_from) & (df_all["date"].dt.date <= date_to)
    df = df_all.loc[mask_date].copy()
    df = df[df["channel"].isin(sel_ch)] if sel_ch else df
    df = df[df["campaign"].isin(sel_camp)] if sel_camp else df

    st.title("마케팅 성과 대시보드")
    st.caption("필터는 사이드바에서 조정할 수 있습니다.")

    if df.empty:
        st.info("선택한 조건에 맞는 데이터가 없습니다.")
        return

    _kpi_row(df)

    st.subheader("일별 비용·매출 추이")
    daily = df.groupby("date", as_index=False).agg({"cost": "sum", "revenue": "sum"})
    daily["날짜"] = daily["date"].dt.strftime("%Y-%m-%d")
    line_df = daily.set_index("날짜")[["cost", "revenue"]].rename(columns={"cost": "비용", "revenue": "매출"})
    st.line_chart(line_df)

    col_a, col_b = st.columns(2)
    with col_a:
        st.subheader("채널별 비용")
        ch_cost = df.groupby("channel")["cost"].sum().sort_values(ascending=False)
        st.bar_chart(ch_cost)
    with col_b:
        st.subheader("채널별 매출")
        ch_rev = df.groupby("channel")["revenue"].sum().sort_values(ascending=False)
        st.bar_chart(ch_rev)

    st.subheader("캠페인 상세")
    detail = (
        df.groupby(["channel", "campaign"], as_index=False)
        .agg(
            impressions=("impressions", "sum"),
            clicks=("clicks", "sum"),
            cost=("cost", "sum"),
            conversions=("conversions", "sum"),
            revenue=("revenue", "sum"),
        )
    )
    detail["ROAS"] = detail.apply(lambda r: r["revenue"] / r["cost"] if r["cost"] else 0, axis=1)
    detail = detail.sort_values("revenue", ascending=False)
    st.dataframe(
        detail,
        use_container_width=True,
        hide_index=True,
        column_config={
            "channel": "채널",
            "campaign": "캠페인",
            "impressions": st.column_config.NumberColumn("노출", format="%d"),
            "clicks": st.column_config.NumberColumn("클릭", format="%d"),
            "cost": st.column_config.NumberColumn("비용", format="%d"),
            "conversions": st.column_config.NumberColumn("전환", format="%d"),
            "revenue": st.column_config.NumberColumn("매출", format="%d"),
            "ROAS": st.column_config.NumberColumn("ROAS", format="%.2f"),
        },
    )


def main() -> None:
    st.set_page_config(
        page_title="마케팅 대시보드",
        layout="wide",
        initial_sidebar_state="expanded",
    )
    _init_state()

    if not st.session_state.authenticated:
        _login_form()
        return

    _dashboard()


if __name__ == "__main__":
    main()
