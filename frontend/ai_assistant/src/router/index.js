import { createRouter, createWebHistory } from 'vue-router'
import { useAuthStore } from '@/stores/auth'
import { useAdminAuthStore } from '@/stores/adminAuth'

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

// 导航守卫：未登录重定向到登录页，已登录重定向到主页
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