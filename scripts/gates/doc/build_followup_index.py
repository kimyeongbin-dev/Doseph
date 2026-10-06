"""후속 과제 색인을 **생성**한다 — 손으로 적지 않는다.

`pre-commit` 의 ``pre-push`` 스테이지에서 ``--check`` 로 실행된다.

왜 생성인가
-----------
2026-09-20, 큐 현황판이 *"§B 미착수 **19**"* 라고 적고 있었는데 **실제 28** 이었다.
`QA-32~40` 이 들어올 때 절 건수가 안 따라온 것인데, **총계(41)는 맞아서 합으로는
안 드러났다**(대장 **D29** — *"두 칸이 반대로 틀리면 합은 맞는다"*).

> **손으로 적은 숫자는 반드시 썩는다. 유일한 해법은 사람이 안 적는 것이다.**

그래서 이 스크립트가 다섯 원장을 읽어 색인을 만들고, 게이트가 *생성물 == 커밋된 것*을
대조한다. 색인이 낡으면 **push 가 막힌다.**

무엇을 안 하나 (한계 선언)
--------------------------
- **내용을 판정하지 않는다.** 표에 적힌 것을 옮길 뿐이라, 표가 거짓이면 색인도 거짓이다.
- **`study/`·`docs/` 의 ID(`V-A`~`V-H`·`R##`)는 범위 밖**이다 — 후속 과제가 아니라 분류·규칙이다.
- **열린 것만 세지 않는다.** 닫힌 것도 실어야 *"왜 번호가 비었나"* 를 묻지 않는다.

🔴 ID 는 **줄 머리 앵커**로만 센다(`FILING.md` §3-3 규칙 3). 맨 정규식은 base64·`.venv`·
예고 산문을 물어 **존재하지 않는 ID** 를 만든다 — 실측 하루 3회.
"""

import argparse
import re
import sys

# stdout/stderr 방어가 import 보다 먼저여야 한다 — cp949 크래시 방지(대장 D36).
if hasattr(sys.stdout, "reconfigure"):
  sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
  sys.stderr.reconfigure(encoding="utf-8", errors="replace")

from scripts.gates._root import PRIVATE
from scripts.gates.doc.check_table_shape import split_escaped

INDEX = PRIVATE / "FOLLOWUP_INDEX.md"

#: 표 행 — 줄 머리에 `| **<ID>** |` 가 와야 한다.
#: ⚠️ ID 뒤에 제목이 **같은 굵게 안에** 들어오는 행이 있다 — `| **C-7 챗봇 개인화 툴** |`.
#:    `\*\*ID\*\*` 로 닫으면 그런 행 6개가 통째로 안 보인다(바닥값이 잡았다).
ROW = re.compile(r"^\|\s*\*\*([A-Z가-힣]+-?\d+)[^*|]*\*\*[^|]*\|(.*)$", re.MULTILINE)
#: 제목형 항목 — `### QA-01 — 제목`
HEAD = re.compile(r"^#{2,4}\s+(QA-\d+|문서-\d+)\s*[—-]\s*(.+)$", re.MULTILINE)
#: 트랙 B 의 단계 표 — `| 9 | **문서 정독·분류** | 🔵 진행 중 |`
BSTEP = re.compile(r"^\|\s*\*{0,2}(\d{1,2})\*{0,2}\s*\|([^|]+)\|([^|]*)\|", re.MULTILINE)
#: 트랙 A 의 「한눈에 보기」 표 — `| v2.3 | 테마 | 중 | 상태 | 종료 기준 |`
#: 🔴 `ROW` 로는 못 잡는다 — 그 패턴은 **굵은 ID**(`| **C-6** |`)를 요구하는데 이 표는 굵게가 아니다.
#:    2026-10-06 실측: 이 꼴은 저장소에서 **8행 전부 「한눈에 보기」 절**에만 있다(유일하다).
AROW = re.compile(r"^\|\s*(v2\.\d)\s*\|(.*)$", re.MULTILINE)

