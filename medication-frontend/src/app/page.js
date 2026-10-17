'use client'
import { useRouter } from 'next/navigation'
import { useEffect, useRef, useState } from 'react' // ← [수정] useEffect, useState 추가
import { Camera, Pill, MessageCircle, ArrowRight } from 'lucide-react'

const features = [
  {
    Icon: Camera,
    title: '처방전 자동 인식',
    desc: '사진 한 장으로 약품 정보를 AI가 자동 등록해요. 복잡한 입력은 필요 없어요.',
  },
  {
    Icon: Pill,
    title: '스마트 복약 알림',
    desc: '복약 시간을 절대 놓치지 않도록 맞춤 알림을 보내드려요.',
  },
  {
    Icon: MessageCircle,
    title: 'AI 복약 상담',
    desc: '약에 대한 궁금증을 AI에게 언제든지 물어보세요. 24시간 답변 가능해요.',
  },
]

const useCases = [
  { label: '어르신 복약 관리', desc: '복잡한 복약 일정을 한눈에' },
  { label: '가족 건강 케어', desc: '가족의 복약을 한 곳에서' },
  { label: '만성질환 관리', desc: '꾸준한 복약 습관 형성' },
]

// ← [추가] 전역 변수로 자동 스크롤 상태 관리
let isAutoScrolling = false
let autoScrollTimeout = null

// ← [추가] 배경 이미지 배열
const backgroundImages = ['/hero_bg_1.png', '/hero_bg_2.png', '/hero_bg_3.png']

