/**
 * 管理员 Axios 实例
 * · 请求拦截：自动附加管理员 JWT
 * · 响应拦截：401 自动清理管理员状态并跳转管理员登录页
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
