<template>
  <div class="admin-login-page">
    <div class="admin-login-card">
      <div class="header">
        <div class="logo">🛠️</div>
        <h1>管理员后台</h1>
        <p>课表管理与调课审核入口</p>
      </div>

      <form class="form" @submit.prevent="handleLogin">
        <div class="form-group">
          <label for="username">用户名</label>
          <input
            id="username"
            v-model="form.username"
            type="text"
            placeholder="请输入管理员用户名"
            autocomplete="username"
            :disabled="isSubmitting"
            required
          />
        </div>

        <div class="form-group">
          <label for="password">密码</label>
          <div class="pwd-wrap">
            <input
              id="password"
              v-model="form.password"
              :type="showPassword ? 'text' : 'password'"
              placeholder="请输入管理员密码"
              autocomplete="current-password"
              :disabled="isSubmitting"
              required
            />
            <button type="button" class="toggle" @click="showPassword = !showPassword">
              {{ showPassword ? '隐藏' : '显示' }}
            </button>
          </div>
        </div>

        <Transition name="fade">
          <div v-if="errorMsg" class="error-msg">{{ errorMsg }}</div>
        </Transition>

        <button class="submit-btn" type="submit" :disabled="isSubmitting">
          <span v-if="isSubmitting" class="spinner"></span>
          <span v-else>登录管理员后台</span>
        </button>
      </form>

      <div class="footer">
        <router-link :to="{ name: 'Login' }">返回学生登录</router-link>
      </div>
    </div>
  </div>
</template>

/**
 * 管理员登录视图组件
 *
 * 功能介绍：
 * · 提供管理员后台登录界面（用户名 + 密码）
 * · 密码支持显示/隐藏切换
 * · 登录时调用 adminAuthStore.login（内部自动 AES-CBC 加密密码）
 * · 登录成功后自动跳转至 AdminDashboard 仪表盘
 * · 错误处理：401 用户名或密码错误，403 账号被禁用
 * · 提供返回学生登录入口链接
 */
<script setup>
import { reactive, ref } from 'vue'
import { useRouter } from 'vue-router'
import { useAdminAuthStore } from '@/stores/adminAuth'

const router = useRouter()
const adminAuth = useAdminAuthStore()

const form = reactive({
  username: '',
  password: ''
})
const showPassword = ref(false)
const isSubmitting = ref(false)
const errorMsg = ref('')

/**
 * 处理管理员登录表单提交
 * 前端校验用户名与密码非空后调用 Pinia adminAuthStore 登录
 * 错误处理：401 显示用户名或密码错误，403 显示账号不可用
 */
async function handleLogin() {
  errorMsg.value = ''

  if (!form.username.trim()) {
    errorMsg.value = '请输入管理员用户名'
    return
  }
  if (!form.password) {
    errorMsg.value = '请输入密码'
    return
  }

  isSubmitting.value = true
  try {
    await adminAuth.login(form.username.trim(), form.password)
    router.push({ name: 'AdminDashboard' })
  } catch (error) {
    const status = error.response?.status
    const detail = error.response?.data?.detail

    if (status === 401) {
      errorMsg.value = detail || '用户名或密码错误'
    } else if (status === 403) {
      errorMsg.value = detail || '账号不可用，请联系系统管理员'
    } else {
      errorMsg.value = detail || '登录失败，请稍后重试'
    }
  } finally {
    isSubmitting.value = false
  }
}
</script>

<style scoped>
.admin-login-page {
  min-height: 100vh;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 20px;
  background:
    radial-gradient(circle at 20% 15%, rgba(42, 111, 219, 0.12), transparent 36%),
    radial-gradient(circle at 80% 85%, rgba(245, 124, 0, 0.12), transparent 40%),
    linear-gradient(135deg, #f6f9ff 0%, #fffdf8 100%);
}

.admin-login-card {
  width: 100%;
  max-width: 430px;
  background: #fff;
  border: 1px solid var(--border-light);
  border-radius: var(--radius-lg);
  box-shadow: var(--shadow-lg);
  padding: 34px 30px;
}

.header {
  text-align: center;
  margin-bottom: 26px;
}

.logo {
  font-size: 44px;
  margin-bottom: 8px;
}

.header h1 {
  font-size: 27px;
  color: #1d4f99;
  margin-bottom: 6px;
}

.header p {
  font-size: 13px;
  color: var(--text-muted);
}

.form {
  display: flex;
  flex-direction: column;
  gap: 18px;
}

.form-group label {
  display: block;
  margin-bottom: 8px;
  font-size: 13px;
  font-weight: 600;
  color: var(--text-secondary);
}

.form-group input {
  width: 100%;
  border: 1px solid var(--border);
  border-radius: var(--radius-sm);
  padding: 12px 14px;
  font-size: 14px;
  transition: var(--transition);
}

.form-group input:focus {
  border-color: var(--primary);
  box-shadow: 0 0 0 3px rgba(42, 111, 219, 0.12);
}

.pwd-wrap {
  position: relative;
}

.pwd-wrap input {
  padding-right: 72px;
}

.toggle {
  position: absolute;
  top: 50%;
  right: 8px;
  transform: translateY(-50%);
  border: none;
  background: transparent;
  color: var(--text-muted);
  font-size: 12px;
  padding: 6px 8px;
}

.error-msg {
  border-radius: var(--radius-sm);
  background: var(--danger-light);
  color: var(--danger);
  border: 1px solid #ffcdd2;
  padding: 10px 12px;
  font-size: 13px;
}

.submit-btn {
  margin-top: 4px;
  border: none;
  border-radius: var(--radius-sm);
  background: linear-gradient(120deg, #2a6fdb, #4f8ae6);
  color: #fff;
  font-size: 15px;
  font-weight: 600;
  padding: 13px;
  min-height: 46px;
  display: flex;
  align-items: center;
  justify-content: center;
  transition: var(--transition);
}

.submit-btn:hover:not(:disabled) {
  box-shadow: var(--shadow-md);
  transform: translateY(-1px);
}

.submit-btn:disabled {
  opacity: 0.72;
  cursor: not-allowed;
}

.spinner {
  width: 20px;
  height: 20px;
  border: 2.5px solid rgba(255, 255, 255, 0.3);
  border-top-color: #fff;
  border-radius: 50%;
  animation: spin 0.7s linear infinite;
}

.footer {
  margin-top: 18px;
  text-align: center;
}

.footer a {
  color: #1d4f99;
  font-size: 13px;
  font-weight: 500;
}

@keyframes spin {
  to {
    transform: rotate(360deg);
  }
}
</style>
