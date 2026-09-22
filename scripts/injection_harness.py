"""결핍 주입 **하네스** — 측정기가 조용히 죽는 것을 막는다.

왜 이 모듈이 있나
-----------------
`D52` 는 *"세기 전에 기대 범위를 먼저 말한다"* 고 한다. 그건 **탐지기**다 —
매번 **틀린 뒤에** 걸린다. 2026-09-22 한 세션에서만 측정기가 **8번** 틀렸고,
D52 는 8번 다 잡았지만 **한 번도 예방하지 못했다.**

원인을 묶으면 셋이다::

    A. 셸 파이프라인에서 실패가 침묵한다
       (`--ignore ""` 가 에러인데 `2>/dev/null` 이 숨기고, 빈 값이 0 으로 인쇄됐다.
        `bc` 부재로 printf 인자가 밀려 "363%" 가 나왔다.)
    B. 구조를 문자열로 센다 — D47 이 이미 말하는 것
    C. 🔴 주입 표본이 «검사 구역 밖» 에 있었다  ← 이름이 없던 실패

**C 가 이 모듈이 막으려는 것이다.** 두 번 났다:

- `BLE001` 주입이 0 → 표식을 `scripts/` 에 뒀는데 그 경로는 **`per-file-ignores` 로
  그 규칙이 면제**돼 있었다.
- `D101/102/103` 주입이 0/3 → 표식을 `_probe.py` 로 만들었는데 **밑줄로 시작하는
  모듈은 «비공개»** 라 `D1xx` 가 보지 않는다.

둘 다 **규칙도 코드도 멀쩡했다.** 내 표본이 검사 대상이 아니었을 뿐이다.
그리고 *"안 뜬다"* 는 **«규칙이 죽었다»** 와 **«표본이 사각지대다»** 를 구분해 주지 않는다 —
**둘 다 침묵으로 나타난다.**

무엇을 더하나 — 단계 ⓪
-----------------------
기존 절차는 두 단계였다::

    ① 음성 대조   정상 표본 → 통과해야 정상
    ② 결핍 주입   결함 표본 → Red 여야 정상

여기에 **앞단계**를 붙인다::

    ⓪ 하네스 살아있음   «이 자리»에 **확실한 위반**을 넣으면 뜨는가

⓪이 초록이어야 ②의 침묵을 *"규칙이 안 잡는다"* 로 읽을 수 있다.
⓪ 없이 ②만 보면 **사각지대를 게이트 결함으로 오진**한다(실제로 두 번 그랬다).

🔑 그리고 표본 위치 규약: **«고장난 곳에 표식을 둔다»** —
실제 위반이 관측된 **그 디렉터리**에 주입한다. 그러면 면제 구역·명명 규칙이
**자동으로 같아진다.** 위 두 실패 모두 이 규칙 하나로 막혔다.

한계 (먼저 적는다)
------------------
- **A(셸 침묵)만 막는다. B(구조를 문자열로 셈)는 못 막는다** — 무엇을 세는지는
  여전히 사람이 정한다.
- 카나리아가 **그 규칙과 다른 규칙**이면, 두 규칙의 면제 범위가 다를 때 ⓪이 거짓 초록이 된다.
  그래서 `assert_harness_live` 는 **검사할 규칙 자체**로 카나리아를 만들라고 요구한다.
"""

from pathlib import Path
import subprocess
import sys

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

REPO_ROOT = Path(__file__).resolve().parents[1]


# ── 명령 실행 — 실패를 절대 삼키지 않는다 ────────────────────────────
# 흐름: 실행 -> 종료코드·stderr 를 «보이게» -> 호출자에게 통째로 돌려준다
# 🔴 stderr 를 버리지 않는 것이 이 함수의 존재 이유다. 버리면 «도구가 에러났다» 와
#    «위반이 0건이다» 가 같은 모양(빈 출력)이 된다 — 실제로 그렇게 8번 중 2번 틀렸다.
def run(cmd: list[str], *, allow_fail: bool = True) -> subprocess.CompletedProcess[str]:
    """명령을 돌리고 **stderr 를 버리지 않는다**.

    Args:
        cmd: 실행할 명령.
        allow_fail: False 면 비정상 종료 시 stderr 를 인쇄하고 예외를 올린다.

    Returns:
        완료된 프로세스(stdout·stderr·returncode 전부 보존).

    Raises:
        RuntimeError: `allow_fail` 이 False 인데 명령이 실패했을 때.
    """
    proc = subprocess.run(cmd, capture_output=True, text=True, cwd=REPO_ROOT, check=False)
    if not allow_fail and proc.returncode != 0:
        msg = f"명령 실패(rc={proc.returncode}): {' '.join(cmd)}\n--- stderr ---\n{proc.stderr}"
        raise RuntimeError(msg)
    return proc