NOISE = re.compile(r"\*\*|`|<br>|[🔴🟠🟡🟢🔵⬜✅⚠️🔑⭐📦⏸⛔🆕🟦🧱🧪🔁]")

#: 바닥값 — 0건은 *"없다"* 가 아니라 *"못 셌다"* 이다(fail-closed).
#: ⚠️ 손으로 올린다. 항목이 늘어 이 값을 넘기면 그때 올리는 것이 **의식적인 결정**이 된다.
#: ⚠️ QA 41 -> 33: 2026-09-21 §C(완료 8건)를 `record/2026-09-21_qa-completed-record.md` 로
#:    **배출**했다. 바닥값이 그 감소를 잡아 차단했고(설계대로), 배출이 의도였음을 확인하고
#:    의식적으로 내렸다 — 조용히 0이 되는 것과 다르다.
#: ⚠️ 2026-09-21 (B-8 닫기): QA 39->36 — QA-06·09·11 **배출**. 닫으면 내려가므로 같이 내린다
#: ⚠️ 2026-09-21 (B-8 S1): QA 36->38(QA-45·46 — respx 가 처음 관측한 잠금-불일치)
#: ⚠️ 2026-09-21 (B-8 S1): 문서 23->24(문서-27 — 감사 노트의 카카오 서술 오류)
#: ⚠️ 2026-09-21 (B-9 종료 점검): QA 34->36(QA-43·44 — 게이트가 스스로 예약한 전환)
#: ⚠️ 2026-09-21 (B-9 S8): QA 33->34(QA-42) · 문서 22->23(문서-25·26 신규, 문서-8·15 닫힘)
#:    · ROADMAP 17->18(OCR-3). 닫으면 내려가므로 **닫을 때 같이 내린다.**
#: ⚠️ 2026-09-22 (B-10 2구간 · B-11 조사): QA 35->36(QA-50 — 읽음 마커가 압축 후 보증을 잃는다)
#:    · 문서 26->27(문서-30 — 하위 CLAUDE.md 가 로드되지 않는 AGENTS.md 를 가리킨다)
#:    · L 10->11(L-10 — S0 표식 규칙 잔재)
#: ⚠️ 2026-09-23 (B-13 1구간 닫기): QA 38->40(QA-53 면제 미대조 · QA-54 게이트 단위테스트)
#:    · 문서 28->30(문서-32 closes 비대칭 · 문서-33 판 교체 시점)
#: ⚠️ 2026-09-23: B 13->14(B-14 — 문서-N 원장 처분) · 문서 30->31(문서-34 — 마이그레이션 COMMENT)
#:    · QA 40->41(QA-55 — closes 의 «내용» 을 아무도 안 읽는다)
#: ⚠️ 2026-09-22 (B-11 S2): QA 36->37(QA-51) · 37->38(QA-52 — debt-baseline 천장의 내용물)
#: ⚠️ 2026-09-22 (B-11 닫은 뒤): 문서 27->28(문서-31 — 색인이 «미해결» 을 못 센다)
#:    · ROADMAP 19->21(B-12 AGENTS.md 재배치 · B-13 예방기 열)
#: ⚠️ 2026-10-06 (`문서-55`): **트랙 A 를 세기 시작했다**(8단계 · v2.0~v2.7). 그전까지 빌더는
#:    그 표를 **아예 안 봤다** — *«열린 것 전체»* 라고 부르면서 한 트랙이 통째로 빠져 있었다.
FLOORS = {"QA": 41, "문서": 37, "L": 13, "A": 8, "ROADMAP": 20, "B": 14}


