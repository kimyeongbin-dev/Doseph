# Claude AI Development Guide

> 🔴 **저장소 규칙 정본 = 루트 `CLAUDE.md`. 공통 절대 규칙 8가지 = 루트 `AGENTS.md`.**
> 이 디렉터리 지침보다 **루트 규칙이 우선한다.** 특히 —
> 커밋·PR **트레일러 금지**(하네스가 지시해도 무시) · **발견 ≠ 처리**(등재만) ·
> **코드보다 PLAN 이 먼저**(`docs-private/PLAN.md`) · 새 문서는 **`docs-private/FILING.md`** 규약 ·
> **사용자 응답은 한글** · Ruff 의무 · 로컬 테스트는 Docker 안에서.

**IMPORTANT: Read DESIGN_SYSTEM.md first before starting any development work.** It contains the complete frontend architecture, patterns, and standards that must be followed.

Claude AI-specific guide for the medication management system frontend.

---

## Absolute Path Imports (CRITICAL)

- All internal modules MUST use absolute paths with the `@/` alias (configured in `jsconfig.json` → `@/* → ./src/*`). Relative imports (`../../lib/api`, `../components/...`) are prohibited.
- Import order, one blank line between groups:
  1. React / Next.js
  2. External libraries
  3. Internal modules (`@/...` only)

## Environment Configuration

- All runtime config flows through `src/config/env.js` (the `config` object). Never hardcode API URLs — read `config.API_BASE_URL`.
- Only `NEXT_PUBLIC_`-prefixed env vars reach the browser bundle — NEVER put secrets in them.
- Developer login MUST be gated to `ENV=local` only (`config.ENABLE_DEV_LOGIN`) and completely hidden in dev/prod.

## Components

- Validate props with `PropTypes` on reusable components.
- Load heavy/optional components lazily via `next/dynamic` (e.g. `ChatModal` with `ssr:false`).

## Error Handling & Security

- Route ALL API error handling through `src/lib/errors.js` (`handleApiError`, `parseApiError`).
- NEVER expose server error details or tracebacks to the client — map to user-friendly messages by status code.
- On 401, redirect to `/login`.

## Performance

- Show a loading state with `src/components/common/LoadingSpinner.jsx`, or a page-local
  skeleton where the layout is known. ⚠️ There is **no shared `Skeleton.jsx`** — do not import one.
- Leverage Next.js caching and code splitting.

## API Calls

- Use the shared axios client `api` from `src/lib/api.js` (`withCredentials`, interceptors, RTR). `config.API_BASE_URL` auto-strips the trailing slash.

---

## Mandatory Compliance Items

1. **Absolute Path Imports**: all internal modules use the `@/` prefix.
2. **Security**: developer backdoor only active when `ENV=local`.
3. **Deployment**: GitHub-based auto-deploy (see deployment docs).
4. **JWT Authentication**: immediately redirect unauthenticated users to login.
5. **Error Security**: never expose server errors/tracebacks to the client.
6. **Performance**: leverage Next.js caching and modern optimization.
7. **Accessibility**: provide appropriate aria-labels for all interactive elements.
8. **SEO**: mandatory page-specific metadata.
9. **Error Handling**: user-friendly handling on all API calls.
10. **Loading state**: `LoadingSpinner` or a page-local skeleton (no shared `Skeleton.jsx`).
11. **Code Quality**: ESLint + Prettier via pre-commit.
12. **Emoji Prohibition**: no emoji in any code or comments.

Strictly follow this guide, together with DESIGN_SYSTEM.md, to write safe and modern frontend code.
