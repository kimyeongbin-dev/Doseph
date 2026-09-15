# 부채 원장 — 삭제 의미론이 주석과 다르다

> 2026-09-15 개설. **C12-b(DB 테스트 층)를 만들다가 발견.** 둘 다 mock 기반
> 테스트로는 구조적으로 발견할 수 없던 것들이다 — mock 은 "그 메서드가 호출됐는가"만
> 보는데, 두 건 모두 **호출은 정확히 일어났고 결과가 주석과 달랐다.**

| 상태 | 2건 미해결 → **QA-01** · **QA-02** (정본 = `docs-private/TEST_FOLLOWUP_QUEUE.md`) |
|---|---|
| 발견 경로 | `app/tests/db/test_db_cascade.py` — 진짜 행을 만들고 지워본 결과 |
| 공통점 | **사용자에게 보이는 결과는 맞다.** 어긋난 것은 *메커니즘*과 *주석* |

---

## 왜 이걸 원장에 올리나

둘 다 "지금 당장 사용자가 피해를 본다"가 아니다. 그래서 더 위험하다 —
**고칠 이유가 급하지 않은 채로 주석만 거짓으로 남는다.** 다음 사람이 그 주석을
믿고 코드를 고치면 그때 사고가 난다.

그리고 둘 다 **판단이 필요한 behavior 결정**이라 테스트 커밋에 섞을 수 없었다.
`fix` 단위로 분리한다(CLAUDE.md §5.2).

---

## QA-01 (구 1-i). 미시작 챌린지는 soft delete 되지 않는다 (hard delete 된다)

**위치**: `app/services/lifestyle_guide_service.py` `_cascade_delete_guide`

**주석이 말하는 것**
```
- 활성/완료 챌린지: guide_id=None 으로 분리만 (사용자 진행분 보존)
- 미시작 챌린지: soft-delete
```

**실제로 일어나는 일**
```python
for c in challenges:
    if not c.is_active:
        await self.challenge_repo.soft_delete(c)   # deleted_at 설정 — 행은 아직 guide_id 를 가리킴
    else:
        await Challenge.filter(id=c.id).update(guide_id=None)
await self.guide_repo.delete_by_id(guide.id)        # ← 가이드를 **hard delete**
```

`challenges.guide_id` 의 FK 가 **`ON DELETE CASCADE`** 다
(`0_20260911135245_init.py:297`). 그래서 가이드가 물리적으로 지워지는 순간,
방금 soft delete 한 챌린지 행도 **DB 가 같이 물리 삭제**한다.

> **soft delete 가 한 줄 뒤의 hard delete 에 덮인다.**

**왜 mock 이 못 잡았나**: mock 테스트는 `soft_delete` 가 호출됐는지만 봤다.
호출은 정확히 일어났다. 그 다음 줄이 결과를 지운다는 것은 **진짜 FK 가 있어야**
관측된다.

**영향**
- 사용자 눈에 보이는 결과는 같다(챌린지가 사라진다) → 지금 당장의 버그는 아님
- 다만 soft delete 의 목적(복구·감사)이 이 경로에선 **존재하지 않는다**
- `soft_delete` 호출은 **죽은 작업**이다
- 가이드를 soft delete 로 바꾸는 미래 변경이 들어오면 동작이 조용히 달라진다

**선택지**
| # | 방향 | 결과 |
|---|---|---|
| A | 주석·구현을 **현실에 맞춘다** — 미시작 챌린지는 FK cascade 로 정리됨을 명시하고 `soft_delete` 호출 제거 | 가장 작음. 복구 여지는 계속 없음 |
| B | `guide_id` FK 를 `ON DELETE SET NULL` 로 바꾸고 soft delete 를 살린다 | 마이그레이션 필요. 의도대로 동작 |
| C | 가이드도 soft delete 로 | 파급 큼(조회 경로 전부 필터 필요) |

**잠금 상태**: `test_cascade_removes_unstarted_challenges_but_keeps_started_ones` 가
현재 계약("행이 없다")을 잠그고 있다. 방향을 정하면 그 단언도 함께 조인다.

---

## QA-02 (구 1-j). 탈퇴 시 refresh token 은 hard delete 가 아니라 soft revoke 다

**위치**: `app/services/oauth.py` `delete_account` / `refresh_token_repository.revoke_all_for_account`

**주석이 말하는 것**
```python
# 1) refresh_tokens hard-delete (보안 우선)
await self.refresh_token_repo.revoke_all_for_account(account.id)
```

**실제로 일어나는 일**
```python
updated = await RefreshToken.filter(account_id=account_id, is_revoked=False).update(is_revoked=True)
```

`is_revoked=True` 로 표시만 한다. **행은 남는다** — `token_hash` 포함.

**영향**
- 인증 관점에서는 안전하다(폐기된 토큰은 갱신에 쓸 수 없다)
- 하지만 **탈퇴한 계정의 토큰 해시가 DB 에 계속 남는다**. 탈퇴는 "내 흔적을 지워
  달라"는 요청이라 데이터 보존 정책 관점의 판단이 필요하다
- 주석이 "hard-delete" 라고 단언하고 있어, 이걸 근거로 다른 판단을 내릴 위험이 있다

**선택지**
| # | 방향 | 결과 |
|---|---|---|
| A | 탈퇴 경로에서만 **실제 hard delete** 로 (`.delete()`) | 주석과 일치. 로그아웃 경로의 revoke 는 그대로 |
| B | 주석을 현실에 맞게 고친다 | 가장 작음. 보존 문제는 남음 |
| C | 보존 기간 뒤 정리하는 배치 | 과함 |

**잠금 상태**: `test_account_withdrawal_cascades_everything` 이 실제 계약
("쓸 수 있는 토큰이 남지 않는다")을 잠그고 있다.

---

## 배운 것

> **mock 은 "우리가 호출한 것"을 검증하고, DB 는 "실제로 남은 것"을 검증한다.**
> 두 건 모두 호출은 완벽했다. 어긋난 건 그 다음에 DB 가 한 일이다.
> 소유한 시스템이라도 **경계 너머(FK 제약, 트리거, cascade)는 대역으로 대신할 수 없다.**

관련: `docs-private/study/schema-introspection-and-version-pinning.md` ·
`docs-private/study/test-doubles-stubs-seeds.md` · `docs/TESTING_SAFETY_NET_RULES.md`
