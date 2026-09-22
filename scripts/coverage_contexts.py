"""coverage dynamic context 수집·조회 (줄 ↔ 그 줄을 실행한 테스트).

**무엇을 위한 것인가**: *"이 줄을 고치면 어떤 테스트가 반응하는가"* 를 추측이 아니라
**실행 기록**으로 답한다. import 그래프(`scripts/check_layers.py`)가 정적으로 못 보는
DI·`getattr`·문자열 참조 경로를 이쪽이 덮는다 — 정적·동적을 둘 다 쓰는 이유다.

⚠️ **이 스크립트는 게이트가 아니다.** 커버리지는 *"실행됐나"* 를 말할 뿐 *"틀리면 빨개지나"* 를
말하지 않는다. 여기서 하는 *context 조회*는 로컬에서 필요할 때 돌린다.

🔄 **2026-09-21(B-8 S3) 정정**: 커버리지 자체는 **게이트가 됐다** —
`scripts/gates/code/check_coverage_baseline.py` 가 CI 에서 파일별 미커버 증가를 막는다.
다만 그쪽도 위 한계는 그대로 안고 있고(한계 선언이 그 모듈 docstring 에 있다),
여기의 `dynamic_context` 수집은 **그 게이트와 별개**다.

⚠️ **수집은 Docker 안에서 한다.** 테스트가 진짜 PostgreSQL 을 필요로 하기 때문이다.
`relative_files = true` 라서 컨테이너(`/app`)에서 만든 데이터 파일을 호스트(Windows)에서
그대로 읽을 수 있다 — 저장되는 경로가 `app/services/x.py` 같은 상대경로다.
"""

import argparse
from collections import defaultdict
import os
from pathlib import Path
import subprocess
import sys

from coverage import CoverageData

REPO_ROOT = Path(__file__).resolve().parents[1]
DATA_FILE = REPO_ROOT / ".coverage"

# 자기 출력 인코딩을 UTF-8 로 고정한다. 이 스크립트는 한글·이모지를 찍는데,
# Windows 콘솔(cp949)에서 돌면 **본래 하려던 일은 다 끝난 뒤 출력 단계에서**
# UnicodeEncodeError 로 죽는다 — 성공을 실패로 보이게 만드는 종류의 실패다.
# 자식 프로세스는 UTF8_ENV 가, 자기 자신은 이 두 줄이 책임진다(대장 D36).
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.stderr.reconfigure(encoding="utf-8", errors="replace")

# 수집 대상. DB 층을 **별도 스텝으로** 돌리는 이유는 CI 와 같다 — pytest 는 수집 0건이면
# exit 5 로 실패하므로, 한 층이 통째로 안 돌면 조용히 지나가지 않는다.
SUITES = [
    ["pytest", "app", "-m", "not db", "-q"],
    ["pytest", "app", "-m", "db", "-q"],
    ["pytest", "tests", "-q"],
]

SERVICE = "fastapi"
# 컨테이너 안의 작업 디렉터리. 저장소 루트는 **마운트돼 있지 않아서**(app·ai_worker·
# scripts·tests·pyproject.toml 만 마운트) 여기서 만든 데이터 파일은 호스트에 안 나온다.
# 그래서 수집이 끝나면 명시적으로 복사해 온다.
CONTAINER_DATA_FILE = "/app/.coverage"

UTF8_ENV = {**os.environ, "PYTHONIOENCODING": "utf-8"}


def _docker(*args: str) -> list[str]:
    return ["docker", "compose", "exec", "-T", SERVICE, *args]


# ── 수집 ────────────────────────────────────────────────────────────────
# 흐름: 컨테이너의 기존 데이터 삭제 -> 스위트별 coverage run(--append)
#       -> .coverage 를 호스트로 복사
# 한 스위트라도 빨가면 즉시 중단한다 — 부분 수집 데이터는 없는 것보다 위험하다
# ("이 줄은 아무 테스트도 안 덮는다"가 거짓이 된다).
# ⚠️ 반드시 Docker 안에서 돈다. DB 층 테스트가 진짜 PostgreSQL 을 요구하기 때문이다.
def collect() -> int:
    """전체 스위트를 순서대로 돌려 커버리지 컨텍스트를 모은다."""
    subprocess.run(_docker("rm", "-f", CONTAINER_DATA_FILE), check=False)
    for index, suite in enumerate(SUITES):
        append = ["--append"] if index else []
        print(f"\n=== [{index + 1}/{len(SUITES)}] {' '.join(suite)} ===", flush=True)
        result = subprocess.run(
            _docker("uv", "run", "--no-sync", "coverage", "run", *append, "-m", *suite),
            cwd=REPO_ROOT,
            env=UTF8_ENV,
            check=False,
        )
        if result.returncode != 0:
            print(f"\n실패: {' '.join(suite)} (exit {result.returncode}) — 수집을 중단한다")
            return result.returncode

    print("\n=== 데이터 파일을 호스트로 복사 ===", flush=True)
    copied = subprocess.run(
        ["docker", "compose", "cp", f"{SERVICE}:{CONTAINER_DATA_FILE}", str(DATA_FILE)],  # noqa: S607
        cwd=REPO_ROOT,
        env=UTF8_ENV,
        check=False,
    )
    if copied.returncode != 0:
        print("복사 실패 — 컨테이너 안에는 데이터가 있으나 호스트에서 조회할 수 없다")
        return copied.returncode
    print(f"완료: {DATA_FILE}")
    return 0


