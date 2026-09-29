"""`PreToolUse` 훅 — **읽기를 «결정» 에서 «전제조건» 으로 바꾼다** (트랙 B-10).

왜 훅이어야 하나
----------------
이 저장소의 장치는 거의 전부 **사후**다 — `pre-commit`·`pre-push` 는 일을 끝낸 뒤 막는다.
사전 장치는 `CLAUDE.md`(층②, 매 턴 토큰)와 저장소 문서(층⑤, **`Read` 를 불러야만**)뿐이다.

> *"필요할 때 읽어라"* 는 **이미 아는 사람에게만 작동한다.** 읽어야 할 상황임을 알려면
> 그걸 읽어야 알기 때문이다 — **순환**이다(대장 **D38** 이 그 실증: 규칙을 쓴 다음 턴에 어겼다).

**`PreToolUse` 만이 «사전 + 판단 불필요» 칸을 채운다.**

무엇을 하나
-----------
1. `Read` 로 **라우팅 문서**를 열면 → 세션 마커를 남긴다(조용히 통과).
2. `Write`/`Edit` 로 **`docs-private/**.md`** 를 고치려 하면
   → 마커가 없으면 **deny + 어디를 읽어라**, 있으면 통과하며 **상시 세트를 주입**한다.

훅은 **1종**이다(`matcher` 하나). 안에서 `tool_name` 으로 분기한다 — 계승 계획의
정지 규칙(*훅을 여러 개 만들지 않는다. 1종으로 시작해 오탐을 재고 늘린다*)을 지킨다.

🔴 이 훅이 **못 하는 것** (한계 선언)
--------------------------------------
- **읽은 «내용» 을 모른다.** `Read` 를 불렀다는 사실만 안다 — 훑었는지 정독했는지는 모른다.
- **통째로 꺼질 수 있다**(`disableAllHooks`·관리 정책). 그래서 **최소 핵 8줄은 `CLAUDE.md`
  본문에 상주**시켜 훅과 무관하게 살게 했다. 훅에 «전부» 를 걸지 않는다.
- **성공은 보이지 않는다** — UI 는 훅이 실패하거나 느릴 때만 표시한다. *"돌았나"* 는 따로 재야 한다.
- **자기 배선을 스스로 못 본다** → `scripts/gates/tooling/check_claude_hooks.py` 가 pre-push 에서 센다.
- ✅ **압축은 이제 보증을 무른다**(`QA-50` 해소, 2026-09-29). 앞 판은 «읽었다는 사실» 만 남기고
  압축을 넘겼는데, **읽은 «내용» 은 요약에서 탈락한다**(2026-09-22 실측: 압축 요약에 본문 0줄).
  🔑 **공짜로 돌아오지도 않는다** — 압축이 되돌려주는 것은 최근 수정 5개까지이고,
  5,000토큰 넘는 파일은 **경로만** 온다. 직하 정본은 전부 그 선을 넘는다(`문서-46`).
  ⇒ `PostCompact` 가 읽음 마커에 **«압축됨» 을 새긴다.** 다음 편집은 **막히고**,
  이유를 *«한 번도 안 읽었다»* 와 **다른 문장**으로 말한다.
- 🔴 **여전히 읽은 «내용» 은 모른다.** `Read` 호출 사실만 안다 — 훑었는지 정독했는지는 모른다.

🟡 **내부 오류가 나면 «통과» 시킨다(fail-open).** 의도된 선택이다 —
버그로 전부 막히면 **사람이 훅을 통째로 끄고, 그러면 검출률이 0 이 된다**(`QUALITY_GATES` §2-8).
대신 오류를 `systemMessage` 로 **드러낸다.** 조용히 실패하지는 않는다.
"""

import json
import os
from pathlib import Path
import sys
import tempfile

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

REPO_ROOT = Path(__file__).resolve().parents[2]
MARKER_ROOT = Path(tempfile.gettempdir()) / "doseph-read-precondition"

# 읽어야 통과하는 문서 — 키는 마커 이름, 값은 파일명 조각.
GATED_DOC = "FILING.md"
# 「상시 세트를 이미 주입했다」 기록. `PostCompact` 가 이것을 지운다.
INJECTED = "상시세트-주입됨"
# 🔴 읽음 마커에 새기는 «압축됨» 표식(`QA-50`). **지우지 않고 표시하는 이유**는
#    「한 번도 안 읽었다」 와 「읽었는데 압축이 내용을 지웠다」 를 **다른 메시지로** 말하기 위해서다.
#    지워 버리면 둘이 같은 모양이 되고, 읽는 사람은 왜 막혔는지 모른다.
COMPACTED = "compacted"
# 규약 밖 구역은 묻지 않는다(미분류·죽은 문서를 옮기는 일이 막히면 오탐이 된다).
EXEMPT_PARTS = ("/_unfiled/", "/_legacy/")


