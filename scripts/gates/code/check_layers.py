"""레이어 계약 게이트 (import-linter 연동, CI·로컬 pre-push 공용).

계약 정본은 `pyproject.toml` 의 `[tool.importlinter]` 에 있다. 이 스크립트는
그 계약을 **어느 OS 에서든 같은 방식으로 돌리기 위한 얇은 실행기**다.
CI(Linux)와 로컬(Windows)이 같은 단일 스크립트를 호출한다(DRY — mypy_gate.py 와 같은 이유).

이식성 처리:
  - `PYTHONPATH` 에 저장소 루트를 넣는다. `lint-imports` 는 콘솔 스크립트라
    sys.path 에 cwd 가 없어, 그대로 두면 grimp 이 `app` 패키지를 못 찾는다.
  - UTF-8 강제로 Windows cp949 크래시 회피. 계약 이름이 한글·em-dash 라
    강제하지 않으면 **계약은 통과했는데 출력에서 터져 non-zero** 가 된다
    (거짓 빨강 — 실제로 결핍 주입 검증 중에 이 함정을 밟았다).
"""

import os
import subprocess
import sys

# Windows 콘솔 기본 코드페이지(cp949)에서 한글 출력이 깨지거나 죽지 않도록 고정한다.
# 🔴 stdout 과 stderr 는 **서로를 보호하지 않는다** — 한쪽만 고정하면 다른 쪽이 크래시한다(대장 D36).
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

# stdout/stderr 방어가 import 보다 먼저여야 한다 — cp949 크래시 방지(대장 D36).
from scripts.gates._root import REPO_ROOT

# 자식 프로세스 환경: 저장소 루트를 import 경로에 얹고 출력 인코딩을 UTF-8 로 고정.
# (CI/Linux 는 이미 UTF-8 이라 무영향)
GATE_ENV = {
    **os.environ,
    "PYTHONIOENCODING": "utf-8",
    "PYTHONPATH": os.pathsep.join(
        [str(REPO_ROOT), *([os.environ["PYTHONPATH"]] if os.environ.get("PYTHONPATH") else [])],
    ),
}


# ── 레이어 계약 게이트 본문 ─────────────────────────────────────────────
# 흐름: PYTHONPATH·인코딩 고정 -> lint-imports 실행(pyproject 의 계약 읽음)
#       -> 위반이 있으면 non-zero 로 push/CI 차단
def main() -> int:
    # 실행파일은 uv 관리 venv 의 PATH 로 해석(부분경로 의도적) -> S607 예외
    result = subprocess.run(
        ["lint-imports", "--no-logo", *sys.argv[1:]],  # noqa: S607
        cwd=REPO_ROOT,
        env=GATE_ENV,
        check=False,
    )
    return result.returncode


if __name__ == "__main__":
    sys.exit(main())
