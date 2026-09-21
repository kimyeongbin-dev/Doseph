"""커버리지 baseline 게이트 — **기존 파일의 미커버가 늘면 막는다** (B-8 S3 · QA-11).

왜 baseline 방식인가
--------------------
총량 임계치(``fail_under=80``)는 두 가지로 실패한다 — 넘기면 **아무도 안 보고**,
못 넘기면 **한 번에 못 넘어서** 사람이 꺼 버린다. 이 저장소는 이미 같은 문제를
MyPy 에서 **baseline(신규만 차단)** 으로 풀었고(`scripts/mypy_gate.py`), 그 방식이
마찰 없이 돌고 있다. 여기서는 **새 설계를 하지 않고 그 철학만 이식**한다.

*"새 오류"* 의 커버리지 대응물은 **«덮여 있던 줄이 안 덮이게 된 것»** 이다.
그래서 파일별 미커버 줄 수를 baseline 에 박아 두고 **늘어나면 막는다.**

🔴 이 게이트가 **못 하는 것** (한계 선언 — 안 적으면 초록이 과잉 해석된다)
-------------------------------------------------------------------------
- **커버리지는 «실행됐나» 지 «틀리면 빨개지나» 가 아니다.** 단언 없는 테스트도
  커버리지는 100% 를 만든다. 이 게이트의 쓸모는 품질 측정이 아니라
  **V-H(도달 불가 분기) 탐지**다 — 죽은 분기는 커버리지 0 으로 드러난다
  (`study/2026-09-15_vacuous-green-detection-study.md` §4).
- **새 파일이 통째로 미검증인 것은 막지 못한다.** baseline 에 없는 파일은
  🟡 보고만 한다. 막으면 새 모듈을 만들 때마다 걸려 사람이 ``sync`` 를
  반사적으로 돌리게 되고, 그러면 게이트가 **통과 기계**가 된다(D46 의 오탐 경고).
  대신 **보고에는 반드시 인쇄**해서 사람이 보게 한다.
- **분기(branch) 커버리지가 아니라 줄(line) 커버리지다.** ``branch = true`` 를 켜면
  baseline 이 통째로 바뀌므로 그건 별도 결정이다.

사용
----
    uv run python -m scripts.gates.code.check_coverage_baseline          # 검사
    uv run python -m scripts.gates.code.check_coverage_baseline sync     # baseline 갱신

``coverage json`` 리포트를 입력으로 받는다(기본 ``coverage.json``).
"""

import json
from pathlib import Path
import sys

# Windows 콘솔 기본 코드페이지(cp949)에서 한글 출력이 깨지거나 죽지 않도록 고정한다.
# 🔴 stdout 과 stderr 는 **서로를 보호하지 않는다** — 한쪽만 고정하면 다른 쪽이 크래시한다(대장 D36).
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

# stdout/stderr 방어가 import 보다 먼저여야 한다 — cp949 크래시 방지(대장 D36).
from scripts.gates._root import REPO_ROOT

BASELINE_PATH = REPO_ROOT / ".coverage-baseline.json"
DEFAULT_REPORT = REPO_ROOT / "coverage.json"

#: 측정 대상 접두사. 여기 밖(테스트·마이그레이션 등)은 baseline 에 넣지 않는다.
MEASURED_PREFIXES = ("app/", "ai_worker/")
#: 제외 — 테스트 자신과 자동 생성물은 커버리지 판정 대상이 아니다.
EXCLUDED_PARTS = ("/tests/", "/migrations/", "/__pycache__/")

#: 🔴 바닥값 = **측정된 파일 수**. 이 아래로 떨어지면 *"미커버가 안 늘었다"* 가 아니라
#: *"대상이 사라졌다"* 이다. `check_utf8_guard` 가 11건 → 1건이 되고도 초록이었던
#: 실패(대장 **D31**)를 여기서 되풀이하지 않기 위한 장치다.
#: ⚠️ 손으로 올린다. `sync` 가 값을 인쇄하므로 그때 같이 본다.
#:
#: 🔑 **이 값은 실측이다. 어림잡지 않는다** — 처음에 `150` 이라고 넣었더니 실제가 **148** 이라
#: 게이트가 자기 첫 실행에서 자기를 막았다. 바닥값은 *"이쯤 되겠지"* 가 아니라
#: **지금 세어지는 수**여야 한다(그래야 줄어든 것이 실패로 보인다).
MIN_MEASURED_FILES = 148


# ── coverage json 리포트 읽기 ──────────────────────────────────────────
# 흐름: 파일 존재 확인 -> JSON 파싱 -> 측정 대상만 추려 {경로: 미커버 줄수}
def is_measured(path: str) -> bool:
    """``app/``·``ai_worker/`` 의 비-테스트 소스인가."""
    if not path.startswith(MEASURED_PREFIXES):
        return False
    return not any(part in path for part in EXCLUDED_PARTS)


