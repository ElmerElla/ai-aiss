<template>
  <div class="profile-view">
    <div class="page-card">
      <!-- 页面标题 -->
      <div class="page-header">
        <h2>👤 个人信息</h2>
        <p>查看你的学生账户信息和系统状态</p>
      </div>

      <!-- 信息卡片网格 -->
      <div class="info-grid">
        <div class="info-item">
          <div class="info-label">学号</div>
          <div class="info-value">{{ authStore.studentId }}</div>
        </div>

        <div class="info-item">
          <div class="info-label">账户状态</div>
          <div class="info-value">
            <span class="status-badge active">✅ 已认证</span>
          </div>
        </div>

        <div class="info-item">
          <div class="info-label">令牌有效期至</div>
          <div class="info-value">{{ expiresAtFormatted }}</div>
        </div>

        <div class="info-item">
          <div class="info-label">设备标识 (DID)</div>
          <div class="info-value mono">{{ deviceId }}</div>
        </div>

        <div class="info-item">
          <div class="info-label">当前会话数</div>
          <div class="info-value">{{ chatStore.sessions.length }} 个对话</div>
        </div>

        <div class="info-item">
          <div class="info-label">总消息数</div>
          <div class="info-value">{{ totalMessages }} 条</div>
        </div>

        <div class="info-item">
          <div class="info-label">套餐</div>
          <div class="info-value">Free Plan</div>
        </div>

        <div class="info-item">
          <div class="info-label">认证方式</div>
          <div class="info-value">JWT Bearer Token</div>
        </div>
      </div>

      <!-- 操作按钮 -->
      <div class="page-actions">
        <router-link to="/change-password" class="btn btn-outline">
          🔑 修改密码
        </router-link>
        <button class="btn btn-danger-outline" @click="handleClearData">
          🗑 清除所有对话
        </button>
      </div>

      <!-- 系统信息区 -->
      <div class="system-section">
        <h3>🖥 系统信息</h3>
        <div class="system-info">
          <div class="sys-row">
            <span class="sys-label">服务状态</span>
            <span class="sys-value">
              <span class="status-dot" :class="healthStatusClass"></span>
              {{ healthStatusText }}
            </span>
          </div>
          <div class="sys-row" v-if="versionInfo">
            <span class="sys-label">服务名称</span>
            <span class="sys-value">{{ versionInfo.name }}</span>
          </div>
          <div class="sys-row" v-if="versionInfo">
            <span class="sys-label">服务版本</span>
            <span class="sys-value">v{{ versionInfo.version }}</span>
          </div>
          <div class="sys-row">
            <span class="sys-label">API 基础路径</span>
            <span class="sys-value mono">/api/v1</span>
          </div>
        </div>

        <button class="btn btn-ghost btn-sm" @click="refreshSystemInfo" :disabled="systemLoading">
          {{ systemLoading ? '检查中...' : '🔄 刷新状态' }}
        </button>
      </div>
    </div>
  </div>
</template>

/**
 * 个人信息视图组件
 *
 * 功能介绍：
 * · 展示当前学生的账户信息（学号、认证状态、Token 有效期、设备标识 DID）
 * · 展示聊天统计数据（当前会话数、总消息数）
 * · 提供修改密码与清除所有对话的操作入口
 * · 展示系统状态信息（服务健康检查、版本号、API 基础路径）
 * · 支持手动刷新系统状态
 */
<script setup>
import { ref, computed, onMounted } from 'vue'
import { useAuthStore } from '@/stores/auth'
import { useChatStore } from '@/stores/chat'
import { getDeviceId } from '@/utils/session'
import { systemApi } from '@/api/system'

const authStore = useAuthStore()
const chatStore = useChatStore()
const deviceId = getDeviceId()

const healthStatus = ref('loading') // 'ok' | 'error' | 'loading'
const versionInfo = ref(null)
const systemLoading = ref(false)

/**
 * 格式化 Token 过期时间为本地可读字符串
 * @returns {string}
 */
const expiresAtFormatted = computed(() => {
  if (!authStore.expiresAt) return '未知'
  return new Date(authStore.expiresAt).toLocaleString('zh-CN', {
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit'
  })
})

/**
 * 计算所有会话中的消息总数
 * @returns {number}
 */
const totalMessages = computed(() => {
  return chatStore.sessions.reduce((sum, s) => sum + s.messages.length, 0)
})

/**
 * 根据健康状态返回对应的 CSS 类名
 * @returns {string} 'green' | 'yellow' | 'red'
 */
const healthStatusClass = computed(() => {
  switch (healthStatus.value) {
    case 'ok': return 'green'
    case 'loading': return 'yellow'
    default: return 'red'
  }
})

/**
 * 根据健康状态返回对应的中文描述
 * @returns {string}
 */
const healthStatusText = computed(() => {
  switch (healthStatus.value) {
    case 'ok': return '正常运行'
    case 'loading': return '检查中...'
    default: return '连接异常'
  }
})

