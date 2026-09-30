"""줄끝 게이트 — **워킹트리 전체에서 CR 을 막는다** (추적 여부와 무관).

왜 필요한가
-----------
`.gitattributes` 의 ``eol=lf`` 와 ``mixed-line-ending`` 훅이 이미 있는데도 이 게이트가 필요하다.
**둘 다 «추적 파일» 만 본다.**

- `.gitattributes` 는 **커밋·체크아웃 시점**에 작동한다. 디스크에 이미 있는 파일은 건드리지 않는다.
- `pre-commit` 은 **staged 파일**에만 훅을 돌린다. ``docs-private/`` 는 gitignore 라 **한 번도 staged 되지 않는다.**

⇒ 저장소에서 **가장 많이 고쳐지는 문서들**(직하 정본·스냅샷)이 구조적으로 무방비였다.
🔬 실측 2026-09-30: 추적 파일 CRLF **0**건인 상태에서 **미추적 파일 CRLF 170건**(CR 38,953개)이 있었다.

🔴 **왜 «결과» 를 보는가** — 원인을 막으려면 오탐이 난다
------------------------------------------------------
범인은 **파이썬 텍스트 모드**다. Windows 에서 ``Path.write_text()`` · ``open(f, "w")`` 는
``newline=None`` 기본값이라 ``chr(10)`` 을 ``os.linesep``(= CRLF)으로 **조용히 번역**한다.
🔑 **CPython 에 그 기본값을 바꾸는 환경변수·설정은 없다**(실측: ``os.linesep`` 은 코드로 못 바꾼다).

그렇다고 *"텍스트 모드로 쓰는 코드"* 를 금지하면 **정상 코드까지 걸린다** — 대부분의 쓰기는 문제가 없다.
과잉 차단하는 게이트는 사람이 끄고, 그러면 검출률이 0 이 된다(`QUALITY_GATES` §2-1).
⇒ **원인이 아니라 결과를 본다.** CR 이 파일에 있으면 실패다. 오탐이 원리적으로 없다.

📌 **대장 `D74` 가 이 게이트의 근거다** — *"파일을 고치는 스크립트가 줄끝을 통째로 바꿨다 —
gitignore 된 곳에선 신호가 0이다."* 그 항목을 **인용하면서 같은 사고를 다시 냈다**(2026-09-30,
`PLAN.md` 345줄). 읽은 것과 지킨 것은 다른 사실이고, 그 차이를 메우는 것이 기계다.

🔴 이 게이트가 **못 하는 것** (한계 선언)
-----------------------------------------
- **원인을 모른다.** CR 이 있다는 것만 안다 — 누가 어떤 함수로 썼는지는 사람이 찾는다.
- **바이너리를 확장자로 가르지 않는다**(NUL 바이트로 판별). 그래서 **NUL 없는 바이너리**는
  텍스트로 오인할 수 있다. 실측에서는 없었다.
- **고립 CR 을 «의도된 것» 과 구별하지 못한다.** 구 Mac 줄바꿈은 전부 결함으로 본다
  (실측 2026-09-30: `plan/` 스냅샷 4건에 31개 — 전부 렌더가 깨진 결함이었다).

사용
----
    uv run python -m scripts.gates.code.check_line_endings
"""

import sys

from scripts.gates._root import REPO_ROOT

if hasattr(sys.stdout, "reconfigure"):
  sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
  sys.stderr.reconfigure(encoding="utf-8", errors="replace")

#: 🔴 이스케이프 리터럴을 쓰지 않는다 — heredoc·스크립트를 거치며 한 겹이 벗겨져
#:    **소스에 진짜 CR 이 박히는** 사고가 실재한다(대장 `D45`①, 2026-09-30 재발).
CR = bytes([13])
LF = bytes([10])
CRLF = CR + LF

#: 들어가지 않는 곳 — 생성물·의존성·캐시. 남의 줄끝은 우리 책임이 아니다.
SKIP_DIRS = frozenset({
  ".git",
  "node_modules",
  "__pycache__",
  ".venv",
  ".next",
  ".ruff_cache",
  ".pytest_cache",
  ".mypy_cache",
  "htmlcov",
  ".uv-cache",
  "dist",
  "build",
})

