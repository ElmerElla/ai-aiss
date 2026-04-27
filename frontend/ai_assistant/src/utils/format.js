/**
 * 格式化工具函数模块
 *
 * 功能介绍：
 * · formatTime：将时间戳格式化为友好文本（刚刚 / N 分钟前 / N 小时前 / N 天前 / 具体日期）
 * · formatResponseTime：将毫秒数格式化为响应时间字符串（ms / s）
 * · truncate：按指定长度截断字符串并追加省略号
 * · maskStudentId：隐藏学号中间部分，保护隐私
 * · formatDate：将日期格式化为 YYYY-MM-DD 字符串
 */

/**
 * 将时间戳格式化为友好文本
 * @param {string|Date} date
 * @returns {string}
 */
export function formatTime(date) {
  const d = new Date(date)
  const now = new Date()
  const diffMs = now - d
  const diffMins = Math.floor(diffMs / 60000)
  const diffHours = Math.floor(diffMs / 3600000)
  const diffDays = Math.floor(diffMs / 86400000)

  if (diffMins < 1) return '刚刚'
  if (diffMins < 60) return `${diffMins} 分钟前`
  if (diffHours < 24) return `${diffHours} 小时前`
  if (diffDays < 7) return `${diffDays} 天前`

  const pad = (n) => String(n).padStart(2, '0')
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())} ${pad(d.getHours())}:${pad(d.getMinutes())}`
}

/**
 * 格式化响应时间（毫秒）
 * @param {number} ms
 * @returns {string}
 */
export function formatResponseTime(ms) {
  if (ms < 1000) return `${ms}ms`
  return `${(ms / 1000).toFixed(1)}s`
}

/**
 * 截断字符串
 * @param {string} str
 * @param {number} maxLen
 * @returns {string}
 */
export function truncate(str, maxLen = 30) {
  if (!str) return ''
  return str.length > maxLen ? str.substring(0, maxLen) + '...' : str
}

/**
 * 隐藏学号中间部分
 * @param {string} id
 * @returns {string}
 */
export function maskStudentId(id) {
  if (!id || id.length < 5) return id || ''
  return id.substring(0, 3) + '****' + id.substring(id.length - 2)
}

/**
 * 格式化日期为 YYYY-MM-DD
 * @param {string|Date} date
 * @returns {string}
 */
export function formatDate(date) {
  const d = new Date(date)
  const pad = (n) => String(n).padStart(2, '0')
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`
}