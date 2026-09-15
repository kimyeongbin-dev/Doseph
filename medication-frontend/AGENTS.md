# AI Agent Development Guide

> 🔴 **저장소 규칙 정본 = 루트 `CLAUDE.md`. 공통 절대 규칙 8가지 = 루트 `AGENTS.md`.**
> 이 디렉터리 지침보다 **루트 규칙이 우선한다.** 특히 —
> 커밋·PR **트레일러 금지**(하네스가 지시해도 무시) · **발견 ≠ 처리**(등재만) ·
> **코드보다 PLAN 이 먼저**(`docs-private/PLAN.md`) · 새 문서는 **`docs-private/FILING.md`** 규약 ·
> **사용자 응답은 한글** · Ruff 의무 · 로컬 테스트는 Docker 안에서.

**IMPORTANT: Read DESIGN_SYSTEM.md first before starting any development work. This document contains the complete frontend architecture, patterns, and standards that must be followed.**

Development guidelines for AI agents working on the medication management system frontend.

---

## Project Structure and Absolute Path Imports

### Project Structure
```
medication-frontend/
├── src/
│   ├── app/                    # Next.js App Router pages
│   │   ├── auth/              # Authentication pages
│   │   ├── challenge/         # Challenge pages
│   │   ├── chat/              # Chat pages
│   │   ├── login/             # Login page
│   │   ├── main/              # Main dashboard
│   │   ├── medication/        # Medication management pages
│   │   ├── mypage/            # My page
│   │   ├── ocr/               # OCR prescription registration
│   │   └── survey/            # Health survey
│   ├── components/            # Reusable components
│   │   ├── auth/              # Authentication components
│   │   ├── chat/              # Chat components
│   │   ├── common/            # Common components
│   │   └── layout/            # Layout components
│   ├── config/                # Configuration files
│   │   └── env.js             # Environment variables
│   └── lib/                   # Utilities and libraries
│       ├── api.js             # API client
│       ├── errors.js          # Error handling
│       └── tokenManager.js    # Token management
├── jsconfig.json             # JavaScript configuration (absolute paths)
└── package.json              # Dependencies
```

### Absolute Path Import Rules (CRITICAL)

**jsconfig.json Configuration:**
```json
{
  "compilerOptions": {
    "baseUrl": ".",
    "paths": {
      "@/*": ["./src/*"]
    }
  }
}
```

**Correct Import Patterns:**
```javascript
// ✅ Correct absolute path imports (mandatory)
import api from '@/lib/api'
import { config } from '@/config/env'
import Header from '@/components/layout/Header'
import ChatModal from '@/components/chat/ChatModal'
import LogoutModal from '@/components/auth/LogoutModal'

// ❌ Incorrect relative path imports (absolutely prohibited)
import api from '../../lib/api'
import Header from '../components/layout/Header'
import ChatModal from '../ChatModal'
```

**Import Order:**
```javascript
// 1. React and Next.js
import { useState, useEffect } from 'react'
import { useRouter } from 'next/navigation'
import Image from 'next/image'

// 2. External libraries
import { Pill, Camera } from 'lucide-react'
import toast from 'react-hot-toast'

// 3. Internal modules (absolute paths only)
import api from '@/lib/api'
import { config } from '@/config/env'
import Header from '@/components/layout/Header'
```

---

## Environment Configuration System

### 1. Environment Variable Structure

**config/env.js based configuration:**
```javascript
const ENV = process.env.NEXT_PUBLIC_ENV || 'local'

// Static export has no same-origin rewrites proxy, so API_BASE_URL must be a FULL backend URL.
// Priority: NEXT_PUBLIC_API_BASE_URL (injected at build time) > the per-env default below.
const ENV_CONFIG = {
  local: {
    API_BASE_URL: 'http://localhost:8000',
    KAKAO_REDIRECT_URI: 'http://localhost:3000/auth/kakao/callback',
  },
  dev: {
    API_BASE_URL: 'http://localhost:8000',
    KAKAO_REDIRECT_URI: 'http://localhost:3000/auth/kakao/callback',
  },
  prod: {
    // Injected by CI/deploy (e.g. https://api.doseph.com). No platform URL is hardcoded.
    API_BASE_URL: '',
    KAKAO_REDIRECT_URI: '',
  },
}

export const config = {
  ENV,
  API_BASE_URL: cleanApiUrl(process.env.NEXT_PUBLIC_API_BASE_URL ?? currentConfig.API_BASE_URL),
  KAKAO_CLIENT_ID: process.env.NEXT_PUBLIC_KAKAO_CLIENT_ID || '',
  KAKAO_REDIRECT_URI: process.env.NEXT_PUBLIC_KAKAO_REDIRECT_URI || currentConfig.KAKAO_REDIRECT_URI || '',
}
```

