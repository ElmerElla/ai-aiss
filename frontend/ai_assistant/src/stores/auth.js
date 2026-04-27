/**
 * 学生认证状态管理 (Pinia Store)
 *
 * 功能介绍：
 * · 管理学生端的登录状态（JWT Token、学号、过期时间）
 * · 登录时通过 AES-CBC 加密密码后发送至后端
 * · 修改密码时同步加密旧密码与新密码
 * · 登出时清除 localStorage 与内存中的认证信息
 * · 提供 isAuthenticated 计算属性自动判断 Token 是否有效
 *
 * 存储键：campus_ai_token / campus_ai_student_id / campus_ai_expires_at
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
  /**
   * 判断当前学生是否已登录且 Token 未过期
   * @returns {boolean}
   */
  const isAuthenticated = computed(() => {
    return !!token.value && Date.now() < expiresAt.value
  })

  // ---- 登录 ----
  /**
   * 学生登录
   * @param {string} studentIdInput 学号
   * @param {string} password 明文密码（内部自动 AES-CBC 加密）
   * @returns {Promise<Object>} 后端登录响应数据 { access_token, token_type, expires_in, student_id }
   */
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
  /**
   * 修改当前学生密码
   * @param {string} oldPassword 当前明文密码
   * @param {string} newPassword 新明文密码
   * @returns {Promise<Object>} 后端响应 { success, student_id, detail }
   */
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
  /**
   * 登出并清除所有本地认证状态
   * 会同步清空 Pinia state 与 localStorage 中的 Token、学号、过期时间
   */
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