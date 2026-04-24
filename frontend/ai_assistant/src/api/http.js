/**
 * Axios 实例 — 统一拦截器
 * · 请求拦截：自动附加 JWT Bearer Token
 * · 响应拦截：401 自动登出并跳转登录页
 */
import axios from 'axios'
import { useAuthStore } from '@/stores/auth'
import router from '@/router'

const http = axios.create({
  baseURL: '/api/v1',
  timeout: 60000,
  headers: {
    'Content-Type': 'application/json'
  }
})

// ---- 请求拦截 ----
http.interceptors.request.use(
  (config) => {
    // 方式1：直接读取 localStorage (最安全，无依赖)
    const token = localStorage.getItem('campus_ai_token')
    if (token) {
      config.headers.Authorization = `Bearer ${token}`
    }
    
    // 方式2：如果是必须用 store (例如需要响应式状态)，请在函数内部 import
    // const { useAuthStore } = await import('@/stores/auth')
    // const auth = useAuthStore()
    
    return config
  },
  (error) => Promise.reject(error)
)

// ---- 响应拦截 ----
http.interceptors.response.use(
  (response) => response,
  (error) => {
    if (error.response?.status === 401) {
      const auth = useAuthStore()
      auth.logout()
      router.push({ name: 'Login' })
    }
    return Promise.reject(error)
  }
)

export default http