/**
 * 会话 & 设备标识管理工具
 *
 * · session_id: 每个对话一个，格式 sess_<uuid>
 * · did (设备ID): 首次生成后持久化，格式 did_<uuid>
 * · 会话列表通过 localStorage 持久化
 */
import { v4 as uuidv4 } from 'uuid'

const SESSION_STORAGE_KEY = 'campus_ai_sessions'
const ACTIVE_SESSION_KEY = 'campus_ai_active_session'
const DEVICE_ID_KEY = 'campus_ai_did'

/**
 * 生成新的 session_id
 */
export function generateSessionId() {
  return `sess_${uuidv4().replace(/-/g, '')}`
}

/**
 * 获取设备 ID（首次自动生成并持久化）
 */
export function getDeviceId() {
  let did = localStorage.getItem(DEVICE_ID_KEY)
  if (!did) {
    did = `did_${uuidv4().replace(/-/g, '')}`
    localStorage.setItem(DEVICE_ID_KEY, did)
  }
  return did
}

/**
 * 获取所有会话列表
 * @returns {Array}
 */
export function getAllSessions() {
  try {
    const raw = localStorage.getItem(SESSION_STORAGE_KEY)
    return raw ? JSON.parse(raw) : []
  } catch {
    return []
  }
}

/**
 * 持久化会话列表
 * @param {Array} sessions
 */
export function saveSessions(sessions) {
  localStorage.setItem(SESSION_STORAGE_KEY, JSON.stringify(sessions))
}

/**
 * 获取当前活跃会话 ID
 */
export function getActiveSessionId() {
  return localStorage.getItem(ACTIVE_SESSION_KEY) || null
}

/**
 * 设置当前活跃会话 ID
 */
export function setActiveSessionId(sessionId) {
  if (sessionId) {
    localStorage.setItem(ACTIVE_SESSION_KEY, sessionId)
  } else {
    localStorage.removeItem(ACTIVE_SESSION_KEY)
  }
}