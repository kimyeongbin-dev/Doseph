"""트랙 상태 어휘 게이트에 **결핍을 주입**한다 — `문서-55` S5.

왜 별 스크립트인가
------------------
`injection_harness.run_doc_gate` 는 게이트에 **경로 인자**를 넘기는데, 여기서 검증할 둘
(`build_followup_index` · `check_doc_markers`)은 **정본 경로를 직접 읽는다**(인자를 안 받는다).
⇒ 사본에 주입할 수 없으므로 **정본을 백업 → 주입 → `finally` 원복 → 바이트 동일 확인**한다.
🔴 `D68` 이 *«소스를 안 읽고 이 하네스를 쓰겠다고 계획에 적었다»* 로 적어 둔 자리라, 쓰기 전에
`run_doc_gate` 의 구현을 읽고 적용 범위를 확인했다.

무엇을 묻나
-----------
``⓪`` 손대지 않은 정본이 Green 인가 — 아니면 아래 Red 는 아무것도 증명하지 않는다
``①~④`` 결핍을 넣으면 Red 인가 (fail-closed 가 무장돼 있나)
``⑤~⑥`` 정상 표본은 통과하고 **값이 맞는가** — 🔴 *«기대 = 통과»* 는 아무것도 안 해도
통과하므로, 음성 대조는 **실제 수를 대조**해야 뜻이 있다(`D46`).
"""

import subprocess
import sys

from scripts.gates._root import PRIVATE
from scripts.gates.doc.build_followup_index import (
  CLOSED_TOKENS,
  FLOORS,
  PENDING,
  PROGRESS,
  build,
)
from scripts.injection_harness import inject

if hasattr(sys.stdout, "reconfigure"):
  sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
  sys.stderr.reconfigure(encoding="utf-8", errors="replace")

ROADMAP = PRIVATE / "ROADMAP.md"
BUILDER = "scripts.gates.doc.build_followup_index"
MARKERS = "scripts.gates.doc.check_doc_markers"


# ── 게이트 하나를 돌린다 ─────────────────────────────────────────────
# 흐름: 모듈 실행 -> 종료코드 (0 = 통과)
def gate(module: str, *args: str) -> tuple[int, str]:
  """게이트 모듈을 돌려 종료코드를 돌려준다.

  Args:
      module: 모듈 경로.
      *args: 추가 인자.

  Returns:
      (종료코드, stderr + stdout).
  """
  done = subprocess.run(
    [sys.executable, "-m", module, *args],
    capture_output=True,
    text=True,
    encoding="utf-8",
    errors="replace",
    check=False,
  )
  return done.returncode, (done.stderr or "") + (done.stdout or "")


#: 주입 케이스 — (이름, 바꿀 것, 바꿔 넣을 것, 돌릴 게이트, 인자)
#: 🔑 표본은 **결함과 가장 닮았지만 결함인 것**을 고른다 — 전부 «이 표가 어제까지 쓰던 꼴» 이다.
CASES = (
  (
    "① 트랙 B 상태를 이모지로 되돌린다 (B-8 — «완료» 가 들어 있는데 열린 행)",
    "| 8 | **테스트 표준 현대화** | `부분` **2구간 완료 2026-09-22 · 3구간 남음**",
    "| 8 | **테스트 표준 현대화** | 🔶 **2구간 완료 2026-09-22**",
    BUILDER,
    ("--check",),
  ),
  (
    "② 트랙 A 상태를 산문으로 되돌린다 (v2.3 진행 중)",
    "| `진행` |",
    "| **🔄 진행 중** |",
    BUILDER,
    ("--check",),
  ),
  (
    "③ 트랙 C 상태 칸을 비운다 (OCR-1)",
    "| 중 | `열림` |\n| **OCR-2**",
    "| 중 |  |\n| **OCR-2**",
    BUILDER,
    ("--check",),
  ),
  (
    "④ 마커 값을 1 틀리게 한다 (track-open 26 -> 25)",
    "**트랙 열림 = 26건**<!--=track-open-->",
    "**트랙 열림 = 25건**<!--=track-open-->",
    MARKERS,
    (),
  ),
)


#: 🔴 **Red 의 «이유»** — 종료코드만 보면 *«내가 주입한 결함»* 과 *«주입이 건드린 부수 효과»* 를
#:    구분할 수 없다(`D22`). ①~③ 은 `ROADMAP` 을 고치므로 **«색인이 원장과 어긋난다»** 만으로도
#:    Red 가 날 수 있었다 — 그러면 fail-closed 가 무장됐는지는 **아무것도 증명되지 않는다.**
#:    🔑 실측(2026-10-06): `build()` 가 `problems` 를 **색인 대조보다 먼저** 거부해 이유가 맞았다.
#:    그래도 문구를 대조한다 — 순서가 바뀌면 조용히 헛된 초록이 된다.
EXPECT = {
  "①": "상태 토큰이 없는 트랙 B",
  "②": "상태 토큰이 없는 트랙 A",
  "③": "상태 토큰이 없는 트랙 C·OCR·ARCH",
  "④": "마커 `track-open`",
}


