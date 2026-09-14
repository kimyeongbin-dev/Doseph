'use client'
import { useState, useEffect, useRef, useCallback } from 'react'
import { X, Send, RefreshCw, Plus, Pencil, Trash2, Check, MapPin } from 'lucide-react'
import PropTypes from 'prop-types'
import Markdown from 'react-markdown'
import api, { showError } from '@/lib/api'
import { useChatSession } from '@/contexts/ChatSessionContext'

// Assistant 메시지는 LLM 이 Markdown 으로 답하므로 커스텀 컴포넌트 매핑으로
// Tailwind 스타일을 주입한다. Tailwind Typography 플러그인 없이도 읽기 좋은
// 리스트·볼드·링크 스타일을 확보하는 게 목적.
const MARKDOWN_COMPONENTS = {
  p: ({ children }) => <p className="mb-2 last:mb-0 leading-relaxed">{children}</p>,
  ul: ({ children }) => <ul className="list-disc pl-5 mb-2 last:mb-0 space-y-0.5">{children}</ul>,
  ol: ({ children }) => <ol className="list-decimal pl-5 mb-2 last:mb-0 space-y-0.5">{children}</ol>,
  li: ({ children }) => <li className="leading-relaxed">{children}</li>,
  strong: ({ children }) => <strong className="font-semibold text-ink">{children}</strong>,
  em: ({ children }) => <em className="italic">{children}</em>,
  h1: ({ children }) => <h1 className="font-bold text-base mt-3 mb-1 first:mt-0">{children}</h1>,
  h2: ({ children }) => <h2 className="font-bold text-base mt-3 mb-1 first:mt-0">{children}</h2>,
  h3: ({ children }) => <h3 className="font-semibold text-sm mt-2 mb-1 first:mt-0">{children}</h3>,
  a: ({ href, children }) => (
    <a
      href={href}
      target="_blank"
      rel="noopener noreferrer"
      className="underline text-blue-600 hover:text-blue-800 break-all"
    >
      {children}
    </a>
  ),
  code: ({ children }) => (
    <code className="bg-surface-2 px-1 py-0.5 rounded text-xs font-mono">{children}</code>
  ),
  pre: ({ children }) => (
    <pre className="bg-surface-2 rounded-md p-2 my-2 text-xs font-mono overflow-x-auto">{children}</pre>
  ),
  hr: () => <hr className="my-3 border-line" />,
  blockquote: ({ children }) => (
    <blockquote className="border-l-4 border-line pl-3 my-2 text-muted">{children}</blockquote>
  ),
}

// 빈 세션/새 세션에서 보여줄 인사말. 5곳에 같은 문자열이 흩어져 있어 상수로 모은다
// (문구를 고칠 때 한 곳만 바뀌어 세션마다 다른 인사말이 나오는 것을 막는다).
const WELCOME_MESSAGE = { role: 'assistant', content: '안녕하세요! 복약 관련 궁금한 것을 물어보세요.' }
const NO_PROFILE_MESSAGE = { role: 'assistant', content: '프로필 정보를 불러올 수 없습니다.' }
const INIT_FAILED_MESSAGE = {
  role: 'assistant',
  content: '채팅 연결에 실패했습니다. 아래 버튼을 눌러 다시 시도해주세요.',
}

/**
 * 기본 세션 제목 포맷: "새 채팅 MM/DD HH:mm"
 */
function formatDefaultSessionTitle(date = new Date()) {
  const pad = (n) => String(n).padStart(2, '0')
  return `새 채팅 ${pad(date.getMonth() + 1)}/${pad(date.getDate())} ${pad(date.getHours())}:${pad(date.getMinutes())}`
}

/**
 * 공통 챗봇 모달 컴포넌트 (좌측 세션 사이드바 포함)
 *
 * @param {Object} props
 * @param {Function} props.onClose - 모달 닫기 콜백
 * @param {string} props.profileId - 프로필 ID (필수)
 */