# ── ruff 위반 수 — 「못 셌다」와 「0건」을 가른다 ──────────────────────
# 흐름: --statistics 실행 -> 도구 자체 오류면 None -> 아니면 정수
# 🔴 실패를 0 으로 바꾸지 않는다. 0 은 «위반이 없다» 는 답이고 None 은 «답을 못 얻었다» 다.
def ruff_count(rule: str, paths: list[str] | None = None) -> int | None:
    """한 ruff 규칙의 위반 수를 센다.

    Args:
        rule: 규칙 코드(예: ``D103``).
        paths: 검사 경로. 생략하면 저장소 전체.

    Returns:
        위반 수. **측정 자체에 실패하면 `None`** — 0 이 아니다.
    """
    cmd = ["uv", "run", "ruff", "check", "--no-cache", "--no-fix", "--select", rule, "--statistics"]
    proc = run([*cmd, *(paths or [])])
    # ruff 는 위반이 있으면 rc=1 이다. 그러나 «인자가 틀렸다» 도 rc!=0 이므로 구분해야 한다.
    if proc.returncode not in (0, 1):
        print(f"⚠️ ruff 측정 실패(rc={proc.returncode}) — {proc.stderr.strip()[:200]}")
        return None
    for line in proc.stdout.splitlines():
        parts = line.split()
        if len(parts) >= 2 and parts[0].isdigit() and parts[1] == rule:
            return int(parts[0])
    return 0


# ── ⓪ 하네스 살아있음 — 이 모듈의 핵심 ───────────────────────────────
# 흐름: 표본 자리에 «확실한 위반» 을 넣는다 -> 뜨는가 -> 원복
# 🔴 이 단계가 통과해야 ②의 침묵을 «규칙이 안 잡는다» 로 읽을 수 있다.
#    통과 못 하면 그 자리는 **검사 구역 밖**이다(면제 경로 · 비공개 모듈 · 제외 glob).
def assert_harness_live(probe: Path, canary_source: str, rule: str) -> None:
    """**주입하기 전에** 그 자리가 검사 대상인지 증명한다.

    Args:
        probe: 표식 파일 경로. 🔑 **실제 위반이 관측된 디렉터리**에 두어야 한다.
        canary_source: 그 `rule` 을 **확실히 한 번** 위반하는 소스.
        rule: 검사할 규칙 코드.

    Raises:
        AssertionError: 표식이 이미 있거나, 카나리아가 안 잡힐 때(= 검사 구역 밖).
    """
    assert not probe.exists(), f"🔴 이름 충돌 — {probe} 를 덮을 뻔했다"
    probe.write_text(canary_source, encoding="utf-8")
    try:
        seen = ruff_count(rule)
    finally:
        probe.unlink()
    assert seen is not None, f"🔴 하네스 측정 자체가 실패했다 — {rule}"
    assert seen >= 1, (
        f"🔴 하네스가 죽어 있다 — {probe} 에 {rule} 위반을 넣었는데 **0건**이다.\n"
        f"   그 자리는 검사 구역 밖이다. 확인할 것:\n"
        f"   ① per-file-ignores 가 그 경로에서 {rule} 을 면제하는가\n"
        f"   ② 파일명이 밑줄로 시작하는가(비공개 모듈 — D1xx 가 안 본다)\n"
        f"   ③ exclude glob·.gitignore 에 걸리는가\n"
        f"   🔑 표본은 **실제 위반이 관측된 디렉터리**에 둔다."
    )