#: 🔴 **항목 상태 어휘 — 텍스트 값이다. 이모지로 태깅하지 않는다**(사용자 지시 2026-09-22).
#:    이모지는 전각·조합 문자라 셸 정규식에서 자주 깨진다 — 기계가 파싱할 필드는 텍스트여야 한다.
#:    `문서-N` 은 한 표에 열림·닫힘이 섞여 있어 **행마다 토큰**이 필요하다(문서-31).
OPEN = "열림"
CLOSED_TOKENS = frozenset({"완료", "보냄", "기각"})
#: 🔴 **`보류` 는 «열림» 이다 — `CLOSED_TOKENS` 에 넣지 않는다**(2026-09-30, B-15 S4 · 사용자 제안).
#:    *«착수 조건이 올 때까지 대기»* 는 **아직 처분되지 않은 것**이다. 닫힘으로 세면
#:    후속 과제가 조용히 사라진다 — `FILING` §8-5 가 *«보류는 죽지 않는다»* 로 못 박은 그것이다.
#: ⚠️ **문서 `status: pending` 과 이름이 겹치지 않게 갈랐다** — 항목 상태는 **`보류`**,
#:    문서 생애주기는 **`pending`**(`FILING` §8 이 *«이름이 겹치지 않게»* 를 절 제목으로 단 문서다).
PENDING = "보류"
#: 🔴 **`진행` 도 «열림» 이다** (2026-10-06, `문서-55`). 트랙 A 의 *«진행 중»* 을 받기 위해 넣었다 —
#:    원장 3종에는 이 상태가 없었다(항목은 열렸거나 닫혔거나다). **트랙은 «구간» 이라 중간이 있다.**
PROGRESS = "진행"
STATUS_TOKENS = CLOSED_TOKENS | {OPEN, PENDING, PROGRESS, "부분"}
STATUS_RE = re.compile(r"`(" + "|".join(sorted(STATUS_TOKENS)) + r")`")

#: 절로 열림/닫힘이 갈리는 원장 — 표가 아니라 **구조**가 상태를 말한다.
#: `QA` 는 §C(완료 → 배출), `L` 은 §2(닫힌 항목).
#: 🔑 `QA` 는 **둘**이다 — §C(완료 → 배출)와 §A(잠금-불일치 **개념 선언**, 전건 해소).
CLOSED_SECTIONS = {"QA": ("§C", "§A"), "L": ("2. 닫힌",)}


def tidy(text: str, limit: int = 150) -> str:
  """표 셀에서 장식을 걷고 한 줄로 줄인다."""
  clean = NOISE.sub("", text).replace("|", "/").strip()
  clean = re.sub(r"\s+", " ", clean)
  return clean[:limit] + ("…" if len(clean) > limit else "")


# ── 원장 하나에서 항목을 긁는다 ─────────────────────────────────────
# 흐름: 파일 읽기 -> 줄머리 앵커로 표 행·제목형 수집 -> (ID, 셀들) 목록
def scrape(filename: str, prefix: str) -> list[tuple[str, list[str]]]:
  """(ID, 셀 목록). `prefix` 로 시작하는 ID 만 남긴다.

  🔑 마지막 셀 뒤에 **그 행이 있던 절 이름**을 붙인다 — `QA`·`L` 은 절이 상태를 말한다.
  """
  path = PRIVATE / filename
  body = path.read_text(encoding="utf-8", errors="replace")
  items: dict[str, list[str]] = {}
  section = ""
  for line in body.splitlines():
    if line.startswith("## "):
      section = line[3:].strip()
    row = ROW.match(line)
    if row and row.group(1).startswith(prefix):
      cells = [c.strip() for c in split_escaped(row.group(2)) if c.strip()]
      items.setdefault(row.group(1), [*cells, f"§절={section}"])
  section = ""
  for line in body.splitlines():
    if line.startswith("## "):
      section = line[3:].strip()
    head = HEAD.match(line)
    if head and head.group(1).startswith(prefix):
      items.setdefault(head.group(1), [head.group(2).strip(), f"§절={section}"])
  return sorted(items.items(), key=lambda kv: int(re.sub(r"\D", "", kv[0]) or 0))