export default function ChatModal({ onClose, profileId }) {
  // ChatSessionContext 가 sessions list 와 activeSessionId 를 단일 진실로 관리
  const {
    sessions,
    activeSessionId,
    setActiveSessionId,
    createSession,
    renameSession,
    deleteSession,
    refetchSessions,
  } = useChatSession()
  const [messages, setMessages] = useState([])
  const [input, setInput] = useState('')
  const [isLoading, setIsLoading] = useState(false)
  // 세션 목록 동기화 진행 여부. 초깃값이 이미 '동기화 중'이라 effect 본문에서
  // 다시 세팅할 필요가 없다 — 되돌리는 건 재시도 버튼(이벤트)의 몫이다.
  const [isSyncingSessions, setIsSyncingSessions] = useState(true)
  const [initError, setInitError] = useState(false)
  // 재시도 트리거. 값이 바뀌면 아래 동기화 effect 가 다시 돈다.
  const [initAttempt, setInitAttempt] = useState(0)
  // 모달을 연 시점의 세션. Context 의 activeSessionId 는 모달 unmount 후에도
  // 보존되므로, 다시 열면 그 세션으로 복귀시키기 위해 마운트 값만 고정해 둔다.
  const [sessionIdAtOpen] = useState(activeSessionId)

  // 사이드바 인라인 편집/삭제 상태
  const [editingSessionId, setEditingSessionId] = useState(null)
  const [editingTitle, setEditingTitle] = useState('')
  const [confirmDeleteId, setConfirmDeleteId] = useState(null)

  // GPS 권한 토글 (JIT opt-in 정책)
  // - 새 세션은 토글이 hidden (세션 변경 시 reset)
  // - 사용자가 GPS 가 필요한 질문을 처음 던지면 토글이 등장 (gpsToggleVisible=true)
  // - 사용자가 ON 하기 전까지 위치는 보내지 않음 (즉시 denied POST)
  // - ON 일 때 들어온 pending turn 은 navigator.geolocation 흐름으로 진행
  const [gpsToggleVisible, setGpsToggleVisible] = useState(false)
  const [gpsToggleOn, setGpsToggleOn] = useState(false)
  const [pendingGpsTurnId, setPendingGpsTurnId] = useState(null)

  const scrollRef = useRef(null)
  const editInputRef = useRef(null)

  // 특정 세션의 메시지 로드 (비어있으면 환영 메시지)
  const loadMessagesForSession = useCallback(async (sessionId) => {
    const res = await api.get(`/api/v1/messages/session/${sessionId}`)
    if (res.data?.length > 0) {
      setMessages(res.data.map(m => ({
        role: m.sender_type === 'USER' ? 'user' : 'assistant',
        content: m.content,
      })))
    } else {
      setMessages([WELCOME_MESSAGE])
    }
  }, [])

  // profileId 가 없으면 초기화할 것 자체가 없다 — state 로 복제하지 않고 렌더 중 파생한다.
  const hasProfile = !!profileId
  const isInitializing = hasProfile && isSyncingSessions

  // 목록에 없는 활성 id(삭제·프로필 전환 등)는 렌더 중에 걸러 첫 세션으로 물러난다.
  // effect 로 state 를 되돌리지 않으므로 Context 에 남은 낡은 id 는 무해하게 버려진다.
  const effectiveSessionId =
    sessions.find(s => s.id === activeSessionId)?.id ?? sessions[0]?.id ?? null

  // 화면에 실제로 그릴 메시지. 프로필 없음/세션 없음은 상태로 들고 있지 않고 파생한다.
  const displayMessages = !hasProfile
    ? [NO_PROFILE_MESSAGE]
    : !isInitializing && !initError && sessions.length === 0
      ? [WELCOME_MESSAGE]
      : messages

  // ── 모달 열림 시 세션 동기화 ────────────────────────────────────────
  // 흐름: 세션 목록 최신화 -> 복귀할 세션 결정 -> 그 세션 메시지 로드
  //       (세션이 하나도 없으면 인사말만)
  // 서버와의 동기화라 effect 가 맞다. 다만 상태 변경은 전부 비동기 콜백 안에서만
  // 일어난다 — effect 본문에서 동기 setState 를 하면 렌더가 한 번 더 돈다.
  // ⚠️ 세션 전환/생성/삭제는 각 이벤트 핸들러가 직접 메시지를 로드한다. 여기서
  //    activeSessionId 를 다시 구독하면 전송 중 낙관적 메시지를 덮어쓸 수 있다.
  useEffect(() => {
    if (!hasProfile) return
    let cancelled = false

    refetchSessions()
      .then(async (latest) => {
        if (cancelled) return
        const nextId = latest.find(s => s.id === sessionIdAtOpen)?.id ?? latest[0]?.id ?? null
        setActiveSessionId(nextId)
        if (!nextId) {
          setMessages([WELCOME_MESSAGE])
          return
        }
        await loadMessagesForSession(nextId)
      })
      .catch((err) => {
        if (cancelled) return
        console.error('세션 초기화 실패:', err)
        showError('채팅 세션을 시작할 수 없습니다.')
        setMessages([INIT_FAILED_MESSAGE])
        setInitError(true)
      })
      .finally(() => {
        if (!cancelled) setIsSyncingSessions(false)
      })

    return () => {
      cancelled = true
    }
  }, [
    hasProfile,
    initAttempt,
    refetchSessions,
    setActiveSessionId,
    sessionIdAtOpen,
    loadMessagesForSession,
  ])

  // 초기화 재시도 — 이벤트 핸들러라 동기 setState 가 허용된다(effect 가 아니다).
  const retryInit = () => {
    setInitError(false)
    setIsSyncingSessions(true)
    setInitAttempt(n => n + 1)
  }

  useEffect(() => {
    if (scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight
    }
    // 파생값(displayMessages)이 아니라 실제 대화 state 를 따른다 — 파생 분기는
    // 한 줄짜리 안내 메시지라 스크롤 대상이 아니고, 매 렌더 새 배열이라 deps 를 흔든다.
  }, [messages, isLoading])

  // 세션이 바뀌면 GPS 토글 상태를 새 세션 기준으로 reset
  // (새 세션의 첫 GPS 검색에서 다시 등장하도록 hidden + OFF)
  useEffect(() => {
    setGpsToggleVisible(false)
    setGpsToggleOn(false)
    setPendingGpsTurnId(null)
  }, [effectiveSessionId])

  // 편집 모드 진입 시 입력창에 포커스
  useEffect(() => {
    if (editingSessionId && editInputRef.current) {
      editInputRef.current.focus()
      editInputRef.current.select()
    }
  }, [editingSessionId])

  // 세션 전환 — isLoading (현재 세션 답변 대기) 와 무관하게 항상 가능.
  // 새 세션의 isPendingResponse 는 그 세션 메시지 기준으로 재계산되어 자동 분리됨.
  const switchSession = async (sessionId) => {
    if (sessionId === effectiveSessionId) return
    setActiveSessionId(sessionId)
    setConfirmDeleteId(null)
    try {
      await loadMessagesForSession(sessionId)
    } catch (err) {
      console.error('세션 메시지 로드 실패:', err)
      showError('메시지를 불러오지 못했습니다.')
    }
  }

  // 새 세션 생성 — 다른 세션 답변 대기 중에도 항상 허용 (각 세션은 독립).
  const handleCreateSession = async () => {
    if (isInitializing || !profileId) return
    try {
      const newSession = await createSession(profileId, formatDefaultSessionTitle())
      setActiveSessionId(newSession.id)
      setMessages([WELCOME_MESSAGE])
    } catch (err) {
      console.error('새 세션 생성 실패:', err)
      showError('새 채팅을 만들 수 없습니다.')
    }
  }

  // 편집 시작
  const startEditing = (session) => {
    setEditingSessionId(session.id)
    setEditingTitle(session.title || '')
    setConfirmDeleteId(null)
  }

  const cancelEditing = () => {
    setEditingSessionId(null)
    setEditingTitle('')
  }

  // 편집 저장 (Enter / blur / 체크 클릭)
  const saveEditing = async () => {
    const sessionId = editingSessionId
    const trimmed = editingTitle.trim()
    if (!sessionId) return
    if (!trimmed) {
      cancelEditing()
      return
    }
    const original = sessions.find(s => s.id === sessionId)
    if (original && original.title === trimmed) {
      cancelEditing()
      return
    }
    try {
      await renameSession(sessionId, trimmed)
    } catch (err) {
      console.error('세션 이름 변경 실패:', err)
      showError('이름을 변경하지 못했습니다.')
    } finally {
      cancelEditing()
    }
  }

  // 삭제 (인라인 확인: 첫 클릭 → 확정 아이콘 표시, 두 번째 클릭 → 삭제)
  const handleDeleteClick = async (sessionId) => {
    if (confirmDeleteId !== sessionId) {
      setConfirmDeleteId(sessionId)
      return
    }
    // 확정 클릭 — Context 가 응답으로 sessions 자동 갱신 + activeSessionId 자동 reset
    try {
      const wasActive = sessionId === effectiveSessionId
      await deleteSession(sessionId)
      setConfirmDeleteId(null)

      // 활성 세션을 지운 경우: 남은 첫 세션으로 자동 전환 (sessions 변동 effect 처리)
      // 단, 메시지 로드는 여기서 직접 호출 (effect 가 동기화 한 turn 늦을 수 있음)
      if (wasActive) {
        const remaining = sessions.filter(s => s.id !== sessionId)
        if (remaining.length > 0) {
          const nextId = remaining[0].id
          setActiveSessionId(nextId)
          await loadMessagesForSession(nextId)
        } else {
          setActiveSessionId(null)
          setMessages([WELCOME_MESSAGE])
        }
      }
    } catch (err) {
      console.error('세션 삭제 실패:', err)
      showError('세션을 삭제하지 못했습니다.')
      setConfirmDeleteId(null)
    }
  }

  // Tool Calling 분기: 202 수신 시 브라우저 GPS 권한 요청 → /tool-result 로
  // 허용/거부 결과 전달. 위치 기반 약국·병원 검색 (Phase Y) 전용 플로우.
  const handleGeolocationCallback = useCallback(async (pending) => {
    const { turn_id } = pending

    const resolveWithCoords = (position) =>
      api.post('/api/v1/messages/tool-result', {
        turn_id,
        status: 'ok',
        lat: position.coords.latitude,
        lng: position.coords.longitude,
      })

    const resolveAsDenied = () =>
      api.post('/api/v1/messages/tool-result', {
        turn_id,
        status: 'denied',
      })

    let finalRes
    try {
      const position = await new Promise((resolve, reject) => {
        if (!navigator.geolocation) {
          reject(new Error('navigator.geolocation unavailable'))
          return
        }
        navigator.geolocation.getCurrentPosition(resolve, reject, {
          // BE pending TTL 이 60s 이므로 권한 응답 대기는 15s 로 조여둔다
          timeout: 15_000,
          maximumAge: 0,
        })
      })
      finalRes = await resolveWithCoords(position)
    } catch (geoErr) {
      // 권한 거부 / 타임아웃 / 미지원 — 모두 denied 로 보내서 LLM 이 안내 문구 생성
      console.warn('[ToolCalling] geolocation failed, falling back to denied:', geoErr)
      try {
        finalRes = await resolveAsDenied()
      } catch (denyErr) {
        if (denyErr.response?.status === 410) {
          setMessages(prev => [...prev, { role: 'assistant', content: '시간이 너무 지나서 요청이 만료되었어요. 다시 질문해 주세요.' }])
          return
        }
        console.error('[ToolCalling] tool-result denied 전달 실패:', denyErr)
        setMessages(prev => [...prev, { role: 'assistant', content: '요청을 처리하지 못했어요. 잠시 후 다시 시도해 주세요.' }])
        return
      }
    }

    const content = finalRes?.data?.assistant_message?.content || '응답을 받지 못했습니다.'
    setMessages(prev => [...prev, { role: 'assistant', content }])
  }, [])

  // GPS 토글 클릭 — OFF→ON 전환 시 대기 중인 pending turn 이 있으면 즉시 진행
  const handleGpsToggle = useCallback(async () => {
    const next = !gpsToggleOn
    setGpsToggleOn(next)
    if (!next) return // ON→OFF 는 다음 GPS 요청에서만 효과 (이번 turn 은 자연 만료)
    if (!pendingGpsTurnId) return
    const turn_id = pendingGpsTurnId
    setPendingGpsTurnId(null)
    setIsLoading(true)
    try {
      await handleGeolocationCallback({ turn_id })
    } finally {
      setIsLoading(false)
    }
  }, [gpsToggleOn, pendingGpsTurnId, handleGeolocationCallback])

  // 마지막 메시지가 user 면 BE 응답 대기 중 — 모달 unmount 후 재진입해도 이 상태
  // 가 자동 인식돼서 (1) 점점점 스켈레톤 표시 (2) 중복 전송 차단 모두 작동.
  const isPendingResponse =
    displayMessages.length > 0 && displayMessages[displayMessages.length - 1].role === 'user'

  const handleSend = async () => {
    const message = input.trim()
    if (!message || isLoading || isInitializing || isPendingResponse) return

    setInput('')
    setMessages(prev => [...prev, { role: 'user', content: message }])
    setIsLoading(true)

    try {
      // Lazy session creation: 아직 세션이 없으면 여기서 생성한다 — Context 가 sessions 자동 갱신
      let sid = effectiveSessionId
      if (!sid) {
        const newSession = await createSession(profileId, formatDefaultSessionTitle())
        sid = newSession.id
        setActiveSessionId(sid)
      }

      const res = await api.post('/api/v1/messages/ask', {
        session_id: sid,
        content: message,
      })

      // 202 Accepted + action=request_geolocation: Router LLM 이 위치 기반
      // 툴을 고른 상태. JIT 토글 정책 — 사용자가 토글을 ON 한 경우만 즉시
      // navigator.geolocation 호출, 아니면 토글을 등장시키고 사용자 결정 대기.
      if (res.status === 202 && res.data?.action === 'request_geolocation') {
        if (gpsToggleOn) {
          // 토글 ON: 평소 흐름 그대로 GPS 받아서 tool-result POST
          await handleGeolocationCallback(res.data)
        } else {
          // 토글 OFF (default): 토글 등장 + pending turn_id 보존.
          // 사용자가 토글 ON 누르면 그때 handleGeolocationCallback 진행.
          setPendingGpsTurnId(res.data.turn_id)
          if (!gpsToggleVisible) {
            setGpsToggleVisible(true)
            setMessages(prev => [...prev, {
              role: 'assistant',
              content: '이 검색은 위치 정보가 필요해요. 아래 위치 토글을 켜주시면 검색을 진행할게요. (60초 안에 결정해 주세요)'
            }])
          } else {
            setMessages(prev => [...prev, {
              role: 'assistant',
              content: '위치 토글이 꺼져있어요. 아래 토글을 켜주시면 검색을 진행할게요.'
            }])
          }
        }
        return
      }

      const assistantContent = res.data.assistant_message?.content || '응답을 받지 못했습니다.'
      setMessages(prev => [...prev, { role: 'assistant', content: assistantContent }])
    } catch (err) {
      console.error('메시지 전송 실패:', err)
      setMessages(prev => [...prev, { role: 'assistant', content: '죄송합니다. 응답을 처리하는 중 오류가 발생했습니다.' }])
    } finally {
      setIsLoading(false)
    }
  }

  const formatSessionDate = (iso) => {
    if (!iso) return ''
    const d = new Date(iso)
    const pad = (n) => String(n).padStart(2, '0')
    return `${pad(d.getMonth() + 1)}/${pad(d.getDate())}`
  }

  return (
    <div className="fixed inset-0 bg-black/50 z-[100] flex items-end justify-end p-6 backdrop-blur-sm">
      <div className="bg-surface rounded-2xl w-full max-w-3xl h-[640px] flex shadow-2xl border border-line overflow-hidden">
        {/* 좌측 세션 사이드바 */}
        <aside className="w-56 flex-shrink-0 border-r border-line flex flex-col bg-surface-2">
          <div className="p-3 border-b border-line">
            <button
              onClick={handleCreateSession}
              disabled={isInitializing}
              className="w-full flex items-center justify-center gap-2 bg-accent text-accent-ink rounded-lg px-3 py-2 text-sm font-medium hover:brightness-110 disabled:bg-surface-2 active:scale-95 transition-all cursor-pointer"
            >
              <Plus size={16} />
              새 채팅
            </button>
          </div>
          <div className="flex-1 overflow-y-auto">
            {sessions.length === 0 && !isInitializing && (
              <div className="p-4 text-xs text-muted text-center">사용 중인 채팅창이 없습니다.</div>
            )}
            <ul>
              {sessions.map(session => {
                const isActive = session.id === effectiveSessionId
                const isEditing = session.id === editingSessionId
                const isConfirmingDelete = session.id === confirmDeleteId
                return (
                  <li
                    key={session.id}
                    className={`group px-3 py-2 border-b border-line cursor-pointer transition-colors
                      ${isActive ? 'bg-surface' : 'hover:bg-surface'}`}
                    onClick={() => !isEditing && switchSession(session.id)}
                  >
                    <div className="flex items-center justify-between gap-1">
                      {isEditing ? (
                        <input
                          ref={editInputRef}
                          type="text"
                          value={editingTitle}
                          maxLength={64}
                          onChange={(e) => setEditingTitle(e.target.value)}
                          onKeyDown={(e) => {
                            if (e.key === 'Enter') saveEditing()
                            else if (e.key === 'Escape') cancelEditing()
                          }}
                          onBlur={saveEditing}
                          onClick={(e) => e.stopPropagation()}
                          className="flex-1 min-w-0 text-sm px-1.5 py-0.5 border border-line rounded outline-none focus:border-line bg-surface"
                        />
                      ) : (
                        <div
                          className="flex-1 min-w-0 text-sm truncate"
                          onDoubleClick={(e) => { e.stopPropagation(); startEditing(session) }}
                          title={session.title || '제목 없음'}
                        >
                          <span className={isActive ? 'font-semibold text-ink' : 'text-ink'}>
                            {session.title || '제목 없음'}
                          </span>
                        </div>
                      )}
                      {!isEditing && (
                        <div className="flex items-center gap-0.5 opacity-0 group-hover:opacity-100 transition-opacity">
                          <button
                            onClick={(e) => { e.stopPropagation(); startEditing(session) }}
                            className="p-1 text-muted hover:text-ink rounded"
                            aria-label="이름 변경"
                          >
                            <Pencil size={13} />
                          </button>
                          <button
                            onClick={(e) => { e.stopPropagation(); handleDeleteClick(session.id) }}
                            className={`p-1 rounded transition-colors
                              ${isConfirmingDelete ? 'text-red-600 bg-red-50' : 'text-muted hover:text-red-600'}`}
                            aria-label={isConfirmingDelete ? '삭제 확정' : '삭제'}
                          >
                            {isConfirmingDelete ? <Check size={13} /> : <Trash2 size={13} />}
                          </button>
                        </div>
                      )}
                    </div>
                    <div className="text-[10px] text-muted mt-0.5">{formatSessionDate(session.created_at)}</div>
                  </li>
                )
              })}
            </ul>
          </div>
        </aside>

        {/* 우측 대화 영역 */}
        <div className="flex-1 flex flex-col min-w-0">
          {/* 헤더 */}
          <div className="flex justify-between items-center p-5 border-b border-line">
            <div className="min-w-0">
              <h2 className="font-bold text-lg text-ink">복약 AI 상담</h2>
              <p className="text-xs text-muted truncate">약 복용 방법 등 무엇이든 물어보세요</p>
            </div>
            <button onClick={onClose} className="text-muted hover:text-black cursor-pointer p-2 transition-colors">
              <X size={20} />
            </button>
          </div>

          {/* 채팅 영역 */}
          <div ref={scrollRef} className="flex-1 overflow-y-auto p-4 space-y-4 bg-surface-2">
            {displayMessages.map((msg, i) => (
              <div key={i} className={`flex ${msg.role === 'user' ? 'justify-end' : 'justify-start'}`}>
                <div className={`max-w-[80%] px-4 py-3 rounded-2xl text-sm shadow-sm
                  ${msg.role === 'user'
                    ? 'bg-accent text-accent-ink rounded-br-none whitespace-pre-wrap break-words'
                    : 'bg-surface text-ink rounded-bl-none border border-line'
                  }`}>
                  {msg.role === 'user' ? (
                    msg.content
                  ) : (
                    // react-markdown 은 기본적으로 raw HTML 렌더링을 차단한다
                    // (rehype-raw 등 플러그인 미추가). 따라서 사용자나 LLM 이 <script>
                    // 를 포함해도 텍스트 노드로만 삽입되어 XSS 가 차단된다.
                    <Markdown components={MARKDOWN_COMPONENTS}>
                      {msg.content}
                    </Markdown>
                  )}
                </div>
              </div>
            ))}

            {(isInitializing || isLoading || isPendingResponse) && (
              <div className="flex justify-start">
                  <div className="bg-surface border border-line px-4 py-3 rounded-2xl rounded-bl-none shadow-sm flex gap-1.5">
                    <div className="w-1.5 h-1.5 bg-surface-2 rounded-full animate-bounce" style={{animationDelay: '0ms'}} />
                    <div className="w-1.5 h-1.5 bg-surface-2 rounded-full animate-bounce" style={{animationDelay: '150ms'}} />
                    <div className="w-1.5 h-1.5 bg-surface-2 rounded-full animate-bounce" style={{animationDelay: '300ms'}} />
                  </div>
              </div>)}
          </div>

          {/* GPS 권한 토글 (JIT — 첫 위치 검색 후 등장, 이후 같은 세션 동안 유지) */}
          {gpsToggleVisible && (
            <div className="px-4 py-2 bg-blue-50 border-t border-blue-100 flex items-center justify-between">
              <div className="flex items-center gap-2 text-sm text-ink">
                <MapPin size={14} className={gpsToggleOn ? 'text-ink' : 'text-muted'} />
                <span>위치 정보 사용 {gpsToggleOn ? '켜짐' : '꺼짐'}</span>
              </div>
              <button
                onClick={handleGpsToggle}
                disabled={isLoading || isInitializing}
                className={`relative w-10 h-5 rounded-full transition-colors disabled:opacity-50 cursor-pointer
                  ${gpsToggleOn ? 'bg-accent' : 'bg-surface-2'}`}
                aria-label={gpsToggleOn ? '위치 사용 끄기' : '위치 사용 켜기'}
                aria-pressed={gpsToggleOn}
              >
                <span
                  className={`absolute top-0.5 w-4 h-4 bg-surface rounded-full transition-all
                    ${gpsToggleOn ? 'right-0.5' : 'left-0.5'}`}
                />
              </button>
            </div>
          )}

          {/* 입력창 */}
          <div className="p-4 bg-surface border-t border-line flex gap-2 items-center">
            {initError ? (
              <button
                onClick={retryInit}
                disabled={isInitializing}
                className="flex-1 flex items-center justify-center gap-2 bg-accent text-accent-ink rounded-xl px-4 py-2.5 text-sm hover:brightness-110 disabled:bg-surface-2 active:scale-95 transition-all cursor-pointer"
              >
                <RefreshCw size={16} className={isInitializing ? 'animate-spin' : ''} />
                {isInitializing ? '연결 중...' : '다시 연결하기'}
              </button>
            ) : (
              <>
                <input
                  type="text"
                  value={input}
                  onChange={(e) => setInput(e.target.value)}
                  onKeyUp={(e) => { if (e.key === 'Enter') handleSend() }}
                  disabled={isInitializing || isPendingResponse}
                  placeholder={
                    isInitializing
                      ? '연결 중...'
                      : isPendingResponse
                        ? '답변을 기다리는 중...'
                        : '메시지를 입력하세요'
                  }
                  className="flex-1 bg-surface-2 border border-line rounded-xl px-4 py-2.5 text-sm outline-none focus:border-line transition-all disabled:opacity-50"
                />
                <button
                  onClick={handleSend}
                  disabled={isLoading || !input.trim() || isInitializing || isPendingResponse}
                  className="w-10 h-10 rounded-xl flex items-center justify-center bg-accent text-accent-ink hover:brightness-110 disabled:bg-surface-2 disabled:text-muted active:scale-95 transition-all cursor-pointer"
                >
                  <Send size={16} />
                </button>
              </>
            )}
          </div>
        </div>
      </div>
    </div>
  )
}

ChatModal.propTypes = {
  onClose: PropTypes.func.isRequired,
  profileId: PropTypes.oneOfType([
    PropTypes.string,
    PropTypes.number
  ]).isRequired
}
