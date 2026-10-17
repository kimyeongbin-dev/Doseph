'use client'
import PropTypes from 'prop-types'

export default function LoadingSpinner({ size = 'md', className = '' }) {
  const sizeClasses = {
    sm: 'w-4 h-4',
    md: 'w-8 h-8',
    lg: 'w-12 h-12',
  }

  return (
    <div
      className={`inline-block animate-spin rounded-full border-2 border-line border-t-accent ${sizeClasses[size]} ${className}`}
    />
  )
}

LoadingSpinner.propTypes = {
  size: PropTypes.oneOf(['sm', 'md', 'lg']),
  className: PropTypes.string,
}

LoadingSpinner.defaultProps = {
  size: 'md',
  className: '',
}
