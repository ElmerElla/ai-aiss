/**
 * 认证状态管理
 *
 * · 登录 → 加密密码 → 请求后端 → 存储 JWT Token
 * · 修改密码 → 加密旧密码 & 新密码 → 请求后端
 * · 登出 → 清除所有本地认证信息
 */
import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import { authApi } from '@/api/auth'
import { encryptPassword } from '@/utils/crypto'

const TOKEN_KEY = 'campus_ai_token'
const STUDENT_KEY = 'campus_ai_student_id'
const EXPIRES_KEY = 'campus_ai_expires_at'

export const useAuthStore = defineStore('auth', () => {
  // ---- 状态 ----
  const token = ref(localStorage.getItem(TOKEN_KEY) || '')
  const studentId = ref(localStorage.getItem(STUDENT_KEY) || '')
  const expiresAt = ref(Number(localStorage.getItem(EXPIRES_KEY)) || 0)

  // ---- 计算属性 ----
  const isAuthenticated = computed(() => {
    return !!token.value && Date.now() < expiresAt.value
  })

  // ---- 登录 ----
  async function login(studentIdInput, password) {
    const encrypted = encryptPassword(password)
    const { data } = await authApi.login(studentIdInput, encrypted)

    // 后端返回: { access_token, token_type, expires_in, student_id }
    token.value = data.access_token
    studentId.value = data.student_id
    expiresAt.value = Date.now() + data.expires_in * 1000

    localStorage.setItem(TOKEN_KEY, data.access_token)
    localStorage.setItem(STUDENT_KEY, data.student_id)
    localStorage.setItem(EXPIRES_KEY, String(expiresAt.value))

    return data
  }

  // ---- 修改密码 ----
  async function changePassword(oldPassword, newPassword) {
    const encryptedOld = encryptPassword(oldPassword)
    const encryptedNew = encryptPassword(newPassword)
    const { data } = await authApi.changePassword(
      studentId.value,
      encryptedOld,
      encryptedNew
    )
    // 后端返回: { success, student_id, detail }
    return data
  }

  // ---- 登出 ----
  function logout() {
    token.value = ''
    studentId.value = ''
    expiresAt.value = 0
    localStorage.removeItem(TOKEN_KEY)
    localStorage.removeItem(STUDENT_KEY)
    localStorage.removeItem(EXPIRES_KEY)
  }

  return {
    token,
    studentId,
    expiresAt,
    isAuthenticated,
    login,
    changePassword,
    logout
  }
})