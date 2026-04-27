<template>
  <div class="login-page">
    <!-- 登录卡片 -->
    <div class="login-card">
      <div class="login-header">
        <div class="login-logo">🎓</div>
        <h1>校园智助</h1>
        <p>校园智能助手 · 登录你的账号</p>
      </div>

      <form @submit.prevent="handleLogin" class="login-form">
        <!-- 学号 -->
        <div class="form-group">
          <label for="studentId">学号</label>
          <div class="input-wrapper">
            <span class="input-icon">🆔</span>
            <input
              id="studentId"
              v-model="form.studentId"
              type="text"
              placeholder="请输入学号"
              autocomplete="username"
              :disabled="isSubmitting"
              required
            />
          </div>
        </div>

        <!-- 密码 -->
        <div class="form-group">
          <label for="password">密码</label>
          <div class="input-wrapper">
            <span class="input-icon">🔒</span>
            <input
              id="password"
              v-model="form.password"
              :type="showPassword ? 'text' : 'password'"
              placeholder="请输入密码"
              autocomplete="current-password"
              :disabled="isSubmitting"
              required
            />
            <button type="button" class="toggle-pwd" @click="showPassword = !showPassword">
              {{ showPassword ? '🙈' : '👁' }}
            </button>
          </div>
        </div>

        <!-- 错误提示 -->
        <Transition name="fade">
          <div v-if="errorMsg" class="error-msg">❌ {{ errorMsg }}</div>
        </Transition>

        <!-- 登录按钮 -->
        <button type="submit" class="login-btn" :disabled="isSubmitting">
          <span v-if="isSubmitting" class="spinner"></span>
          <span v-else>登 录</span>
        </button>
      </form>

      <div class="login-footer">
        <p>首次使用？请联系教务处获取初始密码</p>
        <router-link class="admin-entry" :to="{ name: 'AdminLogin' }">
          管理员入口
        </router-link>
      </div>
    </div>

    <!-- 装饰背景 -->
    <div class="bg-decor">
      <div class="circle c1"></div>
      <div class="circle c2"></div>
      <div class="circle c3"></div>
    </div>
  </div>
</template>

/**
 * 学生登录视图组件
 *
 * 功能介绍：
 * · 提供学生账号（学号 + 密码）登录界面
 * · 密码支持显示/隐藏切换
 * · 登录时调用 authStore.login（内部自动 AES-CBC 加密密码）
 * · 登录成功后自动跳转至 Chat 聊天页
 * · 提供管理员后台入口链接
 * · 界面包含渐变背景装饰与动画卡片效果
 */
<script setup>
import { ref, reactive } from 'vue'
import { useRouter } from 'vue-router'
import { useAuthStore } from '@/stores/auth'

const router = useRouter()
const authStore = useAuthStore()

const form = reactive({
  studentId: '',
  password: ''
})
const showPassword = ref(false)
const isSubmitting = ref(false)
const errorMsg = ref('')

/**
 * 处理学生登录表单提交
 * 前端校验学号与密码非空后调用 Pinia authStore 登录
 * 错误处理：401 显示学号或密码错误，其他显示网络或服务异常
 */
async function handleLogin() {
  errorMsg.value = ''

  if (!form.studentId.trim()) {
    errorMsg.value = '请输入学号'
    return
  }
  if (!form.password) {
    errorMsg.value = '请输入密码'
    return
  }

  isSubmitting.value = true
  try {
    await authStore.login(form.studentId.trim(), form.password)
    router.push({ name: 'Chat' })
  } catch (error) {
    const status = error.response?.status
    const detail = error.response?.data?.detail
    if (status === 401) {
      errorMsg.value = detail || '学号或密码错误'
    } else {
      errorMsg.value = detail || '登录失败，请检查网络后重试'
    }
  } finally {
    isSubmitting.value = false
  }
}
</script>

