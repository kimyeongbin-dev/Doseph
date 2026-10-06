"""도구 설정이 조용히 되돌아가는 것을 막는다 — `QA-63`.

왜 테스트인가
-------------
설정 한 줄이 사라지면 **아무것도 빨개지지 않는다.** `force-exclude` 가 없으면
`ruff format .` 은 여전히 초록이고, **`pre-commit` 만** 제외 대상을 고친다 —
즉 *«설정은 제외인데 훅은 고친다»* 로 되돌아가는데 **신호가 없다.**
"""

from pathlib import Path
import tomllib

PYPROJECT = Path(__file__).resolve().parents[2] / "pyproject.toml"


# ── ruff 가 「명시적으로 넘긴 파일」에도 exclude 를 적용하는가 ────────
def test_ruff_force_exclude_is_on() -> None:
  """🔴 `pre-commit` 은 파일 목록을 **인자로** 넘긴다.

  ruff 는 기본적으로 인자로 받은 파일에 `exclude` 를 적용하지 않으므로, 이 설정이 없으면
  설정이 제외한 파일을 훅이 고친다. 실측(2026-10-06): 마이그레이션 4개가 그렇게
  4칸 → 2칸으로 바뀌었다(`QA-63` · `D80`).
  """
  cfg = tomllib.loads(PYPROJECT.read_text(encoding="utf-8"))
  ruff = cfg["tool"]["ruff"]
  assert ruff.get("force-exclude") is True, (
    "ruff 의 force-exclude 가 꺼졌다 — pre-commit 이 exclude 대상을 고치게 된다(QA-63)"
  )


def test_generated_migrations_stay_excluded() -> None:
  """마이그레이션은 `aerich` 생성물이라 제외가 **의도**다.

  고쳐도 다음 `migrate` 가 되돌리므로 매번 다시 어긋난다.
  """
  cfg = tomllib.loads(PYPROJECT.read_text(encoding="utf-8"))
  assert "app/db/migrations" in cfg["tool"]["ruff"]["exclude"]