#: 🔑 바닥값 — 0건은 *"깨끗하다"* 가 아니라 *"못 셌다"* 다.
#:    경로 필터가 틀리거나 예외를 삼키면 **대상 0건을 초록으로 보고**한다.
#:    ⚠️ 실측 2026-09-30: 텍스트 898개 · 바이너리 48개. 손으로 올린다.
MIN_SCANNED = 850

#: NUL 을 찾아볼 앞부분 크기. 전체를 읽으면 큰 바이너리에서 느려진다.
NUL_PROBE = 8000


def is_binary(blob: bytes) -> bool:
  """NUL 바이트로 바이너리를 판별한다.

  🔴 **확장자로 가르지 않는다.** 실측 2026-09-30 에 확장자 화이트리스트로 훑다가
  ``.iml`` · ``.xml`` · 확장자 없는 파일 **7건을 통째로 놓쳤다**.

  Args:
      blob: 파일 내용.

  Returns:
      바이너리로 보이면 ``True``.
  """
  return NUL_BYTE in blob[:NUL_PROBE]


NUL_BYTE = bytes([0])


def scan() -> tuple[int, int, list[tuple[str, int, int]]]:
  """워킹트리를 훑어 CR 을 가진 파일을 모은다.

  Returns:
      (검사한 텍스트 파일 수, 건너뛴 바이너리 수, [(경로, CRLF 수, 고립 CR 수)]).
  """
  scanned = 0
  binaries = 0
  offenders: list[tuple[str, int, int]] = []

  for path in REPO_ROOT.rglob("*"):
    if not path.is_file():
      continue
    if any(part in SKIP_DIRS for part in path.relative_to(REPO_ROOT).parts):
      continue
    try:
      blob = path.read_bytes()
    except OSError:
      continue
    if is_binary(blob):
      binaries += 1
      continue
    scanned += 1
    if CR not in blob:
      continue
    n_crlf = blob.count(CRLF)
    offenders.append((path.relative_to(REPO_ROOT).as_posix(), n_crlf, blob.count(CR) - n_crlf))

  return scanned, binaries, offenders


def main() -> int:
  """워킹트리 전체의 줄끝을 검사한다.

  Returns:
      종료코드 — 0 이면 통과.
  """
  scanned, binaries, offenders = scan()

  if scanned < MIN_SCANNED:
    print("❌ 줄끝 검사 실패 — **검사 범위가 줄었다**")
    print(f"   - 텍스트 파일 {scanned}개는 바닥값 {MIN_SCANNED} 아래다")
    print("   🔑 0건은 «CR 이 없다» 가 아니라 «못 셌다» 다 — SKIP_DIRS 나 예외 처리를 먼저 의심한다.")
    return 1

  if offenders:
    total_crlf = sum(n for _, n, _ in offenders)
    total_lone = sum(n for _, _, n in offenders)
    print(f"❌ 줄끝 검사 실패 — CR 을 가진 파일 **{len(offenders)}개**")
    print(f"   CRLF {total_crlf}개 · 고립 CR {total_lone}개")
    for name, n_crlf, n_lone in sorted(offenders, key=lambda row: -row[1] - row[2])[:12]:
      print(f"   - {name}  (CRLF {n_crlf} · 고립 CR {n_lone})")
    if len(offenders) > 12:
      print(f"   … 외 {len(offenders) - 12}개")
    print()
    print("   🔑 범인은 대개 **파이썬 텍스트 모드**다 — Windows 에서 `write_text()` 와")
    print('      `open(f, "w")` 는 줄바꿈을 CRLF 로 조용히 번역한다.')
    print("      ✅ `write_bytes()` 를 쓰거나 `newline=chr(10)` 을 **명시**한다.")
    print("   🔑 고치는 법: CRLF 를 먼저 접고, 남은 고립 CR 을 줄바꿈으로 편다.")
    print("      ⚠️ `docs-private/` 는 git 밖이라 **mtime 이 그 문서의 유일한 «언제»** 다 —")
    print("         옮기는 스냅샷은 `os.utime` 으로 mtime 을 되돌린다(FILING §12-1 · 대장 `D37`).")
    return 1

  print(f"✅ 줄끝 — 텍스트 {scanned}개 전수 CR 0 (바이너리 {binaries}개 제외).")
  return 0


if __name__ == "__main__":
  sys.exit(main())
