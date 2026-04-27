/**
 * Vue Router 路由配置模块
 *
 * 功能介绍：
 * · 定义学生端与管理员端的所有前端路由映射
 * · 使用 createWebHistory 实现基于 HTML5 History API 的路由模式
 * · 配置路由元信息（requiresAuth / guest / requiresAdminAuth / adminGuest）用于权限控制
 * · 全局前置导航守卫 beforeEach：根据认证状态自动重定向未登录/已登录用户
 * · 通配符路由处理 404 并智能重定向（/admin/* 到 /admin，其余到 /）
 */
import { createRouter, createWebHistory } from 'vue-router'
import { useAuthStore } from '@/stores/auth'
import { useAdminAuthStore } from '@/stores/adminAuth'

/** 路由表配置 */
const routes = [
  {
    path: '/admin/login',
    name: 'AdminLogin',
    component: () => import('@/views/AdminLoginView.vue'),
    meta: { adminGuest: true }
  },
  {
    path: '/admin',
    name: 'AdminDashboard',
    component: () => import('@/views/AdminDashboardView.vue'),
    meta: { requiresAdminAuth: true }
  },
  {
    path: '/login',
    name: 'Login',
    component: () => import('@/views/LoginView.vue'),
    meta: { guest: true }
  },
  {
    path: '/',
    component: () => import('@/layouts/MainLayout.vue'),
    meta: { requiresAuth: true },
    children: [
      {
        path: '',
        name: 'Chat',
        component: () => import('@/views/ChatView.vue')
      },
      {
        path: 'profile',
        name: 'Profile',
        component: () => import('@/views/ProfileView.vue')
      },
      {
        path: 'change-password',
        name: 'ChangePassword',
        component: () => import('@/views/ChangePasswordView.vue')
      }
    ]
  },
  {
    path: '/:pathMatch(.*)*',
    redirect: (to) => (to.path.startsWith('/admin') ? '/admin' : '/')
  }
]

const router = createRouter({
  history: createWebHistory(),
  routes
})

/**
 * 全局前置导航守卫
 *
 * 权限控制逻辑：
 * · 访问管理员页面 (requiresAdminAuth) → 检查管理员登录状态，未登录跳转 AdminLogin
 * · 访问管理员登录页 (adminGuest) → 已登录管理员自动跳转 AdminDashboard
 * · 访问学生页面 (requiresAuth) → 检查学生登录状态，未登录跳转 Login
 * · 访问学生登录页 (guest) → 已登录学生自动跳转 Chat
 */
router.beforeEach((to, _from, next) => {
  const auth = useAuthStore()
  const adminAuth = useAdminAuthStore()

  if (to.meta.requiresAdminAuth && !adminAuth.isAuthenticated) {
    next({ name: 'AdminLogin' })
  } else if (to.meta.adminGuest && adminAuth.isAuthenticated) {
    next({ name: 'AdminDashboard' })
  } else if (to.meta.requiresAuth && !auth.isAuthenticated) {
    next({ name: 'Login' })
  } else if (to.meta.guest && auth.isAuthenticated) {
    next({ name: 'Chat' })
  } else {
    next()
  }
})

export default router