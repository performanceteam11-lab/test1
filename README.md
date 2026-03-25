# team-todo-streamlit

Streamlit 기반 **10팀 TODO** · **샤크닌자 캘린더** (팀 할 일, 프로모션, 구글 시트 연동).

## 실행

```bash
pip install -r requirements.txt
streamlit run "10팀 TODO.py"
```

또는:

```bash
streamlit run app.py
```

## 구성

- `10팀 TODO.py` — 오늘의 할 일, 팀 일정, 오늘 메모
- `pages/2_샤크닌자_캘린더.py` — 캘린더, 프로모션, 시트 동기화
- `data/` — 로컬 SQLite (`team.db`, `.gitignore`로 저장소에 포함하지 않음)

## 데이터

`data/team.db`는 기본적으로 Git에 올라가지 않습니다. 새 클론 후 앱 실행 시 시드가 생성됩니다.
