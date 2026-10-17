'use client'
import { AlertCircle } from 'lucide-react'
import PropTypes from 'prop-types'

export default function EmptyState({
  icon,
  title,
  message,
  actionLabel,
  onAction,
  actionClassName,
}) {
  return (
    <div className="flex flex-col items-center justify-center py-12 px-6 text-center bg-surface rounded-2xl shadow-sm border border-line">
      <div className="mb-4 text-muted">{icon || <AlertCircle size={48} />}</div>
      <h3 className="text-lg font-bold text-ink mb-1">{title}</h3>
      <p className="text-muted text-sm mb-6 max-w-[200px] leading-relaxed">{message}</p>
      {actionLabel && (
        <button
          onClick={onAction}
          className={
            actionClassName ||
            'bg-accent text-accent-ink px-8 py-3 rounded-xl font-black text-sm hover:brightness-110 transition-all shadow-lg cursor-pointer active:scale-95'
          }
        >
          {actionLabel}
        </button>
      )}
    </div>
  )
}

EmptyState.propTypes = {
  icon: PropTypes.node,
  title: PropTypes.string.isRequired,
  message: PropTypes.string.isRequired,
  actionLabel: PropTypes.string,
  onAction: PropTypes.func,
  actionClassName: PropTypes.string,
}

EmptyState.defaultProps = {
  icon: null,
  actionLabel: null,
  onAction: null,
  actionClassName: null,
}