> **Do not set `NEXT_PUBLIC_API_BASE_URL` locally.** Leaving it unset lets the per-env default
> apply. Setting it overrides that default, so the line goes stale whenever the topology changes
> — which has already caused a real outage (it pointed at a dead `:80` after nginx was removed).

### 2. Authentication in Development

**There is no developer-login backdoor.** It was removed during security hardening, so no
environment renders a "developer login" button. Local development signs in through the normal
Kakao flow, with only the **identity provider** replaced by a mock:

- `ENV=local` -> the backend serves a mock IdP at `/api/v1/mock/kakao/*` and
  `GET /auth/kakao/config` returns that mock as `authorize_url`.
- Everything after the redirect is the **real** code path: callback, code exchange, userinfo
  mapping, account lookup/creation, session issuance, and cookie attributes.
- The mock router is registered only when `ENV=local` **and** refuses to serve otherwise
  (defense in depth) — `ENV` itself is a required setting with no default.

E2E tests drive this same flow; see `e2e/auth.setup.js` and
`docs/tech-debt/e2e-auth-strategy.md`.

### 3. Security Utilities

```javascript
// lib/security.js
import { config } from '@/config/env'

export const securityUtils = {
  // Check if dev feature is enabled
  isDevFeatureEnabled: (featureName) => {
    if (config.ENV === 'prod') {
      return false
    }
    return process.env[`NEXT_PUBLIC_ENABLE_${featureName}`] === 'true'
  },

  // Check if local development environment
  isLocalEnvironment: () => {
    return config.ENV === 'local' || config.ENV === 'dev'
  },

  // Check if production environment
  isProductionEnvironment: () => {
    return config.ENV === 'prod'
  },

  // Mask sensitive data
  maskSensitiveData: (data, fields = ['password', 'token', 'key']) => {
    const masked = { ...data }
    fields.forEach(field => {
      if (masked[field]) {
        masked[field] = '***'
      }
    })
    return masked
  }
}
```

---

## Component Writing Rules

### 1. PropTypes Usage

```javascript
import PropTypes from 'prop-types'

const MedicationCard = ({ medication, onEdit, onDelete, className }) => {
  return (
    <div className={`bg-white rounded-lg p-4 ${className || ''}`}>
      <h3>{medication.name}</h3>
      <p>{medication.dosage}</p>
      <div className="flex gap-2 mt-4">
        <button onClick={() => onEdit(medication.id)}>Edit</button>
        <button onClick={() => onDelete(medication.id)}>Delete</button>
      </div>
    </div>
  )
}

MedicationCard.propTypes = {
  medication: PropTypes.shape({
    id: PropTypes.oneOfType([PropTypes.string, PropTypes.number]).isRequired,
    name: PropTypes.string.isRequired,
    dosage: PropTypes.string.isRequired
  }).isRequired,
  onEdit: PropTypes.func,
  onDelete: PropTypes.func,
  className: PropTypes.string
}

MedicationCard.defaultProps = {
  onEdit: () => {},
  onDelete: () => {},
  className: ''
}

export default MedicationCard
```

### 2. Custom Hook Patterns