# ── 세션 마커 ────────────────────────────────────────────────────────
# 흐름: session_id 로 디렉터리 -> 읽은 문서 이름으로 빈 파일
# 세션이 끝나면 임시 디렉터리와 함께 자연히 사라진다(상태를 저장소에 남기지 않는다).
def marker_path(session_id: str, name: str) -> Path:
    """세션·문서별 마커 경로를 만든다.

    Args:
        session_id: 훅 입력의 `session_id`.
        name: 문서 이름.

    Returns:
        마커 파일 경로.
    """
    safe = "".join(c for c in session_id if c.isalnum() or c in "-_")[:64] or "nosession"
    return MARKER_ROOT / safe / name


def deny(reason: str) -> dict[str, object]:
    """편집을 막는 훅 출력.

    Args:
        reason: 사람에게 보일 이유. **막힌 까닭마다 다른 문장**이어야 한다.

    Returns:
        훅 출력 dict.
    """
    return {
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": "deny",
            "permissionDecisionReason": reason,
        }
    }


def decide(payload: dict[str, object]) -> dict[str, object] | None:
    """훅 입력을 보고 통과·차단·주입을 정한다.

    Args:
        payload: stdin 으로 온 훅 입력.

    Returns:
        훅 출력 dict. `None` 이면 아무 말 없이 통과.
    """
    tool = str(payload.get("tool_name", ""))
    session = str(payload.get("session_id", ""))
    raw_input = payload.get("tool_input")
    tool_input: dict[str, object] = raw_input if isinstance(raw_input, dict) else {}
    path = str(tool_input.get("file_path", "")).replace("\\", "/")

    # ① Read — 라우팅 문서를 열었으면 기록만 하고 빠진다.
    if tool == "Read":
        if path.endswith(GATED_DOC):
            m = marker_path(session, GATED_DOC)
            m.parent.mkdir(parents=True, exist_ok=True)
            # 🔑 `touch()` 가 아니라 **비운다** — 앞서 새겨진 «압축됨» 을 걷어내야 한다(`QA-50`).
            m.write_text("", encoding="utf-8")
        return None

    # ② Write/Edit — docs-private 의 문서를 고칠 때만 묻는다.
    if tool not in ("Write", "Edit"):
        return None
    if "/docs-private/" not in path or not path.endswith(".md"):
        return None
    if any(part in path for part in EXEMPT_PARTS):
        return None

    marker = marker_path(session, GATED_DOC)
    if marker.exists():
        if marker.read_text(encoding="utf-8", errors="replace").strip() == COMPACTED:
            return deny(
                f"**압축 이후 첫 `docs-private/` 편집이다 — docs-private/{GATED_DOC} 를 다시 읽어라.** "
                "🔴 읽었다는 «사실» 은 남았지만 읽은 «내용» 은 압축 요약에서 탈락한다"
                "(2026-09-22 실측: 압축 요약에 본문 0줄). "
                "그리고 압축이 되돌려주는 것은 최근 수정 5개까지이고 5,000토큰 넘는 정본은 «경로만» 온다 — "
                "**본문이 공짜로 돌아오는 경우는 없다**(`QA-50` · `문서-46`)."
            )
        # 🔴 상시 세트는 **세션당 한 번만** 주입한다.
        #    한 번 들어오면 이미 컨텍스트에 있으므로 같은 340자를 매 편집마다 다시 넣는 것은
        #    순수한 낭비다(실측: 25회 편집 = 약 7,000 토큰 → 1회 = 약 283 토큰).
        #    ⚠️ **대가**: 압축 이후에는 주입분이 컨텍스트에서 사라지는데 마커는 남는다.
        #    → **`PostCompact` 훅이 `--reset-injection` 으로 이 마커를 지운다**(2026-09-22, B-10 2구간).
        #    그래도 훅이 통째로 꺼진 경우엔 **최소 핵 8줄(`CLAUDE.md` §6-5)**이 그 공백을 받는다.
        injected = marker_path(session, INJECTED)
        if injected.exists():
            return None
        injected.parent.mkdir(parents=True, exist_ok=True)
        injected.touch()
        return {
            "hookSpecificOutput": {
                "hookEventName": "PreToolUse",
                "additionalContext": (
                    "★ 상시 세트(대장 상단) — 무엇을 하든 걸린다: "
                    "D31 즉석 grep 으로 정본 검증기를 뒤집지 않는다 · "
                    "D43 «몇 건인가» 는 질문이 덜 된 질문이다(세는 대상을 먼저) · "
                    "D47 구조를 문자열로 세지 않는다(단위를 붙인다) · "
                    "D52 세기 전에 기대 범위를 먼저 말한다 · "
                    "D58 빈칸에 이름 붙이기 전에 그 자리를 열어 본다 · "
                    "D13 소스를 안 읽고 도구 동작을 단정하지 않는다 · "
                    "D14 인과 사슬의 한 고리만 보고 «원인» 이라 하지 않는다 · "
                    "D17 «다 기록했나» 는 두 패스다(내 변경이 기존을 거짓으로 만들었나). "
                    "지금은 문서를 고치는 중이니 축 `문서-닫기` 도 함께 본다."
                ),
            }
        }

    return deny(
        f"`docs-private/` 문서를 고치기 전에 **docs-private/{GATED_DOC}** 를 먼저 읽어라 "
        "(§3-1: 파일명은 «모양» 만 보증한다 — 정독 없이 분류하지 않는다, 대장 D38). "
        "그리고 실수 대장의 축 `문서-닫기` 를 함께 본다."
    )


