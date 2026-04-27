/**
 * 管理员 API 模块
 *
 * 功能介绍：
 * -----------
 * 本模块封装了管理员后台的所有后端接口调用。
 *
 * 接口列表：
 * - POST /admin/auth/login               → 管理员登录
 * - GET  /admin/auth/me                  → 获取当前管理员信息
 * - GET  /admin/dashboard/summary        → 管理面板统计
 * - GET  /admin/meta/terms               → 学期列表
 * - GET  /admin/meta/classes             → 班级列表
 * - GET  /admin/schedules                → 课表查询（支持分页和筛选）
 * - PATCH /admin/schedules/{id}/status   → 更新课表状态
 */
import adminHttp from './adminHttp'

export const adminApi = {
  login(username, encrypted_password) {
    return adminHttp.post('/admin/auth/login', {
      username,
      encrypted_password
    })
  },

  me() {
    return adminHttp.get('/admin/auth/me')
  },

  getSummary() {
    return adminHttp.get('/admin/dashboard/summary')
  },

  getTerms() {
    return adminHttp.get('/admin/meta/terms')
  },

  getClasses() {
    return adminHttp.get('/admin/meta/classes')
  },

  getSchedules(params = {}) {
    return adminHttp.get('/admin/schedules', { params })
  },

  updateScheduleStatus(scheduleId, schedule_status, reason = '') {
    return adminHttp.patch(`/admin/schedules/${scheduleId}/status`, {
      schedule_status,
      reason
    })
  }
}
