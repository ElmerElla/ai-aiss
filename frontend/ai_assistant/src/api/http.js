/**
 * Axios HTTP 客户端实例（学生端）
 *
 * 功能介绍：
 * -----------
 * 本模块创建并导出一个配置好的 Axios 实例，用于学生端所有 API 请求。
 *
 * 请求拦截器：
 * - 自动从 localStorage 读取 campus_ai_token
 * - 为每个请求附加 Authorization: Bearer {token} 请求头
 *
 * 响应拦截器：
 * - 捕获 401 未授权响应
 * - 自动调用 authStore.logout() 清除登录状态
 * - 自动跳转至登录页面
 *
 * 基础配置：
 * - baseURL: /api/v1
 * - timeout: 60000ms
 * - Content-Type: application/json
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