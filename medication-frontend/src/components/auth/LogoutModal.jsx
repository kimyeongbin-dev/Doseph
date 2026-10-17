'use client'
import { useState } from 'react'
import { useRouter } from 'next/navigation'
import { LogOut, UserX } from 'lucide-react'
import PropTypes from 'prop-types'
import api from '@/lib/api'
import { markLoggedOut } from '@/lib/authStatus'
import toast from 'react-hot-toast'

export function useLogout() {
  const router = useRouter()
  const [showLogoutModal, setShowLogoutModal] = useState(false)

  const handleLogout = async () => {
    setShowLogoutModal(false)
    try {
      await api.post('/api/v1/auth/logout')
      toast.success('로그아웃 되었습니다.')
    } catch (err) {
      toast.error('로그아웃 중 오류가 발생했습니다.')
    } finally {
      // 사용자가 직접 수행한 로그아웃 — 별도 안내 불필요, 조용히 NONE 으로 복귀
      markLoggedOut()
      router.push('/')
    }
  }

  return { showLogoutModal, setShowLogoutModal, handleLogout }
}

export function useDeleteAccount() {
  const router = useRouter()
  const [showDeleteModal, setShowDeleteModal] = useState(false)

  const handleDeleteAccount = async () => {
    setShowDeleteModal(false)
    try {
      await api.delete('/api/v1/auth/account')
      toast.success('회원 탈퇴가 완료되었습니다.')
      markLoggedOut()
      router.push('/')
    } catch (err) {
      toast.error('회원 탈퇴 중 오류가 발생했습니다.')
    }
  }

  return { showDeleteModal, setShowDeleteModal, handleDeleteAccount }
}

export function DeleteAccountModal({ onClose, onConfirm }) {
  return (
    <div className="fixed inset-0 bg-black/50 z-[200] flex items-center justify-center p-4">
      <div className="bg-surface rounded-[32px] p-8 w-full max-w-sm shadow-xl">
        <div className="flex items-center justify-center w-14 h-14 bg-red-50 rounded-full mx-auto mb-5">
          <UserX size={24} className="text-red-500" />
        </div>
        <h3 className="text-xl font-black text-ink mb-2 text-center">회원 탈퇴</h3>
        <p className="text-muted text-sm text-center mb-2">정말로 탈퇴하시겠습니까?</p>
        <p className="text-red-400 text-xs text-center mb-8">
          탈퇴 시 모든 데이터가 삭제되며 복구할 수 없습니다.
        </p>
        <div className="flex gap-3">
          <button
            onClick={onClose}
            className="flex-1 py-3 rounded-2xl bg-surface-2 text-muted font-bold hover:bg-surface-2 transition-all cursor-pointer"
          >
            취소
          </button>
          <button
            onClick={onConfirm}
            className="flex-1 py-3 rounded-2xl bg-red-500 text-accent-ink font-black hover:bg-red-600 transition-all cursor-pointer"
          >
            탈퇴하기
          </button>
        </div>
      </div>
    </div>
  )
}

DeleteAccountModal.propTypes = {
  onClose: PropTypes.func.isRequired,
  onConfirm: PropTypes.func.isRequired,
}

export default function LogoutModal({ onClose, onConfirm }) {
  return (
    <div className="fixed inset-0 bg-black/50 z-[200] flex items-center justify-center p-4">
      <div className="bg-surface rounded-[32px] p-8 w-full max-w-sm shadow-xl">
        <div className="flex items-center justify-center w-14 h-14 bg-surface-2 rounded-full mx-auto mb-5">
          <LogOut size={24} className="text-muted" />
        </div>
        <h3 className="text-xl font-black text-ink mb-2 text-center">로그아웃</h3>
        <p className="text-muted text-sm text-center mb-8">정말 로그아웃 하시겠습니까?</p>
        <div className="flex gap-3">
          <button
            onClick={onClose}
            className="flex-1 py-3 rounded-2xl bg-surface-2 text-muted font-bold hover:bg-surface-2 transition-all cursor-pointer"
          >
            취소
          </button>
          <button
            onClick={onConfirm}
            className="flex-1 py-3 rounded-2xl bg-accent text-accent-ink font-black hover:brightness-110 transition-all cursor-pointer"
          >
            로그아웃
          </button>
        </div>
      </div>
    </div>
  )
}

LogoutModal.propTypes = {
  onClose: PropTypes.func.isRequired,
  onConfirm: PropTypes.func.isRequired,
}
