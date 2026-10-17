'use client'

// 약품 상세 본문 panel — /medication/[id] 페이지와 처방전 drill-down 의 데스크탑
// split-pane 우측에서 공유. 페이지 헤더 (처방전 상세의 ← 버튼 등) 는 외부에서
// 책임지므로 본 컴포넌트는 본문만 렌더한다.

import { useEffect, useState } from 'react'
import { useRouter } from 'next/navigation'

import {
  AlertCircle,
  AlertTriangle,
  Ban,
  Calendar,
  ChevronDown,
  ChevronUp,
  Clock,
  PencilLine,
  Pill,
  Trash2,
  Utensils,
} from 'lucide-react'
import toast from 'react-hot-toast'
import Markdown from 'react-markdown'

import api from '@/lib/api'
import { useMedication } from '@/contexts/MedicationContext'
import TimeSlotPicker from '@/components/medication/TimeSlotPicker'

// react-markdown components — ChatModal 과 동일 패턴 (Tailwind Typography 없이
// 가독성 확보). 약품 상세 panel 안에서 BE 응답의 plain text 또는 ** **, - 을
// 자연스럽게 렌더.
const MD_COMPONENTS = {
  p: ({ children }) => (
    <p className="text-sm text-muted leading-relaxed mb-2 last:mb-0">{children}</p>
  ),
  ul: ({ children }) => <ul className="list-disc pl-5 mb-2 last:mb-0 space-y-1">{children}</ul>,
  ol: ({ children }) => <ol className="list-decimal pl-5 mb-2 last:mb-0 space-y-1">{children}</ol>,
  li: ({ children }) => <li className="text-sm text-muted leading-relaxed">{children}</li>,
  strong: ({ children }) => <strong className="font-semibold text-ink">{children}</strong>,
  em: ({ children }) => <em className="italic">{children}</em>,
  h1: ({ children }) => (
    <h1 className="font-bold text-sm mt-2 mb-1 first:mt-0 text-ink">{children}</h1>
  ),
  h2: ({ children }) => (
    <h2 className="font-bold text-sm mt-2 mb-1 first:mt-0 text-ink">{children}</h2>
  ),
  h3: ({ children }) => (
    <h3 className="font-semibold text-xs mt-1.5 mb-1 first:mt-0 text-ink">{children}</h3>
  ),
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
  blockquote: ({ children }) => (
    <blockquote className="border-l-4 border-line pl-3 my-2 text-muted text-sm">
      {children}
    </blockquote>
  ),
}

// ── Collapsible — 접기/펼치기 텍스트. 긴 항목 (주의사항/상호작용 등) 의 가독성
//    개선을 위해 cap 자 이상이면 자동 collapsed 로 시작.
const COLLAPSE_CHAR_THRESHOLD = 180

function CollapsibleText({
  children,
  initialCollapsed = true,
  label = '더 보기',
  collapseLabel = '접기',
}) {
  const [collapsed, setCollapsed] = useState(initialCollapsed)
  const text = typeof children === 'string' ? children : String(children ?? '')
  const needsCollapse = text.length > COLLAPSE_CHAR_THRESHOLD
  if (!needsCollapse) {
    return <Markdown components={MD_COMPONENTS}>{text}</Markdown>
  }
  return (
    <div>
      <div className={collapsed ? 'overflow-hidden max-h-24 relative' : ''}>
        <Markdown components={MD_COMPONENTS}>{text}</Markdown>
        {collapsed && (
          <div className="absolute bottom-0 left-0 right-0 h-8 bg-gradient-to-t from-white to-transparent pointer-events-none" />
        )}
      </div>
      <button
        type="button"
        onClick={() => setCollapsed((c) => !c)}
        className="mt-1 text-xs font-bold text-blue-600 hover:text-blue-800 flex items-center gap-1 cursor-pointer"
      >
        {collapsed ? (
          <>
            {label} <ChevronDown size={14} />
          </>
        ) : (
          <>
            {collapseLabel} <ChevronUp size={14} />
          </>
        )}
      </button>
    </div>
  )
}