/**
 * 调用后端健康检查接口
 * 更新 healthStatus 为 'ok' 或 'error'
 */
async function checkHealth() {
  try {
    const { data } = await systemApi.healthCheck()
    healthStatus.value = data.status // 后端返回 { status: "ok", service: "AI 校园助手" }
  } catch {
    healthStatus.value = 'error'
  }
}

/**
 * 调用后端版本信息接口
 * 更新 versionInfo 对象
 */
async function fetchVersion() {
  try {
    const { data } = await systemApi.getVersion()
    versionInfo.value = data // 后端返回 { name: "AI 校园助手", version: "1.0.0" }
  } catch {
    // 忽略
  }
}

/**
 * 刷新系统信息（并行调用健康检查与版本接口）
 * 自动设置 systemLoading 状态
 */
async function refreshSystemInfo() {
  systemLoading.value = true
  healthStatus.value = 'loading'
  await Promise.all([checkHealth(), fetchVersion()])
  systemLoading.value = false
}

/**
 * 处理清除所有对话记录操作
 * 弹出确认对话框后调用 chatStore.clearAllSessions()
 */
function handleClearData() {
  if (confirm('确定要清除所有对话记录吗？此操作无法撤销。')) {
    chatStore.clearAllSessions()
    alert('已清除所有对话记录')
  }
}

onMounted(() => {
  refreshSystemInfo()
})
</script>

<style scoped>
.profile-view {
  flex: 1;
  padding: 40px 24px;
  overflow-y: auto;
}

.page-card {
  max-width: 680px;
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

/* 信息网格 */
.info-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 16px;
  margin-bottom: 28px;
}
.info-item {
  padding: 16px 18px;
  background: #f8faff;
  border-radius: var(--radius-sm);
  border: 1px solid var(--border-light);
  transition: var(--transition);
}
.info-item:hover {
  border-color: var(--primary);
  box-shadow: var(--shadow-sm);
}
.info-label {
  font-size: 12px;
  color: var(--text-light);
  margin-bottom: 6px;
  font-weight: 500;
  text-transform: uppercase;
  letter-spacing: 0.3px;
}
.info-value {
  font-size: 15px;
  font-weight: 600;
  color: var(--text-primary);
}
.info-value.mono {
  font-family: 'Menlo', 'Monaco', monospace;
  font-size: 11px;
  word-break: break-all;
  font-weight: 500;
}

.status-badge {
  display: inline-block;
  padding: 3px 10px;
  border-radius: 12px;
  font-size: 13px;
  font-weight: 500;
}
.status-badge.active {
  background: var(--success-light);
  color: var(--success);
}

/* 操作按钮 */
.page-actions {
  display: flex;
  gap: 12px;
  margin-bottom: 32px;
  flex-wrap: wrap;
}
.btn {
  padding: 10px 22px;
  border-radius: var(--radius-sm);
  font-size: 14px;
  font-weight: 500;
  transition: var(--transition);
  display: inline-flex;
  align-items: center;
  gap: 6px;
  text-decoration: none;
}
.btn-outline {
  background: white;
  border: 1.5px solid var(--primary);
  color: var(--primary);
}
.btn-outline:hover {
  background: var(--primary-light);
}
.btn-danger-outline {
  background: white;
  border: 1.5px solid var(--danger);
  color: var(--danger);
}
.btn-danger-outline:hover {
  background: var(--danger-light);
}
.btn-ghost {
  background: transparent;
  color: var(--text-muted);
  border: 1px solid var(--border);
}
.btn-ghost:hover {
  background: #f5f8fc;
}
.btn-sm {
  padding: 7px 16px;
  font-size: 13px;
  margin-top: 12px;
}

/* 系统信息 */
.system-section {
  border-top: 1px solid var(--border-light);
  padding-top: 28px;
}
.system-section h3 {
  font-size: 16px;
  font-weight: 600;
  margin-bottom: 16px;
  color: var(--text-secondary);
}
.system-info {
  display: flex;
  flex-direction: column;
  gap: 12px;
}
.sys-row {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 8px 14px;
  background: #fafcff;
  border-radius: var(--radius-sm);
  font-size: 13px;
}
.sys-label {
  color: var(--text-muted);
  font-weight: 500;
}
.sys-value {
  display: flex;
  align-items: center;
  gap: 6px;
  font-weight: 600;
  color: var(--text-primary);
}
.sys-value.mono {
  font-family: monospace;
  font-weight: 500;
}

.status-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  display: inline-block;
}
.status-dot.green {
  background: var(--success);
  box-shadow: 0 0 6px rgba(67, 160, 71, 0.4);
}
.status-dot.yellow {
  background: var(--warning);
  animation: pulse 1.5s ease-in-out infinite;
}
.status-dot.red {
  background: var(--danger);
}
@keyframes pulse {
  0%, 100% { opacity: 1; }
  50% { opacity: 0.4; }
}

@media (max-width: 600px) {
  .info-grid {
    grid-template-columns: 1fr;
  }
  .page-card {
    padding: 28px 20px;
  }
}
</style>