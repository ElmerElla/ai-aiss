<template>
  <div class="change-pwd-view">
    <div class="page-card">
      <!-- 页面标题 -->
      <div class="page-header">
        <h2>🔑 修改密码</h2>
        <p>密码将通过 AES-CBC 加密传输，请牢记新密码</p>
      </div>

      <form @submit.prevent="handleSubmit" class="pwd-form">
        <!-- 当前密码 -->
        <div class="form-group">
          <label for="oldPwd">当前密码</label>
          <div class="input-wrapper">
            <input
              id="oldPwd"
              v-model="form.oldPassword"
              :type="showOld ? 'text' : 'password'"
              placeholder="请输入当前密码"
              autocomplete="current-password"
              :disabled="isSubmitting"
              required
            />
            <button type="button" class="toggle-btn" @click="showOld = !showOld">
              {{ showOld ? '🙈' : '👁' }}
            </button>
          </div>
        </div>

        <!-- 新密码 -->
        <div class="form-group">
          <label for="newPwd">新密码</label>
          <div class="input-wrapper">
            <input
              id="newPwd"
              v-model="form.newPassword"
              :type="showNew ? 'text' : 'password'"
              placeholder="请输入新密码（至少 6 位）"
              autocomplete="new-password"
              :disabled="isSubmitting"
              required
              minlength="6"
            />
            <button type="button" class="toggle-btn" @click="showNew = !showNew">
              {{ showNew ? '🙈' : '👁' }}
            </button>
          </div>

          <!-- 密码强度 -->
          <div v-if="form.newPassword" class="strength-section">
            <div class="strength-bar">
              <div
                class="strength-fill"
                :class="strengthClass"
                :style="{ width: strengthPercent + '%' }"
              />
            </div>
            <span class="strength-label" :class="strengthClass">
              密码强度：{{ strengthText }}
            </span>
          </div>

          <!-- 密码规则提示 -->
          <div v-if="form.newPassword" class="pwd-rules">
            <span :class="{ met: form.newPassword.length >= 6 }">
              {{ form.newPassword.length >= 6 ? '✅' : '⬜' }} 至少 6 位
            </span>
            <span :class="{ met: /[A-Z]/.test(form.newPassword) }">
              {{ /[A-Z]/.test(form.newPassword) ? '✅' : '⬜' }} 包含大写字母
            </span>
            <span :class="{ met: /[0-9]/.test(form.newPassword) }">
              {{ /[0-9]/.test(form.newPassword) ? '✅' : '⬜' }} 包含数字
            </span>
            <span :class="{ met: /[^A-Za-z0-9]/.test(form.newPassword) }">
              {{ /[^A-Za-z0-9]/.test(form.newPassword) ? '✅' : '⬜' }} 包含特殊字符
            </span>
          </div>
        </div>

        <!-- 确认密码 -->
        <div class="form-group">
          <label for="confirmPwd">确认新密码</label>
          <div class="input-wrapper">
            <input
              id="confirmPwd"
              v-model="form.confirmPassword"
              :type="showConfirm ? 'text' : 'password'"
              placeholder="请再次输入新密码"
              autocomplete="new-password"
              :disabled="isSubmitting"
              required
            />
            <button type="button" class="toggle-btn" @click="showConfirm = !showConfirm">
              {{ showConfirm ? '🙈' : '👁' }}
            </button>
          </div>
          <span
            v-if="form.confirmPassword && form.newPassword !== form.confirmPassword"
            class="field-error"
          >
            ❌ 两次输入的密码不一致
          </span>
          <span
            v-if="form.confirmPassword && form.newPassword === form.confirmPassword && form.confirmPassword.length > 0"
            class="field-success"
          >
            ✅ 密码一致
          </span>
        </div>

        <!-- 消息提示 -->
        <Transition name="fade">
          <div v-if="errorMsg" class="msg msg-error">❌ {{ errorMsg }}</div>
        </Transition>
        <Transition name="fade">
          <div v-if="successMsg" class="msg msg-success">✅ {{ successMsg }}</div>
        </Transition>

        <!-- 操作按钮 -->
        <div class="form-actions">
          <router-link to="/profile" class="btn btn-ghost">← 返回</router-link>
          <button
            type="submit"
            class="btn btn-primary"
            :disabled="isSubmitting || !isFormValid"
          >
            <span v-if="isSubmitting" class="spinner-sm"></span>
            <span v-else>确认修改</span>
          </button>
        </div>
      </form>
    </div>
  </div>
</template>

<script setup>
import { ref, reactive, computed } from 'vue'
import { useAuthStore } from '@/stores/auth'

const authStore = useAuthStore()

const form = reactive({
  oldPassword: '',
  newPassword: '',
  confirmPassword: ''
})
const showOld = ref(false)
const showNew = ref(false)
const showConfirm = ref(false)
const isSubmitting = ref(false)
const errorMsg = ref('')
const successMsg = ref('')

// ---- 表单验证 ----
const isFormValid = computed(() => {
  return (
    form.oldPassword.length > 0 &&
    form.newPassword.length >= 6 &&
    form.newPassword === form.confirmPassword
  )
})

// ---- 密码强度计算 ----
const strengthScore = computed(() => {
  const pwd = form.newPassword
  if (!pwd) return 0
  let score = 0
  if (pwd.length >= 6) score += 1
  if (pwd.length >= 10) score += 1
  if (/[A-Z]/.test(pwd)) score += 1
  if (/[0-9]/.test(pwd)) score += 1
  if (/[^A-Za-z0-9]/.test(pwd)) score += 1
  return score
})