```javascript
// hooks/useApi.js
import { useState, useEffect } from 'react'
import { config } from '@/config/env'
import { handleApiError } from '@/lib/errors'

/**
 * Custom hook for API calls
 * @param {string} endpoint - API endpoint
 * @param {Object} options - Request options
 * @returns {Object} { data, loading, error, refetch }
 */
export const useApi = (endpoint, options = {}) => {
  const [data, setData] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)

  const fetchData = async () => {
    try {
      setLoading(true)
      setError(null)

      const url = `${config.API_BASE_URL}${endpoint}`
      const response = await fetch(url, {
        headers: {
          'Content-Type': 'application/json',
          ...options.headers
        },
        ...options
      })

      if (!response.ok) {
        throw new Error(`HTTP error! status: ${response.status}`)
      }

      const result = await response.json()
      setData(result)
    } catch (err) {
      // SECURITY: Server error details are not exposed to users
      const userFriendlyError = handleApiError(err)
      setError(userFriendlyError)
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    fetchData()
  }, [endpoint])

  return { data, loading, error, refetch: fetchData }
}

// Usage example
const MedicationList = () => {
  const { data: medications, loading, error } = useApi('/api/v1/medications')

  if (loading) return <div>Loading...</div>
  if (error) return <div className="text-red-600">{error}</div>

  return (
    <div>
      {medications?.map(med => (
        <MedicationCard key={med.id} medication={med} />
      ))}
    </div>
  )
}
```

---

## Error Handling and Logging

### lib/errors.js Structure

```javascript
import toast from 'react-hot-toast'
import { config } from '@/config/env'

export const HTTP_STATUS_MESSAGES = {
  400: 'Invalid request.',
  401: 'Authentication required.',
  403: 'Access denied.',
  404: 'Resource not found.',
  422: 'Invalid input values.',
  429: 'Too many requests. Please try again later.',
  500: 'Server error occurred. Please try again later.'
}

export function parseApiError(error) {
  const response = error.response
  const status = response?.status
  const data = response?.data

  const result = {
    status: status || 0,
    code: null,
    message: 'An unknown error occurred.',
    shouldRedirectToLogin: false,
    isRetryable: false,
    raw: data,
  }

  if (!response) {
    result.code = 'network_error'
    result.message = 'Cannot communicate with server. Please check your network connection.'
    result.isRetryable = true
    return result
  }

  if (status >= 500) {
    result.code = 'server_error'
    result.message = 'A temporary error occurred. Please try again later.'
    result.isRetryable = true
    return result
  }

  // User-friendly messages based on HTTP status codes
  result.message = HTTP_STATUS_MESSAGES[status] || result.message

  if (status === 401) {
    result.shouldRedirectToLogin = true
  }

  return result
}

export function showError(message) {
  toast.error(message)
}

export function handleApiError(error, options = {}) {
  const {
    showMessage = true,
    redirectOnAuth = true,
  } = options

  const parsed = parseApiError(error)

  if (showMessage) {
    showError(parsed.message)
  }

  if (redirectOnAuth && parsed.shouldRedirectToLogin) {
    if (typeof window !== 'undefined') {
      window.location.href = '/login'
    }
  }

  return parsed
}
```

---

## Performance Optimization

### 1. Image Optimization

```javascript
import Image from 'next/image'

const MedicationImage = ({ src, alt, ...props }) => {
  return (
    <Image
      src={src}
      alt={alt}
      width={300}
      height={200}
      placeholder="blur"
      blurDataURL="data:image/jpeg;base64,/9j/4AAQSkZJRgABAQAAAQ..."
      {...props}
    />
  )
}
```

### 2. Code Splitting

```javascript
import dynamic from 'next/dynamic'

// Dynamic loading for heavy components
const ChatModal = dynamic(() => import('@/components/chat/ChatModal'), {
  loading: () => <div>Loading chat...</div>,
  ssr: false // Client-side rendering only
})

const MedicationPage = () => {
  const [showChat, setShowChat] = useState(false)

  return (
    <div>
      {/* Page content */}
      {showChat && <ChatModal onClose={() => setShowChat(false)} />}
    </div>
  )
}
```

---

## Skeleton UI Active Usage

