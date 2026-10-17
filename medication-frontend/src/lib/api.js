/**
 * API 클라이언트 (JavaScript 복구 버전)
 */

import axios from 'axios'
import { config } from '@/config/env'
import { parseApiError, ERROR_CODE_MESSAGES, HTTP_STATUS_MESSAGES } from './errors'

const api = axios.create({
  baseURL: config.API_BASE_URL, // 이미 cleanApiUrl로 처리됨
  withCredentials: true,
  timeout: 60000,
})

api.interceptors.request.use(
  (config) => config,
  (error) => Promise.reject(error),
)

// 응답 인터셉터: 에러 처리 + RTR
api.interceptors.response.use(
  (response) => response,
  async (error) => {
    const originalRequest = error.config
    const status = error.response?.status

    // AuthGuard에서 인터셉터 비활성화 요청 시 바로 에러 반환
    if (originalRequest.skipAuthInterceptor) {
      return Promise.reject(error)
    }

    // 401 Unauthorized - 토큰 갱신 시도
    if (status === 401 && !originalRequest._retry) {
      originalRequest._retry = true

      if (originalRequest.url?.includes('/auth/refresh')) {
        return Promise.reject(error)
      }

      try {
        const { refreshToken } = await import('./authManager')
        const refreshed = await refreshToken()

        if (refreshed) {
          return api.request(originalRequest)
        }
      } catch (refreshError) {
        return Promise.reject(refreshError)
      }
    }

    const parsed = parseApiError(error)
    error.parsed = parsed

    return Promise.reject(error)
  },
)

export default api
export { parseApiError, ERROR_CODE_MESSAGES, HTTP_STATUS_MESSAGES } from './errors'
export { handleApiError, showError } from './errors'
