'use client'

// ChatSession 도메인 — TanStack Query adapter (PR-B 마이그레이션).
//
// 외부 API: sessions, activeSessionId, setActiveSessionId, isLoading,
// createSession, renameSession, deleteSession, refetchSessions.
//
// ⚠️ refetchSessions 는 **참조가 안정하고(매 렌더 안 바뀜) 최신 목록을 반환**한다.
//    호출자의 effect 의존성에 그대로 넣어도 안전하고, 반환값을 바로 쓰면
//    "재조회 -> 그 결과로 판단"을 한 흐름에서 끝낼 수 있다(ChatModal 초기화).
//    **조회 완료까지 기다리고, 실패하면 reject 한다** — 호출자의 catch 분기가
//    실제로 도달한다. (2026-09-14 이전에는 실패해도 resolve 했고, 관찰자가 붙기 전
//    호출이면 아무것도 기다리지 않아서 ChatModal 의 재시도 UI 가 렌더될 수 없는
//    죽은 코드였다. 후속 큐 1-e.)

import { createContext, useCallback, useContext, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'

import api from '@/lib/api'
import { useProfile } from '@/contexts/ProfileContext'
import { qk, STALE } from '@/queries/keys'

const ChatSessionContext = createContext(null)

// ── 세션 목록 조회 fn (queryKey 공유자 전원이 같이 쓴다) ──────────────
// 흐름: profileId -> GET /chat-sessions -> 세션 배열
// Provider 의 useQuery 와 강제 동기화(refetchSessions)가 **같은 fn** 을 쓴다.
// 같은 queryKey 에 다른 fn 이 붙으면 나중에 등록된 쪽이 쓰여 동작이 등록 순서에
// 좌우된다(처방전 상세에서 실제로 겪은 함정).
async function fetchChatSessionsRequest(profileId) {
  const res = await api.get('/api/v1/chat-sessions', {
    params: { profile_id: profileId },
  })
  return res.data || []
}

export function ChatSessionProvider({ children }) {
  const { selectedProfileId } = useProfile()
  const qc = useQueryClient()
  const [activeSessionId, setActiveSessionId] = useState(null)

  // ── 1) list query ─────────────────────────────────────────────────
  const listQuery = useQuery({
    queryKey: qk.chatSessions.list(selectedProfileId),
    enabled: !!selectedProfileId,
    staleTime: STALE.chatSessions,
    queryFn: () => fetchChatSessionsRequest(selectedProfileId),
  })
  const sessions = listQuery.data || []
  const isLoading = listQuery.isLoading

  // ── 프로필 전환 시 활성 세션 reset (렌더 중 조정) ──────────────────
  // 흐름: 직전 프로필 id 와 비교 -> 달라졌으면 활성 세션 해제
  // effect 로 하면 새 프로필 화면이 이전 프로필의 세션 id 로 한 번 그려진 뒤에야
  // 지워진다(그 한 번의 렌더에서 남의 세션 메시지를 조회할 수 있다).
  const [lastProfileId, setLastProfileId] = useState(selectedProfileId)
  if (lastProfileId !== selectedProfileId) {
    setLastProfileId(selectedProfileId)
    setActiveSessionId(null)
  }

  // ── 2) mutations ──────────────────────────────────────────────────
  const createMutation = useMutation({
    mutationFn: async ({ profileId, title }) => {
      const { data } = await api.post('/api/v1/chat-sessions', {
        profile_id: profileId,
        title,
      })
      return data
    },
    onSuccess: (created) => {
      qc.setQueryData(qk.chatSessions.list(selectedProfileId), (prev = []) => [created, ...prev])
    },
  })

  const renameMutation = useMutation({
    mutationFn: async ({ id, title }) => {
      const { data } = await api.patch(`/api/v1/chat-sessions/${id}`, { title })
      return data
    },
    onSuccess: (updated, { id }) => {
      qc.setQueryData(qk.chatSessions.list(selectedProfileId), (prev = []) =>
        prev.map((s) => (s.id === id ? { ...s, ...updated } : s)),
      )
    },
  })

  const deleteMutation = useMutation({
    mutationFn: async (id) => {
      await api.delete(`/api/v1/chat-sessions/${id}`)
      return id
    },
    onSuccess: (id) => {
      qc.setQueryData(qk.chatSessions.list(selectedProfileId), (prev = []) =>
        prev.filter((s) => s.id !== id),
      )
      qc.removeQueries({ queryKey: qk.chatSessions.detail(id) })
      qc.removeQueries({ queryKey: qk.chatSessions.messages(id) })
      setActiveSessionId((prev) => (prev === id ? null : prev))
    },
  })

  // 외부 호환 API.
  const createSession = useCallback(
    (profileId, title) => createMutation.mutateAsync({ profileId, title }),
    [createMutation],
  )
  const renameSession = useCallback(
    (id, title) => renameMutation.mutateAsync({ id, title }),
    [renameMutation],
  )
  const deleteSession = useCallback((id) => deleteMutation.mutateAsync(id), [deleteMutation])

  // ── 세션 목록 강제 동기화 ─────────────────────────────────────────
  // 흐름: fetchQuery 로 조회 완료까지 대기 -> 성공이면 최신 목록 반환 / 실패면 throw
  // `listQuery.refetch()` 는 매 렌더 새로 만들어지는 query 객체에 묶여 있어
  // 호출자의 effect 의존성을 흔든다. queryClient + key 로만 묶어 참조를 고정한다.
  //
  // ⚠️ 여기서 `refetchQueries` 를 쓰면 안 된다. 두 가지가 겹쳐 실패가 사라진다:
  //   (1) 쿼리가 실패해도 **resolve** 한다(throwOnError 를 켜야 throw).
  //   (2) 호출 시점에 **관찰자가 아직 붙지 않았으면 아무 일도 하지 않고** 즉시 resolve 한다.
  //       모달의 초기화 effect 는 자식이라 부모(Provider)의 쿼리 구독보다 **먼저** 돈다.
  //       그 결과 상태가 pending 인 채 `?? []` 로 흡수돼 "세션 0건"이 된다.
  // `fetchQuery` 는 조회가 끝날 때까지 기다리고(진행 중이면 dedupe) **실패 시 throw** 한다.
  const refetchSessions = useCallback(
    () =>
      qc.fetchQuery({
        queryKey: qk.chatSessions.list(selectedProfileId),
        queryFn: () => fetchChatSessionsRequest(selectedProfileId),
        // 강제 동기화가 목적이라 캐시가 신선해도 항상 다시 받는다.
        staleTime: 0,
      }),
    [qc, selectedProfileId],
  )

  return (
    <ChatSessionContext.Provider
      value={{
        sessions,
        activeSessionId,
        setActiveSessionId,
        isLoading,
        createSession,
        renameSession,
        deleteSession,
        refetchSessions,
      }}
    >
      {children}
    </ChatSessionContext.Provider>
  )
}

export function useChatSession() {
  const ctx = useContext(ChatSessionContext)
  if (!ctx) throw new Error('useChatSession must be used within ChatSessionProvider')
  return ctx
}
