"""문서에 **마커로 표시된 수치**를 실측과 대조한다 — 트랙 B-15 S2.

왜 있나
-------
건수를 문서에 **사본**으로 적으면 반드시 썩는다. 원인은 망각이 아니라 구조다 —
**등재 1회가 고칠 자리 2곳을 만들기 때문**이다(2026-09-30 하루에 `ROADMAP` §지금 위치가
`64`→`67`→`68`→`69`→`70` 으로 **네 번** 움직였다. 전부 «등재·신설 직후»).

S1 이 사본을 대부분 **없앴다**(수치 16 + 상태 표식 15칸). 그래도 지울 수 없는 자리가 있다 —
§지금 위치는 *«여기만 보면 된다»* 가 존재 이유라 총합 한 칸은 남아야 한다.
**그 한 칸을 사람이 아니라 기계가 채운다.**

마커 꼴
-------
값 **뒤**에 붙는 HTML 주석 하나. 닫는 태그는 없다(주석이 이미 닫혀 있다)::

    `43`건**<!--=ledger-open-->

`=` 가 *«이 앞 숫자는 기계가 채운다»* 는 뜻이고, 치환은 **마커 바로 앞의 가장 가까운 숫자**를
바꾼다 — 백틱·볼드·맨숫자 어디에 붙어도 찾는다. 렌더하면 숫자만 보인다.

🔴 **순서 의존 마커는 쓰지 않는다**(기각한 대안). *«줄 끝에 주석 하나 + 그 줄의 수치를 순서대로»*
가 가장 짧지만, 문장을 고치면 매핑이 **조용히** 어긋나 틀린 값을 넣는다.

🔴 이 게이트가 **하지 않는 것**
-------------------------------
- **트랙(A·B·C)의 «열림» 은 세지 않는다.** 그 표들은 상태를 이모지·산문으로 말하고,
  `🔶 2구간 완료 … 3구간 남음` 처럼 **«완료» 가 들어 있는데 열려 있는** 행이 있다 —
  문자열로 세면 틀린다(`D47`). 빌더가 그래서 안 센다. ⇒ 마커가 담는 것은
  **원장 3종(`QA`·`문서-N`·`L-N`)의 열림**이고, 이름도 `ledger-open` 이다.
  트랙까지 세려면 **먼저 그 표의 상태를 텍스트 어휘로 바꿔야 한다**(→ `문서-55`).
- **값을 판정하지 않는다.** 빌더가 센 수를 옮길 뿐이다. 빌더가 틀리면 여기도 틀린다.

무엇을 막나
-----------
1. 마커 값 ≠ 실측
2. **마커 선언이 2건 이상** — 산문에 마커 리터럴을 인용하면 게이트가 그것을 선언으로 센다
   (`D69` 와 같은 함정. 실제로 S1 에서 한 번 밟았다)
3. 마커 앞에 숫자가 없다 — 치환 대상을 못 찾는다
4. 등록되지 않은 마커 이름
5. 🔢 **바닥값 미달** — 마커를 0개 찾았으면 «깨끗함» 이 아니라 «못 찾음» 이다

`--fix`
-------
🔴 **바뀔 때만 쓴다.** 값이 이미 맞으면 **파일을 열지도 않는다** — `docs-private/` 는 git 밖이라
**mtime 이 그 문서의 유일한 «언제»** 이고, 무조건 쓰면 `check_portfolio_sync` 의 신선도 입력이
오염된다(`D41` · `FILING` §12-1).

🔴 **`--fix` 는 로컬 전용이다.** CI 는 대조만 한다 — CI 가 고치면 커밋되지 않은 수정이 생겨
*«생성물 == 커밋본»* 대조와 충돌한다.
"""

import argparse
from pathlib import Path
import re
import sys

from scripts.gates._root import PRIVATE
from scripts.gates.doc.build_followup_index import build

if hasattr(sys.stdout, "reconfigure"):
  sys.stdout.reconfigure(encoding="utf-8", errors="replace")

#: 마커를 찾는 문서. 🔴 직하 정본만 본다 — 닫힌 스냅샷에 마커를 넣으면 mtime 이 깨진다.
TARGETS = ("ROADMAP.md", "FOLLOWUP_QUEUE.md", "DOC_TRUTH_DRIFT.md", "LOCAL_RESIDUE.md")

#: 🔢 바닥값 — 이 아래로 떨어지면 «못 찾음» 으로 본다(게이트 범위는 조용히 줄어든다).
MIN_MARKERS = 1