# ── 신선도 검사 ─────────────────────────────────────────────────────────
# 흐름: .coverage 의 mtime 과 추적 중인 .py 최신 mtime 비교 -> 오래됐으면 경고
# 실패시키지 않는다. 오래된 데이터는 "없음"보다 위험하지만, 판단은 사람이 한다.
def warn_if_stale() -> bool:
    """수집 데이터가 없거나 낡았으면 경고하고 False 를 돌려준다."""
    if not DATA_FILE.exists():
        print(f"⚠️  {DATA_FILE.name} 이 없다. 먼저 `collect` 를 돌려라 (Docker 안에서).")
        return False
    data_mtime = DATA_FILE.stat().st_mtime
    newest = 0.0
    newest_path = ""
    for source_dir in ("app", "ai_worker"):
        for py in (REPO_ROOT / source_dir).rglob("*.py"):
            mtime = py.stat().st_mtime
            if mtime > newest:
                # 경로 구분자 정규화 — 데이터 파일이 상대경로(슬래시)로 말하므로 출력도 맞춘다
                newest, newest_path = mtime, py.relative_to(REPO_ROOT).as_posix()
    if newest > data_mtime:
        print(f"⚠️  커버리지 데이터가 코드보다 오래됐다 — {newest_path} 가 더 새롭다.")
        print("    지금 보는 '줄 ↔ 테스트' 는 과거의 사실이다. `collect` 를 다시 돌려라.")
    else:
        # 침묵은 "검사했는데 문제없음"과 "검사가 안 돌았음"을 구분하지 못한다. 말한다.
        print(f"✅ 커버리지 데이터가 코드보다 새롭다 (기준: {newest_path}).")
    return True


# ── 조회: 파일의 줄 ↔ 그 줄을 실행한 테스트 ─────────────────────────────
# 흐름: CoverageData 로드 -> measured_files 에서 대상 찾기 -> contexts_by_lineno
#       -> 테스트별로 줄을 묶어 출력 (context 가 빈 줄 = 덮는 테스트 0건)
def contexts_for(path: str) -> dict[int, list[str]]:
    """한 파일의 줄별 커버리지 컨텍스트를 모아 돌려준다."""
    data = CoverageData(basename=str(DATA_FILE))
    data.read()
    target = path.replace("\\", "/")
    for measured in data.measured_files():
        if measured.replace("\\", "/").endswith(target):
            raw = data.contexts_by_lineno(measured)
            # context 는 "app/tests/test_x.py::test_name|run" 형태. 빈 문자열은 컨텍스트
            # 없이 실행된 것(import 시점 등)이라 테스트로 세지 않는다.
            return {line: sorted(c for c in ctxs if c) for line, ctxs in sorted(raw.items())}
    return {}


def show(path: str, line: int | None, by_line: bool) -> int:
    """한 파일(또는 한 줄)의 컨텍스트를 사람이 읽을 형태로 인쇄한다."""
    if not warn_if_stale():
        return 1
    mapping = contexts_for(path)
    if not mapping:
        print(f"'{path}' 에 대한 측정 기록이 없다 (파일명 오타이거나, 수집 대상이 아니거나, 아무 테스트도 안 덮는다).")
        return 1

    if by_line:
        print(f"{path} — 줄별 (측정된 줄 {len(mapping)})")
        for lineno, tests in mapping.items():
            label = f"{len(tests)}건" if tests else "0건 ⚠️"
            first = tests[0] if tests else "(테스트 컨텍스트 없이 실행 — import 시점 등)"
            print(f"  L{lineno:<5} {label:>7}  {first}")
        return 0

    if line is not None:
        tests = mapping.get(line, [])
        print(f"{path}:{line} 를 실행한 테스트 {len(tests)}건")
        for test in tests:
            print(f"  - {test}")
        return 0

    by_test: dict[str, list[int]] = defaultdict(list)
    uncovered_context = 0
    for lineno, tests in mapping.items():
        if not tests:
            uncovered_context += 1
        for test in tests:
            by_test[test].append(lineno)

    print(f"{path} — 측정된 줄 {len(mapping)} · 덮는 테스트 {len(by_test)}건")
    for test, lines in sorted(by_test.items(), key=lambda kv: (-len(kv[1]), kv[0])):
        print(f"  {len(lines):>4}줄  {test}")
    if uncovered_context:
        print(f"  ⚠️  {uncovered_context}줄은 **테스트 컨텍스트 없이** 실행됐다(import 시점 등).")
    return 0


# ── CLI ─────────────────────────────────────────────────────────────────
# 흐름: 인자 파싱 -> collect | show | check 분기
def main() -> int:
    """CLI 진입점 — collect / show 서브커맨드를 가른다."""
    parser = argparse.ArgumentParser(description="coverage dynamic context 수집·조회")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("collect", help="전체 스위트를 돌려 컨텍스트를 수집한다 (Docker 안에서)")
    sub.add_parser("check", help="수집된 데이터가 코드보다 오래됐는지 본다")
    show_parser = sub.add_parser("show", help="파일의 줄 ↔ 테스트 매핑을 본다")
    show_parser.add_argument("path")
    show_parser.add_argument("--line", type=int, default=None)
    show_parser.add_argument("--by-line", action="store_true", help="테스트별이 아니라 줄별로 본다")

    args = parser.parse_args()
    if args.command == "collect":
        return collect()
    if args.command == "check":
        return 0 if warn_if_stale() else 1
    return show(args.path, args.line, args.by_line)


if __name__ == "__main__":
    sys.exit(main())