<style scoped>
.login-page {
  min-height: 100vh;
  display: flex;
  align-items: center;
  justify-content: center;
  background: linear-gradient(135deg, #e8f0fe 0%, #f9fbff 50%, #fff3e0 100%);
  position: relative;
  overflow: hidden;
  padding: 20px;
}

.login-card {
  background: white;
  border-radius: var(--radius-lg);
  box-shadow: var(--shadow-lg);
  padding: 48px 40px;
  width: 100%;
  max-width: 420px;
  z-index: 1;
  animation: cardIn 0.5s ease;
}
@keyframes cardIn {
  from {
    opacity: 0;
    transform: translateY(20px);
  }
  to {
    opacity: 1;
    transform: translateY(0);
  }
}

.login-header {
  text-align: center;
  margin-bottom: 36px;
}
.login-logo {
  font-size: 52px;
  margin-bottom: 8px;
}
.login-header h1 {
  font-size: 28px;
  font-weight: 700;
  color: var(--primary);
  margin-bottom: 8px;
}
.login-header p {
  font-size: 14px;
  color: var(--text-muted);
}

.login-form {
  display: flex;
  flex-direction: column;
  gap: 22px;
}

.form-group label {
  display: block;
  font-size: 13px;
  font-weight: 600;
  color: var(--text-secondary);
  margin-bottom: 8px;
}

.input-wrapper {
  position: relative;
  display: flex;
  align-items: center;
}
.input-icon {
  position: absolute;
  left: 14px;
  font-size: 16px;
  z-index: 1;
  pointer-events: none;
}
.input-wrapper input {
  width: 100%;
  padding: 13px 44px 13px 42px;
  border: 1.5px solid var(--border);
  border-radius: var(--radius-sm);
  font-size: 15px;
  transition: var(--transition);
  background: #fafcff;
}
.input-wrapper input:focus {
  border-color: var(--primary);
  background: white;
  box-shadow: 0 0 0 3px rgba(42, 111, 219, 0.1);
}
.input-wrapper input:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}

.toggle-pwd {
  position: absolute;
  right: 12px;
  background: none;
  font-size: 16px;
  color: var(--text-muted);
  padding: 4px;
}

.error-msg {
  background: var(--danger-light);
  color: var(--danger);
  padding: 11px 16px;
  border-radius: var(--radius-sm);
  font-size: 13px;
  font-weight: 500;
  border: 1px solid #ffcdd2;
}

.login-btn {
  background: var(--primary);
  color: white;
  padding: 14px;
  border-radius: var(--radius-sm);
  font-size: 16px;
  font-weight: 600;
  transition: var(--transition);
  display: flex;
  align-items: center;
  justify-content: center;
  min-height: 50px;
}
.login-btn:hover:not(:disabled) {
  background: var(--primary-dark);
  box-shadow: var(--shadow-md);
}
.login-btn:disabled {
  opacity: 0.7;
  cursor: not-allowed;
}

.spinner {
  width: 22px;
  height: 22px;
  border: 2.5px solid rgba(255, 255, 255, 0.3);
  border-top-color: white;
  border-radius: 50%;
  animation: spin 0.6s linear infinite;
}
@keyframes spin {
  to {
    transform: rotate(360deg);
  }
}

.login-footer {
  text-align: center;
  margin-top: 28px;
  font-size: 12px;
  color: var(--text-light);
}

.admin-entry {
  display: inline-block;
  margin-top: 8px;
  color: #1d4f99;
  font-size: 13px;
  font-weight: 500;
}

.admin-entry:hover {
  text-decoration: underline;
}

/* 装饰圆形 */
.bg-decor {
  position: fixed;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  pointer-events: none;
  z-index: 0;
}
.circle {
  position: absolute;
  border-radius: 50%;
  opacity: 0.07;
}
.c1 {
  width: 450px;
  height: 450px;
  background: var(--primary);
  top: -120px;
  right: -120px;
}
.c2 {
  width: 350px;
  height: 350px;
  background: var(--accent);
  bottom: -100px;
  left: -100px;
}
.c3 {
  width: 220px;
  height: 220px;
  background: var(--primary);
  bottom: 18%;
  right: 8%;
}

@media (max-width: 480px) {
  .login-card {
    padding: 32px 24px;
  }
  .login-logo {
    font-size: 42px;
  }
  .login-header h1 {
    font-size: 24px;
  }
}
</style>