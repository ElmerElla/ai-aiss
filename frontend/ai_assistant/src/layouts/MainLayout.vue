<template>
  <div class="layout">
    <!-- ==================== 左侧边栏 ==================== -->
    <aside class="sidebar" :class="{ collapsed: sidebarCollapsed }">
      <!-- 顶部 Logo & 关闭按钮 -->
      <div class="sidebar-top">
        <div class="logo">🎓 校园智助</div>
        <button class="collapse-btn" @click="sidebarCollapsed = !sidebarCollapsed" title="收起侧栏">
          {{ sidebarCollapsed ? '☰' : '✕' }}
        </button>
      </div>

      <!-- 新建对话 -->
      <button class="new-chat-btn" @click="handleNewChat">
        <span class="btn-icon">+</span>
        <span>新建对话</span>
      </button>

      <!-- 搜索框 -->
      <div class="search-box">
        <span class="search-icon">🔍</span>
        <input
          v-model="chatStore.searchKeyword"
          type="text"
          placeholder="搜索记录..."
        />
        <button
          v-if="chatStore.searchKeyword"
          class="search-clear"
          @click="chatStore.searchKeyword = ''"
        >
          ✕
        </button>
      </div>

      <!-- 会话列表 -->
      <div class="session-list">
        <div class="session-group-title">最近会话</div>

        <TransitionGroup name="list">
          <div
            v-for="session in chatStore.filteredSessions"
            :key="session.id"
            class="session-item"
            :class="{ active: session.id === chatStore.activeSessionId }"
            @click="handleSwitchSession(session.id)"
          >
            <span class="session-icon">💬</span>
            <span class="session-title">{{ session.title }}</span>
            <span class="session-count" v-if="session.messages.length">
              {{ session.messages.length }}
            </span>
            <button
              class="session-delete"
              @click.stop="handleDeleteSession(session.id)"
              title="删除对话"
            >
              🗑
            </button>
          </div>
        </TransitionGroup>

        <div v-if="chatStore.filteredSessions.length === 0" class="no-sessions">
          <span>📭</span>
          <p>暂无会话记录</p>
        </div>
      </div>

      <!-- 底部导航 -->
      <div class="sidebar-footer">
        <router-link to="/" class="nav-link" :class="{ active: $route.name === 'Chat' }">
          💬 智能问答
        </router-link>
        <router-link to="/profile" class="nav-link" :class="{ active: $route.name === 'Profile' }">
          👤 个人信息
        </router-link>
        <router-link
          to="/change-password"
          class="nav-link"
          :class="{ active: $route.name === 'ChangePassword' }"
        >
          🔑 修改密码
        </router-link>
        <button class="nav-link logout-btn" @click="handleLogout">
          🚪 退出登录
        </button>

        <div class="user-badge">
          <div class="user-id">👤 {{ maskedId }}</div>
          <div class="user-plan">Free Plan</div>
        </div>
      </div>
    </aside>

    <!-- 移动端遮罩 -->
    <Transition name="fade">
      <div
        v-if="!sidebarCollapsed && isMobile"
        class="sidebar-overlay"
        @click="sidebarCollapsed = true"
      />
    </Transition>

    <!-- ==================== 主内容区 ==================== -->
    <main class="main-area">
      <!-- 移动端顶栏 -->
      <div v-if="isMobile" class="mobile-header">
        <button class="menu-btn" @click="sidebarCollapsed = false">☰</button>
        <span class="mobile-title">🎓 校园智助</span>
        <span class="mobile-spacer"></span>
      </div>

      <router-view />
    </main>
  </div>
</template>

/**
 * 主布局组件
 *
 * 功能介绍：
 * · 提供学生端应用的左侧边栏 + 主内容区双栏布局
 * · 侧边栏包含：Logo、新建对话按钮、会话搜索框、会话列表、底部导航
 * · 支持会话切换、删除、新建操作
 * · 底部导航提供智能问答、个人信息、修改密码、退出登录入口
 * · 展示当前用户脱敏学号与套餐信息
 * · 响应式适配：桌面端固定侧边栏，移动端侧边栏可滑动收起并带遮罩层
 * · 窗口大小变化时自动调整侧边栏展开/收起状态
 */
