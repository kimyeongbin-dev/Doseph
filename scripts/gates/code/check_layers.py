"""레이어 계약 게이트 (import-linter 연동, CI·로컬 pre-push 공용).

계약 정본은 `pyproject.toml` 의 `[tool.importlinter]` 에 있다. 이 스크립트는
그 계약을 **어느 OS 에서든 같은 방식으로 돌리기 위한 얇은 실행기**다.
CI(Linux)와 로컬(Windows)이 같은 단일 스크립트를 호출한다(DRY — mypy_gate.py 와 같은 이유).

🔴 **fail-closed 인 이유** (2026-09-20 보강)
  `lint-imports` 는 계약이 **하나도 없어도** ``Contracts: 0 kept, 0 broken.`` 을 찍고 **exit 0** 이다.
  `pyproject.toml` 의 ``[[tool.importlinter.contracts]]`` 가 지워지거나 섹션 이름이 바뀌면
  **게이트가 아무것도 검사하지 않은 채 초록**이 된다 — ``check_utf8_guard`` 가 11건 → 1건이 되고도
  통과한 것과 같은 실패다(대장 **D31**). 그래서 **출력을 읽어 계약 수를 세고 바닥값**을 건다.

✅ **음성 대조 표본** — 이것들은 **통과해야** 한다:
  - 허용 예외(``ignore_imports``)에 걸리는 import (예: ``app.apis.v1.* -> app.models.accounts``)
  - 정상 경로 ``라우터 → 서비스 → 저장소`` (``forbidden`` + ``allow_indirect_imports``)
  전부 BROKEN 만 확인하면 *"계약이 아무거나 다 실패시키는"* 상태와 구분되지 않는다.

⚠️ **숫자는 도구가 말하게 둔다.** 계약의 예외 수를 우리가 다시 세지 않는다 —
  ``ignore_imports`` 는 *패턴*이고 도구가 보고하는 것은 *해석된 import 수*라, 둘을 섞으면
  정직한 두 계측이 서로를 거짓이라 부른다(대장 **D43**).

이식성 처리:
  - `PYTHONPATH` 에 저장소 루트를 넣는다. `lint-imports` 는 콘솔 스크립트라
    sys.path 에 cwd 가 없어, 그대로 두면 grimp 이 `app` 패키지를 못 찾는다.
  - UTF-8 강제로 Windows cp949 크래시 회피. 계약 이름이 한글·em-dash 라
    강제하지 않으면 **계약은 통과했는데 출력에서 터져 non-zero** 가 된다
    (거짓 빨강 — 실제로 결핍 주입 검증 중에 이 함정을 밟았다).
"""

import os
import re
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

#: 바닥값 — 계약이 조용히 사라지는 것을 막는다. *0건*만이 아니라 **줄어든 것도 실패**다(D31).
#: 이 값은 **손으로 올린다** — 계약을 늘리면 그때 올리는 것이 의식적인 결정이 된다.
MIN_CONTRACTS = 6

#: `lint-imports` 의 마지막 요약 줄. 이 줄이 없으면 **무엇을 셌는지 알 수 없다** → 실패.
SUMMARY = re.compile(r"Contracts:\s*(\d+)\s*kept,\s*(\d+)\s*broken", re.IGNORECASE)


# ── 레이어 계약 게이트 본문 ─────────────────────────────────────────────
# 흐름: PYTHONPATH·인코딩 고정 -> lint-imports 실행(pyproject 의 계약 읽음)
#       -> 도구 출력 그대로 전달 -> 요약 줄 파싱 -> 계약 수 바닥값 검사
#       -> 위반이 있거나 계약이 줄었으면 non-zero 로 push/CI 차단
def main() -> int:
    """pre-push · CI 진입점.

    Returns:
        계약이 전부 KEPT 이고 계약 수가 바닥값 이상이면 0, 그 외 1(또는 도구의 종료코드).
    """
    # 실행파일은 uv 관리 venv 의 PATH 로 해석(부분경로 의도적) -> S607 예외
    result = subprocess.run(
        ["lint-imports", "--no-logo", *sys.argv[1:]],  # noqa: S607
        cwd=REPO_ROOT,
        env=GATE_ENV,
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    # 도구의 출력은 그대로 넘긴다 — 계약 이름·위반 내역이 거기 있다(우리가 다시 세지 않는다, D43).
    print(result.stdout, end="")
    if result.stderr:
        print(result.stderr, end="", file=sys.stderr)

    if result.returncode != 0:
        return result.returncode

    matched = SUMMARY.search(result.stdout)
    if not matched:
        print("[거부] `lint-imports` 의 요약 줄(`Contracts: N kept, M broken`)을 찾지 못했다.", file=sys.stderr)
        print("  무엇을 검사했는지 알 수 없으므로 통과시키지 않는다(fail-closed).", file=sys.stderr)
        return 1

    kept = int(matched.group(1))
    if kept < MIN_CONTRACTS:
        print(f"[거부] 계약이 {kept}건뿐이다 (기대 최소 {MIN_CONTRACTS}건).", file=sys.stderr)
        print(
            "  `pyproject.toml` 의 `[[tool.importlinter.contracts]]` 가 지워졌거나 섹션명이 바뀌었다.", file=sys.stderr
        )
        print("  0건이어도 `lint-imports` 는 exit 0 이다 — 줄어든 것도 실패다(D31).", file=sys.stderr)
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