def load_report(report_path: Path) -> dict[str, int]:
    """``coverage json`` 리포트에서 ``{경로: 미커버 줄수}`` 를 뽑는다.

    Args:
        report_path: ``coverage json -o`` 가 만든 리포트 경로.

    Returns:
        측정 대상 파일별 미커버 줄 수.

    Raises:
        SystemExit: 리포트가 없거나 파싱 불가일 때 (fail-closed).
    """
    if not report_path.is_file():
        print(f"\n[거부] 커버리지 리포트가 없다 — {report_path}", file=sys.stderr)
        print("  먼저 `coverage run` 후 `coverage json -o coverage.json` 을 돌린다.", file=sys.stderr)
        print("  리포트 부재를 통과시키면 **측정하지 않은 것이 초록**이 된다(fail-closed).\n", file=sys.stderr)
        raise SystemExit(1)

    try:
        payload = json.loads(report_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        print(f"\n[거부] 커버리지 리포트를 읽지 못했다 — {exc}\n", file=sys.stderr)
        raise SystemExit(1) from exc

    files = payload.get("files")
    if not isinstance(files, dict):
        print("\n[거부] 리포트에 `files` 가 없다 — coverage 출력 형식이 바뀌었다(fail-closed).\n", file=sys.stderr)
        raise SystemExit(1)

    measured: dict[str, int] = {}
    for raw_path, entry in files.items():
        normalized = raw_path.replace("\\", "/")
        if not is_measured(normalized):
            continue
        measured[normalized] = int(entry["summary"]["missing_lines"])
    return measured


# ── baseline 대조 ──────────────────────────────────────────────────────
# 흐름: 바닥값 확인 -> 사라진 파일 탐지 -> 미커버 증가 탐지 -> 새 파일 보고
def compare(current: dict[str, int], baseline: dict[str, int]) -> tuple[list[str], list[str], list[str]]:
    """(미커버가 는 파일, 측정에서 사라진 파일, baseline 에 없는 새 파일)."""
    worsened = [
        f"{path}: 미커버 {baseline[path]} -> {current[path]} (+{current[path] - baseline[path]})"
        for path in sorted(current)
        if path in baseline and current[path] > baseline[path]
    ]
    # 🔴 baseline 에 있는데 리포트에 없다 = 그 파일이 **측정에서 빠졌다.**
    #    파일을 지웠으면 `sync` 로 내려야 하고, 안 지웠다면 검사 범위가 조용히 줄어든 것이다.
    vanished = sorted(set(baseline) - set(current))
    appeared = sorted(set(current) - set(baseline))
    return worsened, vanished, appeared


def main() -> int:
    """게이트 진입점.

    Returns:
        위반이 없으면 0, 있으면 1.
    """
    argv = sys.argv[1:]
    subcommand = argv[0] if argv and not argv[0].startswith("-") else "check"
    report_path = Path(argv[1]) if len(argv) > 1 else DEFAULT_REPORT

    current = load_report(report_path)

    if len(current) < MIN_MEASURED_FILES:
        print(
            f"\n[거부] 측정된 파일이 {len(current)}개뿐이다 (기대 최소 {MIN_MEASURED_FILES}개).",
            file=sys.stderr,
        )
        print("  테스트가 통째로 안 돌았거나 경로 규약이 바뀌었다.", file=sys.stderr)
        print("  적은 대상은 '미커버가 안 늘었다' 가 아니라 '아무것도 못 봤다' 이다(fail-closed).\n", file=sys.stderr)
        return 1

    if subcommand == "sync":
        BASELINE_PATH.write_text(
            json.dumps(current, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        total_missing = sum(current.values())
        print(f"✅ baseline 갱신 — 파일 {len(current)}개 · 미커버 합계 {total_missing}줄 -> {BASELINE_PATH.name}")
        print(f"   MIN_MEASURED_FILES 는 지금 {MIN_MEASURED_FILES} 다. 파일 수가 크게 늘었으면 같이 올린다.")
        return 0

    if not BASELINE_PATH.is_file():
        print(f"\n[거부] baseline 이 없다 — {BASELINE_PATH.name}", file=sys.stderr)
        print("  `... check_coverage_baseline sync` 로 만든 뒤 커밋한다(fail-closed).\n", file=sys.stderr)
        return 1

    baseline: dict[str, int] = json.loads(BASELINE_PATH.read_text(encoding="utf-8"))
    worsened, vanished, appeared = compare(current, baseline)

    if worsened or vanished:
        print("\n[거부] 커버리지가 뒷걸음쳤다\n", file=sys.stderr)
        for line in worsened:
            print(f"  ▼ {line}", file=sys.stderr)
        for path in vanished:
            print(f"  ✂ {path}: baseline 에 있는데 **측정에서 빠졌다**", file=sys.stderr)
        print(
            "\n  덮여 있던 줄이 안 덮이게 됐다면 테스트를 함께 옮기거나 고친다."
            "\n  의도한 변화라면 `... check_coverage_baseline sync` 로 baseline 을 내리고"
            "\n  **이유를 커밋 메시지에** 적는다.\n",
            file=sys.stderr,
        )
        return 1

    # 침묵은 *"문제없음"* 과 *"안 돌았음"* 을 구분하지 못한다. 통과할 때도 **센 것**을 남긴다.
    total_missing = sum(current.values())
    improved = sum(1 for p in current if p in baseline and current[p] < baseline[p])
    print(
        f"✅ 커버리지 baseline — 측정 {len(current)}파일 · 미커버 {total_missing}줄 · "
        f"악화 0 · 사라진 파일 0 · 개선 {improved}파일."
    )
    if appeared:
        # 🟡 보고. 차단하지 않는 이유는 모듈 docstring 의 «못 하는 것» 참조.
        print(f"   🟡 baseline 에 없는 새 파일 {len(appeared)}개 (통째 미검증이어도 막지 않는다):")
        for path in appeared[:8]:
            print(f"      - {path} (미커버 {current[path]}줄)")
        if len(appeared) > 8:
            print(f"      … 외 {len(appeared) - 8}개")
    return 0


if __name__ == "__main__":
    sys.exit(main())