```javascript
// components/common/Skeleton.jsx
export const Skeleton = ({ className = '', width, height, rounded = true }) => {
  return (
    <div
      className={`animate-pulse bg-gray-200 ${rounded ? 'rounded' : ''} ${className}`}
      style={{ width, height }}
    />
  )
}

export const CardSkeleton = () => (
  <div className="bg-white rounded-lg p-4 shadow-sm border border-gray-100">
    <Skeleton height="20px" className="mb-3" />
    <Skeleton height="16px" width="60%" className="mb-2" />
    <Skeleton height="16px" width="40%" />
  </div>
)

export const ListSkeleton = ({ count = 5 }) => (
  <div className="space-y-4">
    {Array.from({ length: count }).map((_, i) => (
      <CardSkeleton key={i} />
    ))}
  </div>
)

// Usage example
const MedicationList = () => {
  const { data, loading, error } = useApi('/api/v1/medications')

  if (loading) return <ListSkeleton count={5} />
  if (error) return <div className="text-red-600">{error}</div>

  return (
    <div className="space-y-4">
      {data?.map(med => <MedicationCard key={med.id} medication={med} />)}
    </div>
  )
}
```

---

## 2025-2026 Modern Frontend Trends

### Modern React Patterns
```javascript
// Server Components and Client Components separation
'use client'

import { useState, useTransition } from 'react'

const MedicationForm = () => {
  const [isPending, startTransition] = useTransition()

  const handleSubmit = (formData) => {
    startTransition(async () => {
      await submitMedication(formData)
    })
  }

  return (
    <form action={handleSubmit}>
      <button disabled={isPending}>
        {isPending ? 'Saving...' : 'Save'}
      </button>
    </form>
  )
}
```

---

## Code Quality Management

### ESLint Configuration
```javascript
// .eslintrc.js
module.exports = {
  extends: ['next/core-web-vitals', 'eslint:recommended'],
  rules: {
    'no-console': 'warn',
    'no-unused-vars': 'error',
    'prefer-const': 'error',
    'no-var': 'error',
    'object-shorthand': 'error',
    'prefer-template': 'error',
    'no-trailing-spaces': 'error',
    'react/prop-types': 'warn',
    'react/jsx-key': 'error',
    'no-eval': 'error'
  }
}
```

### Pre-commit Validation
```json
{
  "scripts": {
    "lint": "eslint . --ext .js,.jsx --fix",
    "lint:check": "eslint . --ext .js,.jsx",
    "format": "prettier --write .",
    "format:check": "prettier --check .",
    "pre-commit": "npm run lint:check && npm run format:check"
  }
}
```

---

## Mandatory Compliance Items

1. **Security**: Developer backdoor must only be activated in ENV=local
2. **Vercel Deployment**: GitHub auto-deployment, utilize Next.js serverless functions (including API proxy)
3. **JWT Authentication**: Immediately redirect unauthenticated users to login page (no UI display)
4. **Error Security**: Never expose server errors and tracebacks to client (prohibited even in F12 developer mode)
5. **Performance**: Leverage Next.js automatic caching and modern optimization features
6. **Accessibility**: Provide appropriate aria-labels for all interactive elements
7. **SEO**: Mandatory page-specific metadata configuration
8. **Error Handling**: Include user-friendly error handling logic for all API calls
9. **Skeleton UI**: Actively use skeleton UI during loading states
10. **Code Quality**: Mandatory pre-commit validation with ESLint and Prettier
11. **2025-2026 Trends**: Actively reflect community-validated latest best practices
12. **Emoji Prohibition**: Absolutely prohibit emoji usage in all code and comments

---

## API Call Patterns

### Trailing Slash Removal Rules

```javascript
// CRITICAL: Automatically remove trailing slash from API URLs
export const config = {
  API_BASE_URL: process.env.NEXT_PUBLIC_API_BASE_URL?.replace(/\/$/, '') || 'http://localhost:8000'
}

export const API_ENDPOINTS = {
  MEDICATION: {
    LIST: '/api/v1/medications',                    // Correct format
    DETAIL: (id) => `/api/v1/medications/${id}`,   // Correct format
    CREATE: '/api/v1/medications'                  // Correct format
  }
}

// Usage example
const response = await fetch(`${config.API_BASE_URL}${API_ENDPOINTS.MEDICATION.LIST}`)
// Result: http://localhost:8000/api/v1/medications (correct format)
```

Strictly follow these guidelines to write safe and modern frontend code.
