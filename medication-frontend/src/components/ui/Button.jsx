'use client'
import PropTypes from 'prop-types'

// ── 재사용 버튼 프리미티브 ────────────────────────────────────────────
// 흐름: variant/size prop -> 시맨틱 토큰 기반 클래스 매핑 -> 스타일 세부를 호출측에서 은닉
//       (색·반경·그림자 하드코딩 금지, 토큰만 참조 => 저결합)
const VARIANTS = {
  primary: 'bg-accent text-accent-ink hover:brightness-110 shadow-[var(--shadow-card)]',
  secondary: 'bg-surface text-ink border border-line hover:border-accent/40',
  ghost: 'bg-transparent text-accent hover:bg-accent-soft',
  glass:
    'bg-white/15 text-white border border-white/40 backdrop-blur-md hover:bg-white/25 hover:border-white/60',
}

// 최소 터치 영역 44px 보장 (h-11 = 44px)
const SIZES = {
  md: 'h-11 px-5 text-sm',
  lg: 'h-14 px-8 text-base',
}

export default function Button({
  variant = 'primary',
  size = 'md',
  className = '',
  children,
  ...props
}) {
  const base =
    'inline-flex items-center justify-center gap-2 rounded-full font-bold tracking-tight ' +
    'transition-all cursor-pointer active:scale-[0.98] ' +
    'focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent ' +
    'disabled:opacity-50 disabled:cursor-not-allowed'

  return (
    <button className={`${base} ${VARIANTS[variant]} ${SIZES[size]} ${className}`} {...props}>
      {children}
    </button>
  )
}

Button.propTypes = {
  variant: PropTypes.oneOf(['primary', 'secondary', 'ghost', 'glass']),
  size: PropTypes.oneOf(['md', 'lg']),
  className: PropTypes.string,
  children: PropTypes.node,
}