# ── 열림/닫힘 판정 ──────────────────────────────────────────────────
# 흐름: 원장마다 다른 신호를 읽는다 — 구조(절) 또는 토큰
# 🔴 두 방식이 섞이는 이유: `QA`·`L` 은 절이 갈라 놨고, `문서-N` 은 한 표에 섞여 있다.
def open_count(rows: list[tuple[str, list[str]]], ledger: str) -> tuple[int, str | None]:
  """(열린 건수, 문제 메시지 또는 None)."""
  if ledger in CLOSED_SECTIONS:
    marks = CLOSED_SECTIONS[ledger]
    return sum(1 for _, cells in rows if not any(m in cells[-1] for m in marks)), None

  if ledger != "문서":
    return len(rows), None

  # 🔴 fail-closed — 토큰 없는 행이 하나라도 있으면 «열림» 수를 믿을 수 없다.
  # 🔴 «상태 셀» 에서만 찾는다 — 전체를 이으면 **내용 셀의 같은 단어**가 먼저 걸린다.
  #    `cells[-1]` 은 절 표식이므로 그 앞이 상태 셀이다.
  def token(cells: list[str]) -> str | None:
    cell = cells[-2] if len(cells) >= 2 else ""
    found = STATUS_RE.search(cell)
    return found.group(1) if found else None

  missing = [ident for ident, cells in rows if token(cells) is None]
  if missing:
    head = " · ".join(missing[:8]) + (" …" if len(missing) > 8 else "")
    return 0, f"상태 토큰이 없는 `문서-N` {len(missing)}건 — {head}"
  opened = sum(1 for _, cells in rows if token(cells) not in CLOSED_TOKENS)
  return opened, None


# ── 트랙 A 수집 ──────────────────────────────────────────────────────
# 흐름: 「한눈에 보기」 행 -> 칸 분리 -> (ID, [테마, **상태**])
# 🔑 **상태를 마지막 셀에 둔다** — `track_open_count` 가 칸 위치를 추측하지 않게.
# 🔴 **`tidy()` 를 여기서 걸지 않는다.** 그 함수는 백틱을 지우므로(`NOISE`) 상태 토큰
#    ``` `완료` ``` 가 ``` 완료 ``` 가 되어 **판정기가 못 찾는다.** 표시용 축약은 `table()` 이 한다.
def collect_track_a(body: str) -> tuple[list[tuple[str, list[str]]], list[str]]:
  """「한눈에 보기」 8행을 (ID, [테마, 상태]) 로 모은다.

  Args:
      body: ``ROADMAP.md`` 전문.

  Returns:
      (행 목록, 문제 목록).
  """
  rows: list[tuple[str, list[str]]] = []
  problems: list[str] = []
  for ident, rest in AROW.findall(body):
    cells = [c.strip() for c in split_escaped(rest)]
    # 칸 = 테마 / 크기 / 상태 / 종료 기준 (+ 끝 파이프 뒤 빈칸)
    if len(cells) < 4:
      problems.append(f"트랙 A `{ident}` 의 칸이 {len(cells)}개다 — 상태 칸을 특정할 수 없다")
      continue
    rows.append((ident, [cells[0], cells[2]]))
  return rows, problems


# ── 트랙의 열림 판정 ────────────────────────────────────────────────
# 흐름: 상태 셀(**마지막 칸**)에서 토큰 -> 닫힘 어휘에 없으면 열림
# 🔴 **원장(`open_count`)과 한 함수로 합치지 않는다** — 신호가 다르다. 원장은 «절» 이나
#    «행 토큰» 으로 갈리고(§C·§A·행마다), 트랙은 **전부 행 토큰**이다. 합치면 분기가 늘어
#    어느 쪽도 읽기 어려워진다(설계 판단 2026-10-06 · Architect 관점).
# 🔑 **상태를 마지막 칸으로 정규화해 수집한다** — 그래야 여기서 칸 위치를 추측하지 않는다.
#    트랙마다 열 수가 다르다(A 5열 · B 3열 · C 4열).
def track_open_count(rows: list[tuple[str, list[str]]], label: str) -> tuple[int, str | None]:
  """(열린 건수, 문제 메시지 또는 None). 상태 칸은 ``cells[-1]`` 이다.

  Args:
      rows: (ID, 셀 목록). 마지막 셀이 상태여야 한다.
      label: 실패 메시지에 쓰는 트랙 이름.

  Returns:
      (열린 건수, 문제 메시지 또는 None).
  """

  def token(cells: list[str]) -> str | None:
    found = STATUS_RE.search(cells[-1]) if cells else None
    return found.group(1) if found else None

  # 🔴 fail-closed — 토큰 없는 행이 하나라도 있으면 «열림» 수를 믿을 수 없다.
  #    트랙 표는 상태를 **이모지·산문**으로 말해 온 자리라, 이 검사가 그 복귀를 막는다.
  missing = [ident for ident, cells in rows if token(cells) is None]
  if missing:
    head = " · ".join(missing[:8]) + (" …" if len(missing) > 8 else "")
    return 0, f"상태 토큰이 없는 {label} {len(missing)}건 — {head}"
  return sum(1 for _, cells in rows if token(cells) not in CLOSED_TOKENS), None