#: 마커 이름 등록부. 값은 `build()` 의 집계에서 뽑는다.
#: 🔴 등록되지 않은 이름은 막는다 — 오타가 «조용히 통과» 하면 그 칸은 영원히 안 채워진다.
KNOWN = ("ledger-open",)

MARKER = re.compile(r"<!--=([a-z][a-z0-9-]*)-->")

#: 🔴 **코드 안의 마커는 선언이 아니다.** 문서가 마커 꼴을 설명할 때 예시를 인용하는데,
#: 그것을 선언으로 세면 «등록되지 않은 이름» 으로 오탐한다(실측: `ROADMAP` §지금 위치의
#: ``` `41`<!--=qa-open--> ``` 예시). `D69` 와 같은 함정의 반대편이다 — 저쪽은 **산문**
#: 인용을 세는 것이었고 이쪽은 **코드** 인용이다. 정상 인용은 통과해야 한다.
FENCE = re.compile(r"```.*?```", re.DOTALL)
SPAN2 = re.compile(r"``.+?``", re.DOTALL)
SPAN1 = re.compile(r"`[^`\n]+`")

#: 마커 앞에서 숫자를 찾는 범위(글자). 백틱·`건`·볼드가 끼어도 닿는 거리다.
LOOKBACK = 16
TAIL = re.compile(r"(\d+)([^\d]*)$")


# ── 코드 인용을 가린다 ───────────────────────────────────────────────
# 흐름: 펜스 -> 이중 백틱 -> 단일 백틱을 **같은 길이 공백**으로 (인덱스가 보존된다)
# 🔑 길이를 보존해야 masked 에서 찾은 위치를 원본에 그대로 쓸 수 있다.
def mask_code(text: str) -> str:
  """코드 블록·코드 스팬을 같은 길이의 공백으로 바꾼다.

  Args:
      text: 원본 본문.

  Returns:
      길이가 같고 코드 구간만 공백인 본문.
  """
  for pattern in (FENCE, SPAN2, SPAN1):
    text = pattern.sub(lambda m: " " * (m.end() - m.start()), text)
  return text


# ── 실측값 ───────────────────────────────────────────────────────────
# 흐름: build() -> opens(원장별 열림) -> 마커 이름별 값
# 🔴 build() 가 열림을 못 셌으면(fail-closed) 여기서도 멈춘다 — 0 을 답으로 내지 않는다.
def measure() -> tuple[dict[str, int], list[str]]:
  """마커 이름 → 실측값. 두 번째 값은 문제 메시지 목록이다.

  Returns:
      (값 사전, 문제 목록).
  """
  _content, _counts, opens, problems = build()
  if problems:
    return {}, [f"빌더가 열림을 못 셌다 — {p}" for p in problems]
  missing = [k for k in ("QA", "문서", "L") if k not in opens]
  if missing:
    return {}, [f"빌더 출력에 원장이 빠졌다 — {', '.join(missing)}"]
  return {"ledger-open": sum(opens[k] for k in ("QA", "문서", "L"))}, []


# ── 마커 한 개의 위치 ────────────────────────────────────────────────
# 흐름: 마스킹된 본문에서 그 이름의 마커를 찾아 **시작 인덱스**를 돌려준다
def locate(masked: str, name: str) -> int | None:
  """마커 시작 위치. 코드 인용은 이미 가려져 있으므로 진짜 선언만 잡힌다.

  Args:
      masked: `mask_code` 를 거친 본문.
      name: 마커 이름.

  Returns:
      시작 인덱스, 없으면 None.
  """
  hit = re.search(r"<!--=" + re.escape(name) + r"-->", masked)
  return hit.start() if hit else None


