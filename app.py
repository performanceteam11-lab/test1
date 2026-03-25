"""호환용 엔트리: `streamlit run app.py` → `10팀 TODO.py`와 동일 (사이드바에는 app으로 표시될 수 있음)."""
from __future__ import annotations

import runpy
from pathlib import Path

_root = Path(__file__).resolve().parent
runpy.run_path(str(_root / "10팀 TODO.py"), run_name="__main__")
