"""MyPy 타입 게이트 (mypy-baseline 연동, CI·로컬 pre-push 공용).

기존 919 오류를 baseline(`.mypy-baseline.txt`)으로 고정해 **신규 타입오류만 차단**하고
(출혈 정지), 기존 오류는 모듈별로 점진 소각한다. CI(Linux)와 로컬(Windows)이 **같은
단일 스크립트**를 호출하도록 하여 게이트 동작을 일치시킨다(DRY).

이식성 처리:
  - mypy 출력을 plain(--no-pretty 등)으로 강제해 mypy-baseline 이 파싱 가능하게 함.
  - 경로 구분자 백슬래시(Windows) -> 슬래시로 정규화 -> baseline 이 OS 간 일치.
  - UTF-8 강제로 Windows cp949 em-dash 크래시 회피.
sync/filter 가 동일 정규화를 거치므로 로컬 생성 baseline 이 CI 에서도 그대로 매칭된다.
"""

import os
import subprocess
import sys

# mypy 검사 대상(서비스 코드만; tests/aerich 는 config override 로 제외)
MYPY_TARGETS = ["app", "ai_worker"]

# 자식 프로세스 UTF-8 강제: Windows cp949 에서 mypy/mypy-baseline 의 유니코드(em-dash·
# 박스문자) 출력이 UnicodeEncodeError 로 크래시하는 것 방지(CI/Linux 는 이미 UTF-8, 무영향).
UTF8_ENV = {**os.environ, "PYTHONIOENCODING": "utf-8"}

# mypy-baseline 파서가 요구하는 plain 출력 강제 플래그(사람용 pretty 설정을 override)
MYPY_PLAIN_FLAGS = [
    "--no-pretty",
    "--hide-error-context",
    "--no-color-output",
    "--no-error-summary",
]

# baseline 파일 경로(점 파일로 고정)·정렬(git diff 안정). sync/filter 공통.
BASELINE_ARGS = ["--baseline-path", ".mypy-baseline.txt", "--sort-baseline"]


# ── mypy 실행 + 이식성 정규화 ───────────────────────────────────────────
# 흐름: mypy(plain·상대경로) 실행 -> stderr 통과 -> 경로 백슬래시를 슬래시로 치환
def run_mypy_normalized() -> str:
    # 실행파일은 uv 관리 venv 의 PATH 로 해석(부분경로 의도적) -> S607 예외
    proc = subprocess.run(
        ["mypy", *MYPY_TARGETS, *MYPY_PLAIN_FLAGS],  # noqa: S607
        capture_output=True,
        text=True,
        encoding="utf-8",
        env=UTF8_ENV,
        check=False,
    )
    if proc.stderr:
        sys.stderr.write(proc.stderr)
    # OS 간 baseline 일치를 위해 경로 구분자 정규화(sync/filter 동일 적용 -> 자기정합)
    return proc.stdout.replace("\\", "/")


# ── 게이트 본문 ────────────────────────────────────────────────────────
# 흐름: 인자(sync|filter, 기본 filter) -> mypy 정규화 출력 -> mypy-baseline 전달
#       -> filter 는 신규 오류 있으면 non-zero 로 커밋/CI 차단
def main() -> int:
    subcommand = sys.argv[1] if len(sys.argv) > 1 else "filter"
    normalized = run_mypy_normalized()
    result = subprocess.run(
        ["mypy-baseline", subcommand, *BASELINE_ARGS],  # noqa: S607
        input=normalized,
        text=True,
        encoding="utf-8",
        env=UTF8_ENV,
        check=False,
    )
    return result.returncode


if __name__ == "__main__":
    sys.exit(main())