function DrugInfoSkeleton() {
  return (
    <div className="space-y-3 animate-pulse">
      {[1, 2, 3].map((i) => (
        <div key={i} className="h-14 bg-surface-2 rounded-xl" />
      ))}
    </div>
  )
}

function DeleteConfirmModal({ medicineName, onConfirm, onCancel, isDeleting }) {
  return (
    <div className="fixed inset-0 z-50 flex items-end justify-center bg-black/40 px-4 pb-6">
      <div className="bg-surface rounded-2xl w-full max-w-sm p-6 space-y-4">
        <div className="text-center space-y-1">
          <div className="w-12 h-12 bg-red-50 rounded-full flex items-center justify-center mx-auto mb-3">
            <Trash2 size={20} className="text-red-500" />
          </div>
          <p className="font-bold text-ink">약품을 삭제할까요?</p>
          <p className="text-sm text-muted leading-relaxed">
            <span className="font-bold text-ink">{medicineName}</span> 복용 기록이
            <br />
            영구적으로 삭제됩니다.
          </p>
        </div>
        <div className="flex gap-2 pt-1">
          <button
            onClick={onCancel}
            disabled={isDeleting}
            className="flex-1 py-3 rounded-xl text-sm font-bold text-muted bg-surface-2 cursor-pointer hover:bg-surface-2 transition-colors disabled:opacity-50"
          >
            취소
          </button>
          <button
            onClick={onConfirm}
            disabled={isDeleting}
            className="flex-1 py-3 rounded-xl text-sm font-bold text-accent-ink bg-red-500 cursor-pointer hover:bg-red-600 transition-colors disabled:opacity-50"
          >
            {isDeleting ? '삭제 중...' : '삭제'}
          </button>
        </div>
      </div>
    </div>
  )
}

/**
 * @param {object} props
 * @param {string} props.medicationId 표시할 medication UUID.
 * @param {() => void} [props.onDeleted] 삭제 완료 시 콜백 (페이지 이동 / panel close 등).
 */