const strengthPercent = computed(() => (strengthScore.value / 5) * 100)

const strengthClass = computed(() => {
  if (strengthScore.value <= 1) return 'weak'
  if (strengthScore.value <= 3) return 'medium'
  return 'strong'
})

const strengthText = computed(() => {
  if (strengthScore.value <= 1) return '弱'
  if (strengthScore.value <= 3) return '中等'
  return '强'
})

// ---- 提交 ----
async function handleSubmit() {
  errorMsg.value = ''
  successMsg.value = ''

  if (!isFormValid.value) return

  // 前端校验：新旧密码不能相同（后端 400 也会拦截）
  if (form.oldPassword === form.newPassword) {
    errorMsg.value = '新密码不能与旧密码相同'
    return
  }

  isSubmitting.value = true
  try {
    // changePassword 内部自动 AES-CBC 加密
    const result = await authStore.changePassword(form.oldPassword, form.newPassword)
    // 后端返回: { success: true, student_id: "...", detail: "密码已更新" }
    successMsg.value = result.detail || '密码修改成功！下次登录请使用新密码'
    form.oldPassword = ''
    form.newPassword = ''
    form.confirmPassword = ''
  } catch (error) {
    // 匹配后端错误码
    const status = error.response?.status
    const detail = error.response?.data?.detail
    switch (status) {
      case 400:
        errorMsg.value = detail || '旧密码错误 / 新旧密码相同 / 加密数据无效'
        break
      case 403:
        errorMsg.value = detail || '无权修改其他学生的密码'
        break
      case 404:
        errorMsg.value = detail || '学生信息不存在'
        break
      default:
        errorMsg.value = detail || '修改失败，请稍后重试'
    }
  } finally {
    isSubmitting.value = false
  }
}
</script>

<style scoped>
.change-pwd-view {
  flex: 1;
  padding: 40px 24px;
  overflow-y: auto;
}

.page-card {
  max-width: 520px;
  margin: 0 auto;
  background: white;
  border-radius: var(--radius-lg);
  border: 1px solid var(--border);
  padding: 40px;
}

.page-header {
  margin-bottom: 32px;
}
.page-header h2 {
  font-size: 24px;
  font-weight: 700;
  color: var(--text-primary);
  margin-bottom: 8px;
}
.page-header p {
  font-size: 14px;
  color: var(--text-muted);
}

.pwd-form {
  display: flex;
  flex-direction: column;
  gap: 24px;
}

.form-group {
  display: flex;
  flex-direction: column;
  gap: 8px;
}
.form-group label {
  font-size: 13px;
  font-weight: 600;
  color: var(--text-secondary);
}

.input-wrapper {
  position: relative;
  display: flex;
  align-items: center;
}
.input-wrapper input {
  width: 100%;
  padding: 13px 44px 13px 16px;
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
.toggle-btn {
  position: absolute;
  right: 12px;
  background: none;
  font-size: 16px;
  color: var(--text-muted);
  padding: 4px;
}

/* 密码强度 */
.strength-section {
  display: flex;
  align-items: center;
  gap: 10px;
}
.strength-bar {
  flex: 1;
  height: 4px;
  background: #eee;
  border-radius: 2px;
  overflow: hidden;
}
.strength-fill {
  height: 100%;
  border-radius: 2px;
  transition: width 0.3s ease, background 0.3s ease;
}
.strength-fill.weak {
  background: var(--danger);
}
.strength-fill.medium {
  background: var(--warning);
}
.strength-fill.strong {
  background: var(--success);
}
.strength-label {
  font-size: 11px;
  font-weight: 600;
  white-space: nowrap;
}
.strength-label.weak {
  color: var(--danger);
}
.strength-label.medium {
  color: var(--warning);
}
.strength-label.strong {
  color: var(--success);
}

/* 密码规则 */
.pwd-rules {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  font-size: 12px;
  color: var(--text-light);
}
.pwd-rules span.met {
  color: var(--success);
}

/* 字段提示 */
.field-error {
  font-size: 12px;
  color: var(--danger);
  font-weight: 500;
}
.field-success {
  font-size: 12px;
  color: var(--success);
  font-weight: 500;
}

/* 消息提示 */
.msg {
  padding: 12px 16px;
  border-radius: var(--radius-sm);
  font-size: 14px;
  font-weight: 500;
}
.msg-error {
  background: var(--danger-light);
  color: var(--danger);
  border: 1px solid #ffcdd2;
}
.msg-success {
  background: var(--success-light);
  color: var(--success);
  border: 1px solid #c8e6c9;
}

/* 操作按钮 */
.form-actions {
  display: flex;
  gap: 12px;
  justify-content: flex-end;
  padding-top: 8px;
}
.btn {
  padding: 12px 26px;
  border-radius: var(--radius-sm);
  font-size: 14px;
  font-weight: 600;
  transition: var(--transition);
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 6px;
  text-decoration: none;
  min-height: 46px;
}
.btn-primary {
  background: var(--primary);
  color: white;
}
.btn-primary:hover:not(:disabled) {
  background: var(--primary-dark);
  box-shadow: var(--shadow-md);
}
.btn-primary:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}
.btn-ghost {
  background: transparent;
  color: var(--text-muted);
  border: 1px solid var(--border);
}
.btn-ghost:hover {
  background: #f5f8fc;
  color: var(--text-secondary);
}

.spinner-sm {
  width: 18px;
  height: 18px;
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

@media (max-width: 480px) {
  .page-card {
    padding: 28px 20px;
  }
  .form-actions {
    flex-direction: column-reverse;
  }
  .btn {
    width: 100%;
    justify-content: center;
  }
}
</style>