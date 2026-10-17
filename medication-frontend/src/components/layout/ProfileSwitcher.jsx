'use client'

import { useState, useRef, useEffect } from 'react'
import { useRouter } from 'next/navigation'
import { ChevronDown, Check, User, Plus } from 'lucide-react'
import { useProfile } from '@/contexts/ProfileContext'

export default function ProfileSwitcher() {
  const router = useRouter()
  const { profiles, selectedProfile, selectedProfileId, setSelectedProfileId, RELATION_LABELS } =
    useProfile()
  const [isOpen, setIsOpen] = useState(false)
  const ref = useRef(null)

  // 외부 클릭 시 닫기
  useEffect(() => {
    const handler = (e) => {
      if (ref.current && !ref.current.contains(e.target)) setIsOpen(false)
    }
    document.addEventListener('mousedown', handler)
    return () => document.removeEventListener('mousedown', handler)
  }, [])

  if (!selectedProfile || profiles.length <= 1) {
    // 프로필이 1개 이하면 이름만 표시
    return (
      <div className="flex items-center gap-1.5 text-[13px] text-ink px-2">
        <User size={14} className="text-muted" />
        <span className="font-medium">{selectedProfile?.name || ''}</span>
        <span className="text-[11px] text-muted">
          {selectedProfile
            ? RELATION_LABELS[selectedProfile.relation_type] || selectedProfile.relation_type
            : ''}
        </span>
      </div>
    )
  }

  return (
    <div ref={ref} className="relative">
      <button
        onClick={() => setIsOpen((prev) => !prev)}
        className="flex items-center gap-1.5 text-[13px] text-ink px-2.5 py-1.5 rounded-lg hover:bg-surface-2 transition-colors"
      >
        <User size={14} className="text-muted" />
        <span className="font-medium">{selectedProfile.name}</span>
        <span className="text-[11px] text-muted">
          {RELATION_LABELS[selectedProfile.relation_type] || selectedProfile.relation_type}
        </span>
        <ChevronDown
          size={13}
          className={`text-muted transition-transform ${isOpen ? 'rotate-180' : ''}`}
        />
      </button>

      {isOpen && (
        <div className="absolute top-full left-0 mt-1.5 w-52 bg-surface border border-line rounded-xl shadow-lg z-[100] overflow-hidden">
          <div className="px-3 py-2 border-b border-line">
            <p className="text-[11px] text-muted font-medium tracking-wide uppercase">
              프로필 전환
            </p>
          </div>
          <ul className="py-1">
            {profiles.map((profile) => (
              <li key={profile.id}>
                <button
                  onClick={() => {
                    setSelectedProfileId(profile.id)
                    setIsOpen(false)
                  }}
                  className="w-full flex items-center justify-between px-3 py-2 hover:bg-surface-2 transition-colors text-left"
                >
                  <div className="flex items-center gap-2">
                    <div className="w-7 h-7 rounded-full bg-surface-2 flex items-center justify-center flex-shrink-0">
                      <User size={13} className="text-muted" />
                    </div>
                    <div>
                      <p className="text-[13px] font-medium text-ink">{profile.name}</p>
                      <p className="text-[11px] text-muted">
                        {RELATION_LABELS[profile.relation_type] || profile.relation_type}
                      </p>
                    </div>
                  </div>
                  {profile.id === selectedProfileId && (
                    <Check size={14} className="text-ink flex-shrink-0" />
                  )}
                </button>
              </li>
            ))}
          </ul>
          <div className="px-3 py-2 border-t border-line">
            <button
              onClick={() => {
                router.push('/mypage?tab=family')
                setIsOpen(false)
              }}
              className="w-full flex items-center gap-2 px-3 py-2 hover:bg-surface-2 rounded-lg transition-colors text-left"
            >
              <Plus size={13} className="text-muted" />
              <span className="text-[13px] text-muted">프로필 추가</span>
            </button>
          </div>
        </div>
      )}
    </div>
  )
}