<script setup>
import { ref, computed, onMounted, onUnmounted } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import { useAuthStore } from '@/stores/auth'
import { useChatStore } from '@/stores/chat'
import { maskStudentId } from '@/utils/format'

const router = useRouter()
const route = useRoute()
const authStore = useAuthStore()
const chatStore = useChatStore()

const windowWidth = ref(window.innerWidth)
/** 是否为移动端（窗口宽度 < 768px） */
const isMobile = computed(() => windowWidth.value < 768)
/** 侧边栏收起状态（移动端默认收起） */
const sidebarCollapsed = ref(window.innerWidth < 768)

/** 当前登录学生的脱敏学号 */
const maskedId = computed(() => maskStudentId(authStore.studentId))

/**
 * 处理窗口大小变化
 * 桌面端（>=768px）自动展开侧边栏
 */
function handleResize() {
  windowWidth.value = window.innerWidth
  if (windowWidth.value >= 768) {
    sidebarCollapsed.value = false
  }
}

onMounted(() => window.addEventListener('resize', handleResize))
onUnmounted(() => window.removeEventListener('resize', handleResize))

/**
 * 新建对话
 * 创建新会话后跳转至 Chat 页面，移动端自动收起侧边栏
 */
function handleNewChat() {
  chatStore.createSession()
  if (route.name !== 'Chat') {
    router.push({ name: 'Chat' })
  }
  if (isMobile.value) sidebarCollapsed.value = true
}

/**
 * 切换到指定会话
 * 跳转至 Chat 页面并激活对应会话，移动端自动收起侧边栏
 * @param {string} sessionId 会话 ID
 */
function handleSwitchSession(sessionId) {
  chatStore.switchSession(sessionId)
  if (route.name !== 'Chat') {
    router.push({ name: 'Chat' })
  }
  if (isMobile.value) sidebarCollapsed.value = true
}

/**
 * 删除指定会话
 * 弹出确认对话框后调用 chatStore.deleteSession
 * @param {string} sessionId 会话 ID
 */
function handleDeleteSession(sessionId) {
  if (confirm('确定要删除此对话吗？删除后无法恢复。')) {
    chatStore.deleteSession(sessionId)
  }
}

/**
 * 处理退出登录
 * 确认后执行 authStore.logout、chatStore.clearAllSessions，并跳转至 Login 页
 */
function handleLogout() {
  if (confirm('确定要退出登录吗？')) {
    authStore.logout()
    chatStore.clearAllSessions()
    router.push({ name: 'Login' })
  }
}
</script>

<style scoped>
.layout {
  display: flex;
  height: 100vh; /* Fallback for browsers that do not support dvh */
  height: 100dvh;
  width: 100%;
}

/* ==================== 侧边栏 ==================== */
.sidebar {
  width: 280px;
  min-width: 280px;
  background: var(--bg-card);
  border-right: 1px solid var(--border);
  display: flex;
  flex-direction: column;
  padding: 20px 14px;
  gap: 12px;
  transition: transform 0.3s ease;
  z-index: 100;
  overflow: hidden;
}

.sidebar-top {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding-bottom: 4px;
}
.logo {
  font-size: 20px;
  font-weight: 700;
  color: var(--primary);
  white-space: nowrap;
}
.collapse-btn {
  display: none;
  background: none;
  font-size: 20px;
  color: var(--text-muted);
  padding: 4px 8px;
  border-radius: 4px;
}
.collapse-btn:hover {
  background: var(--primary-light);
}

/* 新建对话按钮 */
.new-chat-btn {
  background: var(--accent);
  color: white;
  padding: 11px 16px;
  border-radius: var(--radius-sm);
  font-weight: 600;
  font-size: 14px;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 8px;
  transition: var(--transition);
}
.new-chat-btn:hover {
  background: #e56c00;
  box-shadow: var(--shadow-sm);
}
.btn-icon {
  font-size: 18px;
  font-weight: 700;
}

/* 搜索框 */
.search-box {
  position: relative;
  display: flex;
  align-items: center;
}
.search-icon {
  position: absolute;
  left: 10px;
  font-size: 13px;
  pointer-events: none;
}
.search-box input {
  width: 100%;
  padding: 9px 30px 9px 32px;
  border: 1px solid var(--border);
  border-radius: var(--radius-sm);
  background: #f5f8fc;
  font-size: 13px;
  transition: var(--transition);
}
.search-box input:focus {
  border-color: var(--primary);
  background: white;
}
.search-clear {
  position: absolute;
  right: 8px;
  background: none;
  font-size: 12px;
  color: var(--text-light);
  padding: 2px 4px;
}

