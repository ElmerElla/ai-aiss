/**
 * 管理员认证状态管理
 */
import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import { adminApi } from '@/api/admin'
import { encryptPassword } from '@/utils/crypto'

const TOKEN_KEY = 'campus_ai_admin_token'
const ADMIN_ID_KEY = 'campus_ai_admin_id'
const USERNAME_KEY = 'campus_ai_admin_username'
const DISPLAY_NAME_KEY = 'campus_ai_admin_display_name'
const ROLE_KEY = 'campus_ai_admin_role'
const EXPIRES_KEY = 'campus_ai_admin_expires_at'

export const useAdminAuthStore = defineStore('adminAuth', () => {
  const token = ref(localStorage.getItem(TOKEN_KEY) || '')
  const adminId = ref(Number(localStorage.getItem(ADMIN_ID_KEY)) || 0)
  const username = ref(localStorage.getItem(USERNAME_KEY) || '')
  const displayName = ref(localStorage.getItem(DISPLAY_NAME_KEY) || '')
  const role = ref(localStorage.getItem(ROLE_KEY) || '')
  const expiresAt = ref(Number(localStorage.getItem(EXPIRES_KEY)) || 0)

  const isAuthenticated = computed(() => {
    return !!token.value && Date.now() < expiresAt.value
  })

  async function login(usernameInput, password) {
    const encrypted = encryptPassword(password)
    const { data } = await adminApi.login(usernameInput, encrypted)

    token.value = data.access_token
    adminId.value = data.admin_id
    username.value = data.username
    displayName.value = data.display_name
    role.value = data.role
    expiresAt.value = Date.now() + data.expires_in * 1000

    localStorage.setItem(TOKEN_KEY, token.value)
    localStorage.setItem(ADMIN_ID_KEY, String(adminId.value))
    localStorage.setItem(USERNAME_KEY, username.value)
    localStorage.setItem(DISPLAY_NAME_KEY, displayName.value)
    localStorage.setItem(ROLE_KEY, role.value)
    localStorage.setItem(EXPIRES_KEY, String(expiresAt.value))

    return data
  }

  function logout() {
    token.value = ''
    adminId.value = 0
    username.value = ''
    displayName.value = ''
    role.value = ''
    expiresAt.value = 0

    localStorage.removeItem(TOKEN_KEY)
    localStorage.removeItem(ADMIN_ID_KEY)
    localStorage.removeItem(USERNAME_KEY)
    localStorage.removeItem(DISPLAY_NAME_KEY)
    localStorage.removeItem(ROLE_KEY)
    localStorage.removeItem(EXPIRES_KEY)
  }

  return {
    token,
    adminId,
    username,
    displayName,
    role,
    expiresAt,
    isAuthenticated,
    login,
    logout
  }
})