# ── 문서 하나를 대조한다 ─────────────────────────────────────────────
# 흐름: 마커 수집 -> 선언 건수 검증 -> 앞 숫자 찾기 -> 실측과 비교
def inspect(path: Path, truth: dict[str, int]) -> tuple[list[str], dict[str, int], int]:
  """문서 하나를 판정한다.

  Args:
      path: 대상 문서.
      truth: 마커 이름 → 실측값.

  Returns:
      (오류 목록, {마커 이름: 문서에 적힌 값}, 마커 개수).
  """
  text = path.read_text(encoding="utf-8", errors="replace")
  masked = mask_code(text)
  names = MARKER.findall(masked)
  if not names:
    return [], {}, 0

  errors: list[str] = []
  found: dict[str, int] = {}
  for name in sorted(set(names)):
    # 🔴 선언이 둘이면 어느 쪽이 값인지 알 수 없다 — 산문 인용을 실제 선언으로 세는 함정(D69).
    seen = names.count(name)
    if seen > 1:
      errors.append(
        f"{path.name}: 마커 `{name}` 선언이 **{seen}건**이다 — "
        "산문에 마커 리터럴을 인용하면 게이트가 그것을 선언으로 센다. 이름만 적는다"
      )
      continue
    if name not in truth:
      known = ", ".join(KNOWN)
      errors.append(f"{path.name}: 등록되지 않은 마커 이름 `{name}` — 등록부: {known}")
      continue
    spot = locate(masked, name)
    hit = TAIL.search(text[max(0, spot - LOOKBACK) : spot]) if spot is not None else None
    if hit is None:
      errors.append(f"{path.name}: 마커 `{name}` 앞에 숫자가 없다 — 채울 자리를 못 찾는다")
      continue
    written = int(hit.group(1))
    found[name] = written
    if written != truth[name]:
      errors.append(f"{path.name}: 마커 `{name}` 이 **{written}** 이라는데 실측은 **{truth[name]}** 이다")
  return errors, found, len(names)


# ── 고친다 ───────────────────────────────────────────────────────────
# 흐름: 새 본문 계산 -> 원본과 같으면 **쓰지 않는다**(mtime 보존이 아니라 «건드리지 않기»)
def repair(path: Path, truth: dict[str, int]) -> list[str]:
  """마커 값을 실측으로 맞춘다. 바뀐 마커 이름 목록을 돌려준다.

  Args:
      path: 대상 문서.
      truth: 마커 이름 → 실측값.

  Returns:
      실제로 고친 마커 이름 목록.
  """
  text = path.read_text(encoding="utf-8", errors="replace")
  original = text
  changed: list[str] = []
  for name, want in truth.items():
    # 🔴 위치는 **마스킹된 본문**에서 얻는다 — 코드 인용을 고치면 예시가 망가진다.
    spot = locate(mask_code(text), name)
    if spot is None:
      continue
    head = text[max(0, spot - LOOKBACK) : spot]
    hit = TAIL.search(head)
    if hit is None or int(hit.group(1)) == want:
      continue
    cut = max(0, spot - LOOKBACK) + hit.start(1)
    text = text[:cut] + str(want) + text[cut + len(hit.group(1)) :]
    changed.append(name)
  # 🔴 무변경이면 쓰지 않는다 — 쓰면 mtime 이 갱신돼 신선도 게이트 입력이 오염된다(D41).
  if text != original:
    path.write_text(text, encoding="utf-8", newline="\n")
  return changed


def main() -> int:
  """진입점.

  Returns:
      종료 코드.
  """
  parser = argparse.ArgumentParser(description="문서 마커 수치를 실측과 대조한다")
  parser.add_argument("--fix", action="store_true", help="틀린 마커를 실측으로 고친다(로컬 전용)")
  args = parser.parse_args()

  truth, problems = measure()
  if problems:
    print("❌ 문서 마커 검사 실패 — 실측을 얻지 못했다")
    for p in problems:
      print(f"   - {p}")
    return 1

  errors: list[str] = []
  total = 0
  fixed: list[str] = []
  for name in TARGETS:
    path = PRIVATE / name
    if not path.exists():
      continue
    if args.fix:
      fixed += [f"{path.name}:{n}" for n in repair(path, truth)]
    found_errors, _written, count = inspect(path, truth)
    errors += found_errors
    total += count

  if errors:
    print(f"❌ 문서 마커 위반 {len(errors)}건 (정본 = docs-private/PLAN.md 트랙 B-15 S2):")
    for e in errors:
      print(f"   - {e}")
    print("   ✅ 고치는 법: `--fix` 를 붙여 다시 돌린다(값만 바뀐다).")
    return 1

  # 🔢 0건은 «깨끗함» 이 아니라 «못 찾음» 이다 — 바닥값으로 막는다.
  if total < MIN_MARKERS:
    print(f"❌ 마커를 **{total}개** 찾았다 — 바닥값 {MIN_MARKERS} 미달.")
    print("   마커가 지워졌거나 정규식이 좁아졌다. 0 을 답으로 받지 않는다.")
    return 1

  tally = " · ".join(f"{k} {v}" for k, v in sorted(truth.items()))
  suffix = f" · 고침 {len(fixed)}건" if args.fix else ""
  print(f"✅ 문서 마커 — {total}개 일치 (바닥값 {MIN_MARKERS}) · {tally}{suffix}.")
  return 0


if __name__ == "__main__":
  sys.exit(main())
