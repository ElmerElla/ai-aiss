/**
 * 系统接口
 * 对应后端: GET /api/v1/health
 *           GET /api/v1/version
 */
import http from './http'

export const systemApi = {
  /** 健康检查 */
  healthCheck() {
    return http.get('/health')
  },

  /** 版本信息 */
  getVersion() {
    return http.get('/version')
  }
}