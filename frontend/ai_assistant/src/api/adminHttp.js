/**
 * Axios HTTP 客户端实例（管理员端）
 *
 * 功能介绍：
 * -----------
 * 本模块创建并导出一个配置好的 Axios 实例，用于管理员后台所有 API 请求。
 *
 * 与学生端 http.js 的区别：
 * - 使用独立的 localStorage 键名（campus_ai_admin_token）
 * - 401 时跳转至管理员登录页（AdminLogin）
 * - 清理管理员认证状态（adminAuthStore.logout）
 *
 * 基础配置：
 * - baseURL: /api/v1
 * - timeout: 60000ms
 * - Content-Type: application/json
 */
import axios from 'axios'
import router from '@/router'
import { useAdminAuthStore } from '@/stores/adminAuth'

const ADMIN_TOKEN_KEY = 'campus_ai_admin_token'

const adminHttp = axios.create({
  baseURL: '/api/v1',
  timeout: 60000,
  headers: {
    'Content-Type': 'application/json'
  }
})

adminHttp.interceptors.request.use(
  (config) => {
    const token = localStorage.getItem(ADMIN_TOKEN_KEY)
    if (token) {
      config.headers.Authorization = `Bearer ${token}`
    }
    return config
  },
  (error) => Promise.reject(error)
)

adminHttp.interceptors.response.use(
  (response) => response,
  (error) => {
    if (error.response?.status === 401) {
      const adminAuth = useAdminAuthStore()
      adminAuth.logout()
      router.push({ name: 'AdminLogin' })
    }
    return Promise.reject(error)
  }
)

export default adminHttp
