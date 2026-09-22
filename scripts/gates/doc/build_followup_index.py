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

INDEX = PRIVATE / "FOLLOWUP_INDEX.md"

#: 표 행 — 줄 머리에 `| **<ID>** |` 가 와야 한다.
#: ⚠️ ID 뒤에 제목이 **같은 굵게 안에** 들어오는 행이 있다 — `| **C-7 챗봇 개인화 툴** |`.
#:    `\*\*ID\*\*` 로 닫으면 그런 행 6개가 통째로 안 보인다(바닥값이 잡았다).
ROW = re.compile(r"^\|\s*\*\*([A-Z가-힣]+-?\d+)[^*|]*\*\*[^|]*\|(.*)$", re.MULTILINE)
#: 제목형 항목 — `### QA-01 — 제목`
HEAD = re.compile(r"^#{2,4}\s+(QA-\d+|문서-\d+)\s*[—-]\s*(.+)$", re.MULTILINE)
#: 트랙 B 의 단계 표 — `| 9 | **문서 정독·분류** | 🔵 진행 중 |`
BSTEP = re.compile(r"^\|\s*\*{0,2}(\d{1,2})\*{0,2}\s*\|([^|]+)\|([^|]*)\|", re.MULTILINE)

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
FLOORS = {"QA": 41, "문서": 31, "L": 11, "ROADMAP": 19, "B": 14}


def tidy(text: str, limit: int = 150) -> str:
    """표 셀에서 장식을 걷고 한 줄로 줄인다."""
    clean = NOISE.sub("", text).replace("|", "/").strip()
    clean = re.sub(r"\s+", " ", clean)
    return clean[:limit] + ("…" if len(clean) > limit else "")


# ── 원장 하나에서 항목을 긁는다 ─────────────────────────────────────
# 흐름: 파일 읽기 -> 줄머리 앵커로 표 행·제목형 수집 -> (ID, 셀들) 목록
def scrape(filename: str, prefix: str) -> list[tuple[str, list[str]]]:
    """(ID, 셀 목록). `prefix` 로 시작하는 ID 만 남긴다."""
    path = PRIVATE / filename
    body = path.read_text(encoding="utf-8", errors="replace")
    items: dict[str, list[str]] = {}
    for ident, rest in ROW.findall(body):
        if ident.startswith(prefix):
            items.setdefault(ident, [c.strip() for c in rest.split("|") if c.strip()])
    for ident, title in HEAD.findall(body):
        if ident.startswith(prefix):
            items.setdefault(ident, [title.strip()])
    return sorted(items.items(), key=lambda kv: int(re.sub(r"\D", "", kv[0]) or 0))


# ── 색인 본문 생성 ──────────────────────────────────────────────────
# 흐름: 5개 원장 긁기 -> 바닥값 대조 -> 마크다운 조립
def build() -> tuple[str, dict[str, int]]:
    """(색인 본문, 원장별 건수)."""
    qa = scrape("FOLLOWUP_QUEUE.md", "QA-")
    docs = scrape("DOC_TRUTH_DRIFT.md", "문서-")
    local = scrape("LOCAL_RESIDUE.md", "L-")

    roadmap_body = (PRIVATE / "ROADMAP.md").read_text(encoding="utf-8", errors="replace")
    tracks = sorted(
        {
            ident: [c.strip() for c in rest.split("|") if c.strip()]
            for ident, rest in ROW.findall(roadmap_body)
            if re.match(r"^(OCR|C|ARCH)-\d+$", ident)
        }.items(),
        key=lambda kv: (kv[0].split("-")[0], int(kv[0].split("-")[1])),
    )
    btrack = [
        (f"B-{num}", [tidy(title), tidy(state, 60)])
        for num, title, state in BSTEP.findall(roadmap_body.split("## 트랙 B")[1].split("###")[0])
    ]

    counts = {"QA": len(qa), "문서": len(docs), "L": len(local), "ROADMAP": len(tracks), "B": len(btrack)}

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
            body = " · ".join(tidy(c, 110) for c in cells[:3] if c and c != "—")
            out.append(f"| **{ident}** | {body} |")
        out.append("")

    table("🧪 QA — 테스트·검증·게이트", qa, "docs-private/FOLLOWUP_QUEUE.md")
    table("📄 문서-N — 문서↔현실 어긋남", docs, "docs-private/DOC_TRUTH_DRIFT.md")
    table("💾 L-N — git 밖 로컬 잔재", local, "docs-private/LOCAL_RESIDUE.md")
    table("🗺️ 트랙 C · OCR · ARCH", tracks, "docs-private/ROADMAP.md")
    table("🧱 트랙 B — 정리·강화", btrack, "docs-private/ROADMAP.md")

    out += [
        "---",
        "",
        "## 합계",
        "",
        "| 원장 | 건수 | 바닥값 |",
        "|---|---:|---:|",
        *[f"| {k} | {v} | {FLOORS[k]} |" for k, v in counts.items()],
        f"| **총합** | **{sum(counts.values())}** | |",
        "",
        '> 🔢 **바닥값 아래로 떨어지면 게이트가 막는다** — *0건은 "없다"가 아니라 "못 셌다"이다.*',
        "> 줄어든 것도 실패로 본다(대장 **D31** — `check_utf8_guard` 가 11건→1건이 되고도 초록이었다).",
        "",
    ]
    return "\n".join(out), counts


def main() -> int:
    """생성 또는 대조."""
    parser = argparse.ArgumentParser(description="후속 과제 색인 생성/대조")
    parser.add_argument("--check", action="store_true", help="쓰지 않고 대조만 한다(게이트 모드)")
    args = parser.parse_args()

    content, counts = build()

    low = {k: v for k, v in counts.items() if v < FLOORS[k]}
    if low:
        print("\n[거부] 원장에서 항목을 기대보다 적게 셌다 — 패턴이나 경로가 어긋났다.", file=sys.stderr)
        for key, got in low.items():
            print(f"  - {key}: {got}건 (기대 최소 {FLOORS[key]})", file=sys.stderr)
        print("  0건은 '없다' 가 아니라 '못 셌다' 이다(fail-closed).\n", file=sys.stderr)
        return 1

    tally = " · ".join(f"{k} {v}" for k, v in counts.items())

    if args.check:
        current = INDEX.read_text(encoding="utf-8", errors="replace") if INDEX.exists() else ""
        if current != content:
            print("\n[거부] 후속 과제 색인이 원장과 어긋난다.", file=sys.stderr)
            print("  원장을 고쳤으면 색인도 같은 동작으로 다시 만든다:", file=sys.stderr)
            print("    uv run python -m scripts.gates.doc.build_followup_index\n", file=sys.stderr)
            return 1
        print(f"✅ 후속 과제 색인 정합 — {tally} · 총 {sum(counts.values())}건.")
        return 0

    INDEX.write_text(content, encoding="utf-8")
    print(f"✅ 생성 — {INDEX.name} · {tally} · 총 {sum(counts.values())}건.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