# ── 트랙 B 구간 잘라내기 ─────────────────────────────────────────────
# 흐름: `## 트랙 B` 부터 **다음 `## `** 까지 — 하위 절(`###`·`####`)은 그 안에 남긴다
# 🔴 예전엔 `split("###")[0]` 로 잘랐는데, 트랙 B 머리에 `####` 대응표가 들어오자
#    **표 앞에서 잘려 B 를 0건**으로 셌다(2026-09-23, 문서-13). 앵커 없는 분할이다(D47).
def track_b_block(roadmap: str) -> str:
  """`## 트랙 B` 절 전체를 돌려준다.

  Args:
      roadmap: `ROADMAP.md` 전문.

  Returns:
      그 절의 본문. 없으면 빈 문자열.
  """
  marker = "## 트랙 B"
  if marker not in roadmap:
    return ""
  rest = roadmap.split(marker, 1)[1]
  following = re.search(r"(?m)^## ", rest)
  return rest[: following.start()] if following else rest


# ── 색인 본문 생성 ──────────────────────────────────────────────────
# 흐름: 5개 원장 긁기 -> 바닥값 대조 -> 마크다운 조립
def build() -> tuple[str, dict[str, int], dict[str, int], list[str]]:
  """(색인 본문, 원장별 등재 수, 원장별 열림 수, 문제 목록)."""
  qa = scrape("FOLLOWUP_QUEUE.md", "QA-")
  docs = scrape("DOC_TRUTH_DRIFT.md", "문서-")
  local = scrape("LOCAL_RESIDUE.md", "L-")

  roadmap_body = (PRIVATE / "ROADMAP.md").read_text(encoding="utf-8", errors="replace")
  tracks = sorted(
    {
      ident: [c.strip() for c in split_escaped(rest) if c.strip()]
      for ident, rest in ROW.findall(roadmap_body)
      if re.match(r"^(OCR|C|ARCH)-\d+$", ident)
    }.items(),
    key=lambda kv: (kv[0].split("-")[0], int(kv[0].split("-")[1])),
  )
  # 🔴 `tidy()` 를 걸지 않는다 — 백틱이 지워져 상태 토큰을 못 읽는다. 축약은 `table()` 몫이다.
  btrack = [(f"B-{num}", [title, state]) for num, title, state in BSTEP.findall(track_b_block(roadmap_body))]
  atrack, problems = collect_track_a(roadmap_body)

  counts = {
    "QA": len(qa),
    "문서": len(docs),
    "L": len(local),
    "A": len(atrack),
    "ROADMAP": len(tracks),
    "B": len(btrack),
  }
  opens: dict[str, int] = {}
  for key, rows in (("QA", qa), ("문서", docs), ("L", local)):
    opened, why = open_count(rows, key)
    opens[key] = opened
    if why:
      problems.append(why)
  # 🔑 트랙은 **별 판정기**로 센다(신호가 다르다 — 전부 행 토큰이다). 2026-10-06 `문서-55`.
  for key, rows, label in (
    ("A", atrack, "트랙 A"),
    ("ROADMAP", tracks, "트랙 C·OCR·ARCH"),
    ("B", btrack, "트랙 B"),
  ):
    opened, why = track_open_count(rows, label)
    opens[key] = opened
    if why:
      problems.append(why)

  out = [
    "<!-- doc-meta",
    "kind:     queue",
    "status:   current",
    "note:     🤖 생성물이다 — 손으로 고치지 않는다. 원장을 고치고 다시 생성한다.",
    "-->",
    "",
    "# 후속 과제 색인 (FOLLOWUP INDEX)",
    "",
    "> 🤖 **이 문서는 `scripts/gates/doc/build_followup_index.py` 가 만든다.**",
    "> **손으로 고치지 말 것** — 다음 생성에서 통째로 덮인다. 고칠 곳은 **원장**이다.",
    "> `pre-push` 게이트가 *생성물 == 커밋된 것*을 대조한다 — 원장만 고치고 다시 생성하지 않으면",
    "> **push 가 막힌다.**",
    ">",
    "> 🔴 **이 색인은 *표에 적힌 것*을 옮길 뿐 내용을 판정하지 않는다.** 표가 거짓이면 색인도 거짓이다.",
    "> 그리고 여기 **없는 ID 체계**가 있다 — `R##`(안전망 규칙) · `V-A`~`V-H`(헛된초록 유형) ·",
    "> `S1`·`S2`…(PLAN 지역 ID) · `D##`(실수 대장). 후속 *과제*가 아니라서 범위 밖이다.",
    "> 접두사 등록부 = `FILING.md` §3-3.",
    ">",
    "> 📤 **닫힌 항목은 여기 없다** — 원장이 항목 배출형이라 완료분은 축 폴더로 내려간다.",
    "> QA 완료분 = `record/2026-09-21_qa-completed-record.md`. **ID 는 영구·재사용 금지**라,",
    "> 여기서 번호가 비어 보여도 그 번호는 회수되지 않는다.",
    "",
    "---",
    "",
  ]

  def table(title: str, rows: list[tuple[str, list[str]]], ledger: str) -> None:
    out.append(f"## {title} — {len(rows)}건")
    out.append("")
    out.append(f"> 원장 = `{ledger}`")
    out.append("")
    out.append("| ID | 내용 |")
    out.append("|---|---|")
    for ident, cells in rows:
      shown = [c for c in cells if c and c != "—" and not c.startswith("§절=")]
      body = " · ".join(tidy(c, 110) for c in shown[:3])
      out.append(f"| **{ident}** | {body} |")
    out.append("")

  table("🧪 QA — 테스트·검증·게이트", qa, "docs-private/FOLLOWUP_QUEUE.md")
  table("📄 문서-N — 문서↔현실 어긋남", docs, "docs-private/DOC_TRUTH_DRIFT.md")
  table("💾 L-N — git 밖 로컬 잔재", local, "docs-private/LOCAL_RESIDUE.md")
  table("🚀 트랙 A — 제품 (v2.x)", atrack, "docs-private/ROADMAP.md")
  table("🗺️ 트랙 C · OCR · ARCH", tracks, "docs-private/ROADMAP.md")
  table("🧱 트랙 B — 정리·강화", btrack, "docs-private/ROADMAP.md")

  ledger_keys = ("QA", "문서", "L")
  track_keys = ("A", "ROADMAP", "B")
  ledger_open = sum(opens[k] for k in ledger_keys)
  track_open = sum(opens[k] for k in track_keys)
  ledger_total = sum(counts[k] for k in ledger_keys)
  track_total = sum(counts[k] for k in track_keys)

  out += [
    "---",
    "",
    "## 합계",
    "",
    "| 원장 | 등재 | **열림** | 바닥값 |",
    "|---|---:|---:|---:|",
    *[f"| {k} | {v} | {opens[k]} | {FLOORS[k]} |" for k, v in counts.items()],
    f"| **원장 소계**(QA·문서·L) | {ledger_total} | **{ledger_open}** | |",
    f"| **트랙 소계**(A·B·C) | {track_total} | **{track_open}** | |",
    f"| **총합** | **{sum(counts.values())}** | **{sum(opens.values())}** | |",
    "",
    '> 🔢 **바닥값 아래로 떨어지면 게이트가 막는다** — *0건은 "없다"가 아니라 "못 셌다"이다.*',
    "> 줄어든 것도 실패로 본다(대장 **D31** — `check_utf8_guard` 가 11건→1건이 되고도 초록이었다).",
    ">",
    "> 🔑 **소계를 둘로 가른 이유**: 🧱 `check_doc_markers` 의 `ledger-open` 마커가 담는 것은",
    "> **원장 소계**다. 둘을 한 수로 합치면 그 마커가 무엇을 뜻하는지 알 수 없어진다 —",
    "> *«열린 것 전체»* 라고 부르면서 트랙을 손으로 유지하다 하루에 네 번 썩은 자리가 그것이다",
    "> (`문서-44` · B-15). **이름이 담는 범위를 표가 보여 준다.**",
    ">",
    "> 🆕 **2026-10-06 — 트랙 A·B·C 를 세기 시작했다**(`문서-55`). 그전까지 이 칸은 `—` 였다:",
    "> 트랙 표가 상태를 **이모지·산문**으로 말해 `🔶 2구간 완료 … 3구간 남음` 처럼 *«완료» 가",
    "> 들어 있는데 열려 있는* 행이 있었다(`D47`). 43행을 **행마다 사람이 판정**해 텍스트 어휘로",
    "> 바꾸고 나서야 셀 수 있게 됐다.",
    "",
  ]
  return "\n".join(out), counts, opens, problems


