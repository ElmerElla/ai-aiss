/**
 * 系统 API 模块
 *
 * 功能介绍：
 * -----------
 * 本模块封装了系统级别的公共接口调用，无需认证。
 *
 * 接口列表：
 * - GET /health  → 服务健康检查
 * - GET /version → 获取应用版本信息
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