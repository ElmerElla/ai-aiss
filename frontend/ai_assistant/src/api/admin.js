/**
 * 管理员 API
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