def main() -> int:
  """생성 또는 대조."""
  parser = argparse.ArgumentParser(description="후속 과제 색인 생성/대조")
  parser.add_argument("--check", action="store_true", help="쓰지 않고 대조만 한다(게이트 모드)")
  args = parser.parse_args()

  content, counts, opens, problems = build()

  # 🔴 열림을 «못 셌다» 면 그 수를 인쇄하지 않는다 — 0 을 답으로 내면 거짓 안심이다.
  if problems:
    print("[거부] 열림/닫힘을 셀 수 없다 — 상태 어휘가 빠졌다.", file=sys.stderr)
    for line in problems:
      print(f"  - {line}", file=sys.stderr)
    # 🔴 어휘를 여기 베끼지 않는다 — 상수에서 만든다. 베끼면 어휘가 늘 때 이 줄만 낡는다
    #    (실제로 `보류` 를 추가하자 이 줄이 즉시 거짓이 됐다, B-15 S4).
    allowed = "·".join(f"`{t}`" for t in sorted(STATUS_TOKENS))
    print(f"  값은 {allowed} 중 하나다(FILING).", file=sys.stderr)
    return 1

  low = {k: v for k, v in counts.items() if v < FLOORS[k]}
  if low:
    print("\n[거부] 원장에서 항목을 기대보다 적게 셌다 — 패턴이나 경로가 어긋났다.", file=sys.stderr)
    for key, got in low.items():
      print(f"  - {key}: {got}건 (기대 최소 {FLOORS[key]})", file=sys.stderr)
    print("  0건은 '없다' 가 아니라 '못 셌다' 이다(fail-closed).\n", file=sys.stderr)
    return 1

  tally = " · ".join(f"{k} {v}" + (f"(열림 {opens[k]})" if k in opens else "") for k, v in counts.items())

  if args.check:
    current = INDEX.read_text(encoding="utf-8", errors="replace") if INDEX.exists() else ""
    if current != content:
      print("\n[거부] 후속 과제 색인이 원장과 어긋난다.", file=sys.stderr)
      print("  원장을 고쳤으면 색인도 같은 동작으로 다시 만든다:", file=sys.stderr)
      print("    uv run python -m scripts.gates.doc.build_followup_index\n", file=sys.stderr)
      return 1
    print(f"✅ 후속 과제 색인 정합 — {tally} · 총 {sum(counts.values())}건.")
    return 0

  INDEX.write_text(content, encoding="utf-8", newline="\n")
  print(f"✅ 생성 — {INDEX.name} · {tally} · 총 {sum(counts.values())}건.")
  return 0


if __name__ == "__main__":
  sys.exit(main())
