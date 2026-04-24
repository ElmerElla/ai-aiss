/**
 * 聊天状态管理
 *
 * · 会话 CRUD（创建 / 切换 / 删除 / 清空）
 * · 消息发送（自动附加 session_id）
 * · 消息删除
 * · 搜索过滤
 * · localStorage 持久化
 */
import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import { queryApi } from '@/api/query'
import {
  generateSessionId,
  getDeviceId,
  getAllSessions,
  saveSessions,
  getActiveSessionId,
  setActiveSessionId
} from '@/utils/session'

export const useChatStore = defineStore('chat', () => {
  // ===================== 状态 =====================
  const sessions = ref(getAllSessions())
  const activeSessionId = ref(getActiveSessionId())
  const loadingStates = ref({}) // 记录每个 session 的加载状态
  const searchKeyword = ref('')

  // ===================== 计算属性 =====================

  /** 判断当前会话是否正在加载 */
  const loading = computed(() => {
    if (!activeSessionId.value) return false
    return !!loadingStates.value[activeSessionId.value]
  })

  /** 当前激活的会话对象 */
  const currentSession = computed(() => {
    return sessions.value.find((s) => s.id === activeSessionId.value) || null
  })

  /** 当前会话的消息列表 */
  const currentMessages = computed(() => {
    return currentSession.value?.messages || []
  })

  /** 按关键词过滤后的会话列表 */
  const filteredSessions = computed(() => {
    const kw = searchKeyword.value.trim().toLowerCase()
    if (!kw) return sessions.value
    return sessions.value.filter(
      (s) =>
        s.title.toLowerCase().includes(kw) ||
        s.messages.some((m) => m.content?.toLowerCase().includes(kw))
    )
  })

  // ===================== 操作 =====================

  /** 持久化到 localStorage */
  function persist() {
    saveSessions(sessions.value)
  }

  /** 新建对话 */
  function createSession() {
    const id = generateSessionId()
    const session = {
      id,
      title: '新对话',
      createdAt: new Date().toISOString(),
      updatedAt: new Date().toISOString(),
      messages: []
    }
    sessions.value.unshift(session)
    activeSessionId.value = id
    setActiveSessionId(id)
    persist()
    return session
  }

  /** 切换对话 */
  function switchSession(sessionId) {
    activeSessionId.value = sessionId
    setActiveSessionId(sessionId)
  }

  /** 删除指定对话 */
  function deleteSession(sessionId) {
    const idx = sessions.value.findIndex((s) => s.id === sessionId)
    if (idx === -1) return
    sessions.value.splice(idx, 1)

    // 如果删除的是当前激活的对话，自动切换
    if (activeSessionId.value === sessionId) {
      const nextId = sessions.value.length > 0 ? sessions.value[0].id : null
      activeSessionId.value = nextId
      setActiveSessionId(nextId)
    }
    persist()
  }

  /** 清空所有对话 */
  async function clearAllSessions() {
    try {
      if (typeof queryApi.clearSessions === 'function') {
        await queryApi.clearSessions()
      }
    } catch (err) {
      console.warn("未能清除远端缓存:", err)
    }
    sessions.value = []
    activeSessionId.value = null
    setActiveSessionId(null)
    persist()
  }

  /** 删除单条消息 */
  function deleteMessage(messageId) {
    const session = sessions.value.find((s) => s.id === activeSessionId.value)
    if (!session) return
    const idx = session.messages.findIndex((m) => m.id === messageId)
    if (idx !== -1) {
      session.messages.splice(idx, 1)
      persist()
    }
  }

  /**
   * 发送消息（核心方法）
    * 自动管理 session_id，匹配后端 POST /api/v1/query 格式
   */
  async function sendMessage({ text, image_base64, audio_base64, audioDuration }) {
    // 确保有活跃会话
    if (!activeSessionId.value) {
      createSession()
    }

    const session = sessions.value.find((s) => s.id === activeSessionId.value)
    if (!session) return

    const did = getDeviceId()

    // ---- 1. 添加用户消息 ----
    const userMsg = {
      id: `msg_${Date.now()}_user`,
      role: 'user',
      content: text || '',
      image_base64: image_base64 || null,
      audio_base64: audio_base64 || null,
      audioDuration: audioDuration || null,
      isPlaying: false,
      timestamp: new Date().toISOString()
    }
    session.messages.push(userMsg)

    // 首条用户消息自动设为对话标题
    if (session.messages.filter((m) => m.role === 'user').length === 1 && (text || audio_base64)) {
      session.title = text ? (text.length > 20 ? text.substring(0, 20) + '...' : text) : '语音对话'
    }
    session.updatedAt = new Date().toISOString()
    persist()

    // ---- 2. 请求后端 ----
    loadingStates.value[session.id] = true
    
    // 预先创建一个助手消息占位，等待流式填入
    const assistantMsgRaw = {
      id: `msg_${Date.now()}_assistant`,
      role: 'assistant',
      content: '',
      cached: false,
      response_time_ms: null,
      did,
      timestamp: new Date().toISOString()
    }
    session.messages.push(assistantMsgRaw)
    
    // 获取响应式的代理对象，以便内容更新能触发前端流式渲染
    const assistantMsg = session.messages[session.messages.length - 1]

    try {
      const requestBody = { session_id: session.id }
      if (text) requestBody.text = text
      if (image_base64) requestBody.image_base64 = image_base64
      if (audio_base64) requestBody.audio_base64 = audio_base64

      return await new Promise((resolve, reject) => {
        let isFirstToken = true;

        queryApi.askStream(requestBody, (data) => {
          if (data.done) {
            assistantMsg.response_time_ms = data.response_time_ms
            assistantMsg.cached = data.cached
            if (data.answer) assistantMsg.content = data.answer // just in case it's a full return
            session.updatedAt = new Date().toISOString()
            persist()
            loadingStates.value[session.id] = false
            resolve(data)
          } else {
            if (isFirstToken) {
                isFirstToken = false;
            }
            assistantMsg.content += (data.chunk || '')
            session.updatedAt = new Date().toISOString()
            persist()
          }
        }, (err) => {
          loadingStates.value[session.id] = false
          
          assistantMsg.content = resolveErrorMessage(err)
          assistantMsg.isError = true
          persist()
          reject(err)
        })
      })

    } catch (error) {
      if (!assistantMsg.isError) {
        assistantMsg.content = resolveErrorMessage(error)
        assistantMsg.isError = true
        persist()
      }
      throw error
    } finally {
      loadingStates.value[session.id] = false
    }
  }

  /**
   * 根据后端状态码解析错误信息
   */
  function resolveErrorMessage(error) {
    const status = error.response?.status
    const detail = error.response?.data?.detail
    const message = error?.message
    
    // 如果是后端抛出的由于静音等原因无法识别导致的错误，做一点友好的封装
    if (detail && detail.includes('音频处理失败') && detail.includes('Task failed')) {
      return '❌ 未检测到清晰的语音内容，请大点声再试一次哦 🎤'
    }

    if (detail) return `❌ ${detail}`
    if (message) return `❌ ${message}`
    switch (status) {
      case 400:
        return '❌ 请求参数错误：文本、图片、语音至少需要提供一个'
      case 401:
        return '❌ 登录已过期，请重新登录'
      case 502:
        return '❌ AI 服务暂时不可用，或未正常识别到语音内容，请稍后再试'
      default:
        return '❌ 网络异常，请检查连接后重试'
    }
  }

  return {
    // 状态
    sessions,
    activeSessionId,
    loadingStates,
    searchKeyword,
    // 计算属性
    loading,
    currentSession,
    currentMessages,
    filteredSessions,
    // 操作
    createSession,
    switchSession,
    deleteSession,
    clearAllSessions,
    deleteMessage,
    sendMessage
  }
})