export default function LandingPage() {
  const router = useRouter()
  // ← [추가] 현재 배경 이미지 인덱스 상태
  const [currentBgIndex, setCurrentBgIndex] = useState(0)
  // ← [추가] 배경 이미지 슬라이드쇼 타이머 ref
  const bgSlideShowTimeoutRef = useRef(null)

  // ← [추가] 배경 이미지 슬라이드쇼 로직
  useEffect(() => {
    const startSlideShow = () => {
      bgSlideShowTimeoutRef.current = setTimeout(() => {
        setCurrentBgIndex((prevIndex) => (prevIndex + 1) % backgroundImages.length)
      }, 3000) // 5초마다 다음 이미지로 전환
    }

    startSlideShow()

    return () => {
      if (bgSlideShowTimeoutRef.current) {
        clearTimeout(bgSlideShowTimeoutRef.current)
      }
    }
  }, [currentBgIndex])

  // ← [추가] 자동 스크롤 함수
  const handleAutoScroll = () => {
    if (isAutoScrolling) return

    isAutoScrolling = true
    console.log('[Auto-Scroll] 시작')

    const featuresSection = document.getElementById('features-section')
    if (featuresSection) {
      featuresSection.scrollIntoView({ behavior: 'smooth', block: 'start' })
      console.log('[Auto-Scroll] 1단계: 기능 소개로 이동')
    }

    autoScrollTimeout = setTimeout(() => {
      const useCasesSection = document.getElementById('usecases-section')
      if (useCasesSection) {
        useCasesSection.scrollIntoView({ behavior: 'smooth', block: 'start' })
        console.log('[Auto-Scroll] 2단계: 사용 사례로 이동')
      }

      autoScrollTimeout = setTimeout(() => {
        const ctaSection = document.getElementById('cta-section')
        if (ctaSection) {
          ctaSection.scrollIntoView({ behavior: 'smooth', block: 'start' })
          console.log('[Auto-Scroll] 3단계: CTA로 이동')
        }

        isAutoScrolling = false
        console.log('[Auto-Scroll] 완료')
      }, 2000)
    }, 2000)
  }

  // ← [추가] 사용자 스크롤 감지
  const handleUserScroll = () => {
    if (isAutoScrolling) {
      isAutoScrolling = false
      if (autoScrollTimeout) {
        clearTimeout(autoScrollTimeout)
        autoScrollTimeout = null
      }
      console.log('[Auto-Scroll] 사용자 스크롤로 인해 중단됨')
    }
  }

  return (
    <div className="min-h-screen bg-bg" onWheel={handleUserScroll} onTouchMove={handleUserScroll}>
      {/* ── 히어로 섹션 ── full-width 다크 */}
      <section
        className="relative w-full min-h-[620px] flex items-center justify-center overflow-hidden bg-black"
        // ← [추가] 배경 이미지 동적 설정 및 페이드 애니메이션
        style={{
          backgroundImage: `url('${backgroundImages[currentBgIndex]}')`,
          backgroundSize: 'cover',
          backgroundPosition: 'center',
          backgroundAttachment: 'fixed',
          transition: 'background-image 1s ease-in-out', // 1초에 걸쳐 부드럽게 전환
        }}
      >
        {/* ← [추가] 배경 이미지 위의 다크 오버레이 (텍스트 가독성 유지) */}
        <div className="absolute inset-0 bg-black/40" />

        {/* 그리드 패턴 */}
        <div
          className="absolute inset-0 pointer-events-none opacity-20"
          style={{
            backgroundImage: `
              linear-gradient(to right, rgba(255,255,255,0.1) 1px, transparent 1px),
              linear-gradient(to bottom, rgba(255,255,255,0.1) 1px, transparent 1px)
            `,
            backgroundSize: '72px 72px',
          }}
        />

        {/* 코너 마커 */}
        <div className="absolute top-0 left-1/2 -translate-x-[400px] w-px h-10 bg-white/10 hidden md:block" />
        <div className="absolute top-0 right-1/2 translate-x-[400px] w-px h-10 bg-white/10 hidden md:block" />

        {/* 그라디언트 블랍 */}
        <div
          className="absolute bottom-0 left-1/2 pointer-events-none opacity-40 md:opacity-100"
          style={{
            transform: 'translateX(-340px)',
            width: '580px',
            height: '400px',
            background:
              'radial-gradient(ellipse at center bottom, rgba(249,115,22,0.3) 0%, transparent 70%)',
          }}
        />
        <div
          className="absolute bottom-0 left-1/2 pointer-events-none opacity-40 md:opacity-100"
          style={{
            transform: 'translateX(-60px)',
            width: '580px',
            height: '400px',
            background:
              'radial-gradient(ellipse at center bottom, rgba(20,184,166,0.3) 0%, transparent 70%)',
          }}
        />

        {/* 중앙 아이콘 */}
        <div className="absolute bottom-0 left-1/2 -translate-x-1/2 pointer-events-none select-none">
          <div className="w-[140px] h-[140px] bg-white/5 border border-white/10 rounded-[40px] translate-y-12 rotate-12 flex items-center justify-center backdrop-blur-sm">
            <Pill size={44} className="text-white/10" />
          </div>
        </div>

        {/* 콘텐츠 */}
        <div className="relative z-10 text-center px-6 max-w-3xl mx-auto py-28">
          <p className="text-white/50 text-[11px] font-black mb-6 tracking-[0.3em] uppercase">
            AI 기반 지능형 복약 관리
          </p>
          <h1 className="text-5xl md:text-7xl lg:text-8xl font-black text-white leading-[1.05] tracking-tighter mb-8">
            복약의 새로운
            <span className="text-white/40">기준</span>
          </h1>
          <p className="text-white/60 text-base md:text-lg mb-12 leading-relaxed max-w-xl mx-auto font-medium">
            처방전 촬영으로 시작하는 스마트한 건강 관리.
            <br className="hidden md:block" />
            AI가 당신의 안전한 복약 파트너가 되어드립니다.
          </p>
          <div className="flex flex-col sm:flex-row gap-4 justify-center">
            <button
              onClick={() => router.push('/login')}
              className="px-10 py-4 bg-accent text-accent-ink text-sm font-black rounded-full hover:scale-105 transition-all shadow-xl cursor-pointer flex items-center justify-center gap-2 group"
            >
              지금 시작하기
              <ArrowRight size={16} className="group-hover:translate-x-1 transition-transform" />
            </button>
            <button
              onClick={handleAutoScroll}
              className="px-10 py-4 text-white text-sm font-black rounded-full border border-white/25 hover:bg-white/10 transition-all cursor-pointer"
            >
              서비스 소개
            </button>
          </div>

          {/* ← [추가] 배경 이미지 인디케이터 (선택사항) */}
          <div className="flex gap-2 justify-center mt-12">
            {backgroundImages.map((_, index) => (
              <div
                key={index}
                className={`w-2 h-2 rounded-full transition-all ${
                  index === currentBgIndex ? 'bg-white w-8' : 'bg-white/40'
                }`}
              />
            ))}
          </div>
        </div>
      </section>

      {/* ── 기능 소개 ── */}
      <section id="features-section" className="max-w-6xl mx-auto px-6 py-32">
        <div className="text-center mb-20">
          <p className="text-[11px] font-black text-muted tracking-[0.3em] uppercase mb-4">
            Core Value
          </p>
          <h2 className="text-4xl md:text-5xl font-black text-ink tracking-tighter">
            더 쉽고, 더 정확하게
          </h2>
        </div>
        <div className="grid md:grid-cols-3 gap-8">
          {features.map(({ Icon, title, desc }, i) => (
            <div
              key={i}
              className="p-10 bg-surface-2 rounded-[40px] border border-transparent hover:border-line hover:bg-surface hover:shadow-[var(--shadow-pop)] transition-all duration-300 group"
            >
              <div className="w-14 h-14 bg-accent rounded-2xl flex items-center justify-center text-accent-ink mb-8 group-hover:scale-110 transition-transform shadow-lg">
                <Icon size={24} />
              </div>
              <h3 className="text-xl font-black text-ink mb-4">{title}</h3>
              <p className="text-muted text-base leading-relaxed font-medium">{desc}</p>
            </div>
          ))}
        </div>
      </section>

      {/* ── 사용 사례 ── */}
      <section id="usecases-section" className="bg-surface-2 py-32">
        <div className="max-w-6xl mx-auto px-6">
          <div className="text-center mb-16">
            <p className="text-[11px] font-black text-muted tracking-[0.3em] uppercase mb-4">
              Target
            </p>
            <h2 className="text-3xl md:text-4xl font-black text-ink tracking-tighter">
              모두를 위한 건강 관리
            </h2>
          </div>
          <div className="grid md:grid-cols-3 gap-6">
            {useCases.map((u, i) => (
              <div
                key={i}
                className="flex flex-col p-10 rounded-[40px] bg-surface border border-line hover:shadow-[var(--shadow-pop)] transition-all duration-300"
              >
                <div className="w-12 h-12 bg-accent-soft rounded-2xl flex items-center justify-center text-lg font-black text-accent mb-6">
                  0{i + 1}
                </div>
                <h3 className="font-black text-ink text-xl mb-3">{u.label}</h3>
                <p className="text-muted font-medium">{u.desc}</p>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* ── CTA 섹션 ── */}
      <section id="cta-section" className="py-32 text-center bg-black relative overflow-hidden">
        <div className="absolute inset-0 opacity-10">
          <div className="absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 w-[600px] h-[600px] bg-accent rounded-full blur-[120px]" />
        </div>
        <div className="relative z-10">
          <p className="text-white/50 text-xs font-black mb-6 tracking-[0.3em] uppercase">
            Join us today
          </p>
          <h2 className="text-4xl md:text-5xl font-black text-white mb-6 tracking-tighter">
            안전한 복약의 시작
          </h2>
          <p className="text-white/50 text-lg mb-12 font-medium">지금 바로 무료로 체험해보세요</p>
          <button
            onClick={() => router.push('/login')}
            className="px-12 py-5 bg-accent text-accent-ink font-black rounded-full hover:scale-110 transition-all cursor-pointer text-base shadow-2xl"
          >
            시작하기
          </button>
        </div>
      </section>
    </div>
  )
}