# ── `PostCompact` — 압축이 컨텍스트를 갈아엎었으니 주입 기록을 무른다 ──
# 흐름: 세션 마커 폴더 -> «주입됨» 만 삭제 -> 다음 PreToolUse 가 다시 주입
# 🔑 **«읽음» 마커는 지우지 않고 «압축됨» 으로 새긴다**(`QA-50` 해소, 2026-09-29).
#    앞 판의 설계 근거는 *"읽었다는 사실은 압축으로 변하지 않는다"* 였는데 **반쪽만 참**이었다:
#    `Read` 를 불렀다는 사실은 남지만 **읽은 내용은 요약에서 탈락한다**(2026-09-22 실측).
#    ⇒ 막는 것이 **오탐이 아니라 정탐**이다 — 내용이 실제로 사라졌다.
#    🔑 **지우지 않는 이유**: 지우면 «한 번도 안 읽었다» 와 같은 모양이 되어 **왜 막혔는지 못 말한다.**
#    🔢 **비용은 피할 수 있는 것이 아니다**(`문서-46`): 압축이 되돌려주는 것은 최근 수정 5개까지이고
#    5,000토큰 넘는 정본은 **경로만** 온다 — 정본 본문이 공짜로 돌아오는 경우는 없다.
#    지금까지는 그 비용을 **안 내고 통과**하고 있었던 것이다.
# 🔴 왜 직접 주입하지 않나: `PostCompact` 가 `additionalContext` 를 지원하는지
#    **실측하지 않았다.** 이 방식은 훅이 **돌기만** 하면 되므로 그 미지수에 기대지 않는다.
def reset_after_compaction(session_id: str) -> int:
    """압축 후 «주입됨» 을 지우고 «읽음» 에 압축 표식을 새긴다.

    Args:
        session_id: 훅 입력의 `session_id`. 비어 있으면 모든 세션을 훑는다.

    Returns:
        종료코드 — 항상 0.
    """
    if session_id:
        folders = [marker_path(session_id, INJECTED).parent]
    else:
        folders = [p for p in MARKER_ROOT.glob("*") if p.is_dir()]
    for folder in folders:
        (folder / INJECTED).unlink(missing_ok=True)  # 없어도 죽지 않는다 — 압축이 두 번 와도 안전
        read_marker = folder / GATED_DOC
        if read_marker.exists():
            read_marker.write_text(COMPACTED, encoding="utf-8")
    return 0


def main() -> int:
    """Stdin 을 읽어 판정하고 stdout 으로 답한다.

    Returns:
        종료코드 — 항상 0. 차단은 종료코드가 아니라 `permissionDecision` 으로 한다.
    """
    try:
        payload = json.loads(sys.stdin.read() or "{}")
        # 🔤 `--reset-injection` 은 **과도기 별칭**이다(2026-09-29 개명, `QA-50`).
        #    이제 주입 기록만이 아니라 **읽음 보증까지** 무르므로 옛 이름이 거짓이 됐다.
        #    🔴 설정 감시자는 세션 시작 시점의 설정을 들고 있어, 옛 이름이 한동안 더 올 수 있다.
        if {"--after-compact", "--reset-injection"} & set(sys.argv):
            return reset_after_compaction(str(payload.get("session_id", "")) if isinstance(payload, dict) else "")
        out = decide(payload if isinstance(payload, dict) else {})
    except Exception as exc:
        json.dump({"systemMessage": f"⚠️ read-precondition 훅 내부 오류(통과시킴): {exc}"}, sys.stdout)
        return 0
    if out is not None:
        json.dump(out, sys.stdout, ensure_ascii=False)
    return 0


if __name__ == "__main__":
    os.environ.setdefault("PYTHONIOENCODING", "utf-8")
    sys.exit(main())