/* 会话列表 */
.session-list {
  flex: 1;
  overflow-y: auto;
  display: flex;
  flex-direction: column;
  gap: 2px;
  min-height: 0;
}
.session-group-title {
  font-size: 11px;
  color: var(--text-light);
  padding: 8px 8px 4px;
  text-transform: uppercase;
  letter-spacing: 1px;
  font-weight: 600;
}
.session-item {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 9px 10px;
  border-radius: var(--radius-sm);
  cursor: pointer;
  transition: var(--transition);
  font-size: 13px;
  color: var(--text-secondary);
  position: relative;
}
.session-item:hover {
  background: var(--primary-light);
}
.session-item.active {
  background: var(--primary-light);
  color: var(--primary);
  font-weight: 600;
}
.session-icon {
  font-size: 14px;
  flex-shrink: 0;
}
.session-title {
  flex: 1;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.session-count {
  font-size: 10px;
  background: var(--border);
  color: var(--text-muted);
  padding: 1px 6px;
  border-radius: 10px;
  flex-shrink: 0;
}
.session-delete {
  background: none;
  font-size: 13px;
  opacity: 0;
  transition: var(--transition);
  padding: 2px 4px;
  border-radius: 4px;
  flex-shrink: 0;
}
.session-item:hover .session-delete {
  opacity: 0.5;
}
.session-delete:hover {
  opacity: 1 !important;
  background: var(--danger-light);
}

.no-sessions {
  text-align: center;
  color: var(--text-light);
  font-size: 13px;
  padding: 32px 0;
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 6px;
}
.no-sessions span {
  font-size: 28px;
}

/* 底部导航 */
.sidebar-footer {
  border-top: 1px solid var(--border-light);
  padding-top: 12px;
  display: flex;
  flex-direction: column;
  gap: 2px;
}
.nav-link {
  display: block;
  padding: 9px 12px;
  border-radius: var(--radius-sm);
  font-size: 13px;
  color: var(--text-secondary);
  transition: var(--transition);
  text-align: left;
  background: none;
  width: 100%;
}
.nav-link:hover,
.nav-link.active {
  background: var(--primary-light);
  color: var(--primary);
}
.logout-btn:hover {
  background: var(--danger-light) !important;
  color: var(--danger) !important;
}
.user-badge {
  margin-top: 8px;
  padding: 10px 12px;
  background: #f5f8fc;
  border-radius: var(--radius-sm);
}
.user-id {
  font-weight: 600;
  font-size: 13px;
  color: var(--text-primary);
}
.user-plan {
  font-size: 11px;
  color: var(--text-light);
  margin-top: 2px;
}

/* ==================== 主区域 ==================== */
.main-area {
  flex: 1;
  display: flex;
  flex-direction: column;
  overflow: hidden;
  min-width: 0;
}

/* 移动端顶栏 */
.mobile-header {
  display: flex;
  align-items: center;
  padding: 12px 16px;
  background: white;
  border-bottom: 1px solid var(--border);
  gap: 12px;
}
.menu-btn {
  background: none;
  font-size: 22px;
  color: var(--text-primary);
  padding: 2px 6px;
  border-radius: 4px;
}
.menu-btn:hover {
  background: var(--primary-light);
}
.mobile-title {
  font-weight: 600;
  font-size: 16px;
  color: var(--primary);
}
.mobile-spacer {
  flex: 1;
}

/* 遮罩层 */
.sidebar-overlay {
  position: fixed;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  background: rgba(0, 0, 0, 0.35);
  z-index: 99;
}

/* 列表动画 */
.list-enter-active,
.list-leave-active {
  transition: all 0.3s ease;
}
.list-enter-from,
.list-leave-to {
  opacity: 0;
  transform: translateX(-16px);
}

/* ==================== 响应式 ==================== */
@media (max-width: 768px) {
  .sidebar {
    position: fixed;
    top: 0;
    left: 0;
    height: 100vh;
    box-shadow: var(--shadow-lg);
  }
  .sidebar.collapsed {
    transform: translateX(-100%);
  }
  .collapse-btn {
    display: block;
  }
}
</style>