# ── 음성 대조 — 값을 대조한다 ────────────────────────────────────────
# 흐름: 판정기를 직접 불러 트랙별 열림 수를 센다 -> 기대와 대조
# 🔴 «통과했다» 로 끝내지 않는다 — `return 1` 만 하는 게이트도 그건 만점이다.
def negative_checks() -> list[str]:
  """정상 표본에서 **수가 맞는지** 본다.

  Returns:
      실패 메시지 목록(비면 전부 통과).
  """
  fails: list[str] = []
  _content, counts, opens, problems = build()
  if problems:
    fails.append(f"정상 정본인데 문제가 보고됐다 — {problems}")
  # 🔴 **기대값을 박지 않는다** — 2026-10-06 에 박아 봤더니 같은 작업에서 `B-16` 을 등재하자
  #    **즉시 썩었다**(기대 15 vs 실제 16). 등재 수는 늘어나는 값이라 상수로 고정할 수 없다.
  #    ⇒ 대신 **썩지 않는 불변식**을 본다.
  for key in ("A", "ROADMAP", "B"):
    count, opened = counts.get(key), opens.get(key)
    if count is None or opened is None:
      fails.append(f"{key}: 빌더 출력에 없다")
      continue
    # ① 바닥값은 게이트가 이미 유지하는 값을 재사용한다(두 벌로 만들지 않는다)
    if count < FLOORS[key]:
      fails.append(f"{key}: 등재 {count} 가 바닥값 {FLOORS[key]} 미달이다")
    # ② 🔑 **판정이 실제로 갈렸나** — 전부 열림이나 전부 닫힘이면 하네스를 의심한다(§6-1).
    #    트랙은 완료된 단계와 남은 단계가 **둘 다** 있는 표라, 한쪽으로 쏠리면 판정기가 죽었다.
    elif not 0 < opened < count:
      fails.append(f"{key}: 열림 {opened}/{count} — 전부 열림이나 전부 닫힘이다(판정기를 의심한다)")
  # ③ `보류`·`진행` 이 **닫힘으로 세어지지 않는가** — 그러면 열린 과제가 조용히 사라진다
  fails.extend(
    f"`{token}` 가 닫힘 어휘에 들어 있다 — 열린 과제가 사라진다"
    for token in (PENDING, PROGRESS)
    if token in CLOSED_TOKENS
  )
  return fails


# ── 본체 ─────────────────────────────────────────────────────────────
# 흐름: ⓪ 원본 Green -> ①~④ 주입 Red -> ⑤~⑥ 음성 대조 -> finally 바이트 원복
def main() -> int:
  """주입과 음성 대조를 돌린다.

  Returns:
      0 이면 전부 기대대로.
  """
  original = ROADMAP.read_bytes()
  text = original.decode("utf-8")
  passed = failed = 0

  try:
    # ⓪ 하네스가 살아 있나 — 손대지 않은 정본이 Green 이어야 한다
    for module, args in ((BUILDER, ("--check",)), (MARKERS, ())):
      code, _ = gate(module, *args)
      if code != 0:
        print(f"🔴 ⓪ 하네스가 죽어 있다 — 손대지 않은 정본에 {module} 이 rc={code}", file=sys.stderr)
        print("   이 상태에서 «주입했더니 Red» 는 아무것도 증명하지 않는다.", file=sys.stderr)
        return 1
    print("✅ ⓪ 하네스 살아있음 — 손대지 않은 정본에서 두 게이트 전부 Green")

    # ①~④ 결핍 주입 — Red 여야 정상
    for name, old, new, module, args in CASES:
      expect = EXPECT[name[0]]
      ROADMAP.write_text(inject(text, old, new), encoding="utf-8", newline="\n")
      code, output = gate(module, *args)
      ROADMAP.write_bytes(original)
      if code == 0:
        print(f"🔴 {name} — 통과했다(Red 여야 한다)", file=sys.stderr)
        failed += 1
      elif expect not in output:
        # 🔴 Red 이긴 한데 **다른 이유**다 — 이 주입은 아무것도 증명하지 않았다
        first = output.strip().splitlines()[0][:120] if output.strip() else "(출력 없음)"
        print(f"🔴 {name} — Red 지만 이유가 다르다. 기대 문구 {expect!r} 가 없다", file=sys.stderr)
        print(f"   실제: {first}", file=sys.stderr)
        failed += 1
      else:
        print(f"✅ {name} — Red (rc={code}) · 이유 확인: {expect}")
        passed += 1

    # ⑤~⑥ 음성 대조
    fails = negative_checks()
    if fails:
      for line in fails:
        print(f"🔴 음성 대조 — {line}", file=sys.stderr)
      failed += len(fails)
    else:
      print("✅ 음성 대조 — 바닥값 이상 · 트랙마다 열림과 닫힘이 둘 다 있다 · `보류`·`진행` 이 열림으로 센다")
      passed += 1
  finally:
    # 🔴 바이트 단위 원복을 **확인**한다 — 주입이 정본을 남기면 그게 가장 나쁜 실패다
    ROADMAP.write_bytes(original)
    assert ROADMAP.read_bytes() == original, "🔴 정본 원복에 실패했다"

  print(f"\n{'✅' if not failed else '🔴'} 주입·대조 {passed}/{passed + failed}")
  return 1 if failed else 0


if __name__ == "__main__":
  raise SystemExit(main())