export default function MedicationDetailPanel({ medicationId, onDeleted }) {
  const id = medicationId
  const router = useRouter()
  const { medications, deleteMedication, deactivateMedication, getDrugInfo, refetchMedications } =
    useMedication()
  const [isLoading, setIsLoading] = useState(true)
  const [isDrugInfoLoading, setIsDrugInfoLoading] = useState(false)
  const [isDeleting, setIsDeleting] = useState(false)
  const [showDeleteModal, setShowDeleteModal] = useState(false)
  const [fallbackMed, setFallbackMed] = useState(null)
  const [drugInfo, setDrugInfo] = useState(null)
  const [activeTab, setActiveTab] = useState('용법')

  const med = medications.find((m) => m.id === id) || fallbackMed

  useEffect(() => {
    if (!id) return
    /* eslint-disable react-hooks/set-state-in-effect -- id 변경 시 panel state reset */
    setDrugInfo(null)
    setActiveTab('용법')
    // 직전 약에서 삭제 진행 중이었거나 confirm 모달이 열려 있던 상태가
    // 새 약 panel 로 누수되어 'X 삭제 중...' 모달이 stuck 되는 회귀 차단.
    setIsDeleting(false)
    setShowDeleteModal(false)
    if (medications.find((m) => m.id === id)) {
      setIsLoading(false)
      return
    }
    if (medications.length === 0) return
    setIsLoading(true)
    /* eslint-enable react-hooks/set-state-in-effect */
    api
      .get(`/api/v1/medications/${id}`)
      .then((res) => setFallbackMed(res.data))
      .catch(() => setFallbackMed(null))
      .finally(() => setIsLoading(false))
  }, [id, medications])

  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect -- store 도착 시 loading off
    if (med) setIsLoading(false)
  }, [med])

  useEffect(() => {
    if (!med || drugInfo || !id) return
    let cancelled = false
    // eslint-disable-next-line react-hooks/set-state-in-effect -- 비동기 fetch 의 trigger 이며 컴포넌트 외부 store (lazy LLM cache) 와 동기화
    setIsDrugInfoLoading(true)
    getDrugInfo(id)
      .then((data) => {
        if (!cancelled) setDrugInfo(data)
      })
      .catch((err) => console.error(err))
      .finally(() => {
        if (!cancelled) setIsDrugInfoLoading(false)
      })
    return () => {
      cancelled = true
    }
  }, [med, drugInfo, id, getDrugInfo])

  const handleDelete = async () => {
    setIsDeleting(true)
    try {
      await deleteMedication(id)
      await refetchMedications() // 홈 화면 등에서 즉시 반영 위해 Context 재조회
      // 성공 시에도 모달/플래그 닫기. onDeleted 가 panel close 를 트리거하지만
      // 외부에서 같은 panel 을 다음 약으로 재사용하는 흐름이라면 state 잔여를
      // 남기지 않아야 함.
      setIsDeleting(false)
      setShowDeleteModal(false)
      onDeleted?.()
    } catch (err) {
      console.error(err)
      toast.error('삭제에 실패했습니다. 다시 시도해주세요.')
      setIsDeleting(false)
      setShowDeleteModal(false)
    }
  }

  const handleDeactivate = async () => {
    try {
      await deactivateMedication(id)
    } catch (err) {
      console.error(err)
      toast.error('처리에 실패했습니다. 다시 시도해주세요.')
    }
  }

  if (!id) {
    return (
      <div className="flex items-center justify-center h-full text-sm text-muted py-12">
        약을 선택하면 상세 정보가 표시됩니다.
      </div>
    )
  }

  if (isLoading) {
    return (
      <div className="px-6 py-6 space-y-4 animate-pulse">
        <div className="h-32 bg-accent rounded-2xl opacity-80" />
        <div className="h-10 bg-surface rounded-xl border border-line" />
        <div className="h-48 bg-surface rounded-2xl border border-line" />
      </div>
    )
  }

  if (!med) {
    return (
      <div className="flex items-center justify-center h-full text-sm text-muted py-12">
        약품 정보를 찾을 수 없습니다.
      </div>
    )
  }

  // 짧은 숫자형 값 (1일 복용 횟수 / 총 복용 일수) 은 grid 2-col 로 한 행에 좌우 배치 —
  // 사용자 피드백: 단독 row 일 때 오른쪽 여백 낭비.
  // 자유 텍스트 (1회 복용량 / 복용 방법) 은 full row 로 유지 — 한 줄에 가둘 수 없는 길이 가능성.
  const compactItems = [
    {
      icon: Clock,
      label: '1일 복용 횟수',
      value: med.daily_intake_count ? `${med.daily_intake_count}회` : null,
    },
    {
      icon: Calendar,
      label: '총 복용 일수',
      value: med.total_intake_days ? `${med.total_intake_days}일` : null,
    },
  ].filter((item) => item.value)
  const fullRowItems = [
    { icon: Pill, label: '1회 복용량', value: med.dose_per_intake },
    { icon: Utensils, label: '복용 방법', value: med.intake_instruction },
  ].filter((item) => item.value)

  const tabs = ['용법', '주의사항', '부작용', '상호작용']

  return (
    <div className="space-y-4">
      {/* 약품명 카드 + 편집/삭제 버튼 */}
      <div className="bg-accent rounded-2xl p-6 text-accent-ink relative">
        <div className="absolute top-4 right-4 flex items-center gap-1">
          <button
            onClick={() => router.push(`/medication/edit?ids=${id}`)}
            className="w-8 h-8 flex items-center justify-center rounded-lg text-muted hover:text-blue-300 hover:brightness-110 transition-colors cursor-pointer"
            aria-label="약품 정보 수정"
            title="이 약 정보 수정"
          >
            <PencilLine size={16} />
          </button>
          <button
            onClick={() => setShowDeleteModal(true)}
            className="w-8 h-8 flex items-center justify-center rounded-lg text-muted hover:text-red-400 hover:brightness-110 transition-colors cursor-pointer"
            aria-label="약품 삭제"
          >
            <Trash2 size={16} />
          </button>
        </div>
        <div className="flex items-start justify-between gap-4 pr-20">
          <div className="flex-1">
            {med.category && (
              <span className="text-xs font-bold text-muted bg-accent px-3 py-1 rounded-full mb-3 inline-block">
                {med.category}
              </span>
            )}
            <h2 className="text-xl font-black leading-snug mt-1 break-keep [overflow-wrap:anywhere]">
              {med.medicine_name}
            </h2>
            <p className="text-muted text-sm mt-2 flex items-center flex-wrap gap-x-3">
              <span>
                남은 복용 {med.remaining_intake_count} / {med.total_intake_count}회
              </span>
              {med.dispensed_date && (
                <span className="text-muted">· 처방일 {med.dispensed_date.replace(/-/g, '.')}</span>
              )}
            </p>
          </div>
          <div
            className={`px-3 py-1.5 rounded-full text-xs font-bold shrink-0 ${
              med.is_active ? 'bg-green-500/20 text-green-400' : 'bg-surface-2 text-muted'
            }`}
          >
            {med.is_active ? '복용중' : '완료'}
          </div>
        </div>
        {med.is_active && (
          <button
            onClick={handleDeactivate}
            className="mt-4 w-full py-2.5 rounded-xl text-xs font-bold text-muted bg-accent hover:brightness-110 hover:text-accent-ink transition-colors cursor-pointer"
          >
            복용 완료로 변경
          </button>
        )}
      </div>

      {/* 탭 */}
      <div className="bg-surface rounded-2xl border border-line overflow-hidden">
        <div className="flex border-b border-line">
          {tabs.map((tab) => (
            <button
              key={tab}
              onClick={() => setActiveTab(tab)}
              className={`flex-1 py-3 text-xs font-bold cursor-pointer transition-colors ${
                activeTab === tab ? 'text-ink border-b-2 border-accent' : 'text-muted'
              }`}
            >
              {tab}
            </button>
          ))}
        </div>

        <div className="p-5">
          {activeTab === '용법' && (
            <div className="space-y-3 animate-in fade-in duration-200">
              {compactItems.length === 0 && fullRowItems.length === 0 ? (
                <p className="text-sm text-muted text-center py-6">복용 정보가 없습니다.</p>
              ) : (
                <>
                  {/* 1회 복용량 / 복용 방법 — 자유 텍스트라 full row */}
                  {fullRowItems.map(({ icon: Icon, label, value }) => (
                    <div
                      key={label}
                      className="flex items-center gap-4 p-4 bg-surface-2 rounded-xl"
                    >
                      <div className="w-9 h-9 bg-surface rounded-xl flex items-center justify-center border border-line shrink-0">
                        <Icon size={16} className="text-muted" />
                      </div>
                      <div>
                        <p className="text-xs text-muted">{label}</p>
                        <p className="font-bold text-sm text-ink">{value}</p>
                      </div>
                    </div>
                  ))}
                  {/* 1일 복용 횟수 + 총 복용 일수 — 한 행에 좌우 grid 2-col */}
                  {compactItems.length > 0 && (
                    <div className="grid grid-cols-2 gap-3">
                      {compactItems.map(({ icon: Icon, label, value }) => (
                        <div
                          key={label}
                          className="flex items-center gap-3 p-4 bg-surface-2 rounded-xl"
                        >
                          <div className="w-9 h-9 bg-surface rounded-xl flex items-center justify-center border border-line shrink-0">
                            <Icon size={16} className="text-muted" />
                          </div>
                          <div className="min-w-0">
                            <p className="text-xs text-muted">{label}</p>
                            <p className="font-bold text-sm text-ink truncate">{value}</p>
                          </div>
                        </div>
                      ))}
                    </div>
                  )}
                </>
              )}

              {/* 복용 시간대 — 토글 시 PATCH /medications/{id} + 홈 TodaySchedule 즉시 반영 */}
              <div className="mt-4 p-4 bg-surface-2 rounded-xl space-y-2">
                <p className="text-xs text-muted">복용 시간대</p>
                <TimeSlotPicker medication={med} />
                <p className="text-[11px] text-muted">
                  선택한 시간대는 홈 화면의 시간대별 복용 알림에 표시됩니다.
                </p>
              </div>
              {drugInfo?.dosage && (
                <div className="mt-4 p-4 bg-blue-50 rounded-xl">
                  <p className="text-xs font-black text-blue-600 mb-2 uppercase tracking-wide">
                    식약처 표준 용법
                  </p>
                  <CollapsibleText>{drugInfo.dosage}</CollapsibleText>
                </div>
              )}
            </div>
          )}

          {activeTab === '주의사항' && (
            <div className="space-y-5 animate-in fade-in duration-200">
              {isDrugInfoLoading ? (
                <DrugInfoSkeleton />
              ) : drugInfo?.warnings?.length > 0 ? (
                drugInfo.warnings.map((section) => (
                  <div key={section.category}>
                    <h3 className="text-xs font-black text-ink mb-2 uppercase tracking-wide">
                      {section.category}
                    </h3>
                    <div className="space-y-2">
                      {section.items.map((item, i) => (
                        <div key={i} className="flex gap-3 p-4 bg-yellow-50 rounded-xl">
                          <AlertTriangle size={16} className="text-yellow-500 shrink-0 mt-0.5" />
                          <div className="min-w-0 flex-1">
                            <CollapsibleText>{item}</CollapsibleText>
                          </div>
                        </div>
                      ))}
                    </div>
                  </div>
                ))
              ) : (
                <p className="text-sm text-muted text-center py-6">
                  주의사항 정보를 불러올 수 없습니다.
                </p>
              )}
            </div>
          )}

          {activeTab === '부작용' && (
            <div className="animate-in fade-in duration-200">
              {isDrugInfoLoading ? (
                <DrugInfoSkeleton />
              ) : drugInfo?.side_effects?.length > 0 ? (
                <>
                  <div className="flex flex-wrap gap-2 mb-5">
                    {drugInfo.side_effects.map((s, i) => (
                      <span
                        key={i}
                        className="bg-red-50 text-red-500 px-4 py-2 rounded-full text-sm font-bold"
                      >
                        {s}
                      </span>
                    ))}
                  </div>
                  <div className="bg-red-50 rounded-xl p-4 border border-red-100">
                    <p className="text-red-600 text-sm font-bold mb-1 flex items-center gap-1">
                      <AlertCircle size={14} />
                      이런 증상이 나타나면
                    </p>
                    <CollapsibleText>{drugInfo.severe_reaction_advice}</CollapsibleText>
                  </div>
                </>
              ) : (
                <p className="text-sm text-muted text-center py-6">
                  부작용 정보를 불러올 수 없습니다.
                </p>
              )}
            </div>
          )}

          {activeTab === '상호작용' && (
            <div className="space-y-3 animate-in fade-in duration-200">
              {isDrugInfoLoading ? (
                <DrugInfoSkeleton />
              ) : drugInfo?.interactions?.length > 0 ? (
                drugInfo.interactions.map((item, i) => (
                  <div key={i} className="flex gap-3 p-4 bg-orange-50 rounded-xl">
                    <Ban size={16} className="text-orange-500 shrink-0 mt-0.5" />
                    <div className="min-w-0 flex-1">
                      <p className="text-sm font-bold text-ink mb-1">{item.drug}</p>
                      <CollapsibleText>{item.description}</CollapsibleText>
                    </div>
                  </div>
                ))
              ) : (
                <p className="text-sm text-muted text-center py-6">
                  상호작용 정보를 불러올 수 없습니다.
                </p>
              )}
            </div>
          )}
        </div>
      </div>

      <p className="text-xs text-muted text-center leading-relaxed px-2">
        이 정보는 AI가 생성한 참고용 정보입니다. 정확한 복약 지도는 반드시 전문 의료인과
        상의하십시오.
      </p>

      {showDeleteModal && (
        <DeleteConfirmModal
          medicineName={med.medicine_name}
          onConfirm={handleDelete}
          onCancel={() => setShowDeleteModal(false)}
          isDeleting={isDeleting}
        />
      )}
    </div>
  )
}
