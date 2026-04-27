/**
 * 学生认证 API 模块
 *
 * 功能介绍：
 * -----------
 * 本模块封装了学生认证相关的后端接口调用。
 *
 * 接口列表：
 * - POST /auth/login          → 学生登录
 * - POST /auth/change-password → 修改密码
 *
 * 密码传输安全：
 * 前端通过 AES-CBC 加密密码后传输，格式为 iv_base64:ciphertext_base64
 */
import http from './http'

export const authApi = {
  /**
   * 学生登录
   * @param {string} student_id        学号
   * @param {string} encrypted_password AES-CBC 加密后的密码（iv_base64:ciphertext_base64）
   * @returns {Promise<{access_token, token_type, expires_in, student_id}>}
   */
  login(student_id, encrypted_password) {
    return http.post('/auth/login', {
      student_id,
      encrypted_password
    })
  },

  /**
   * 修改密码
   * @param {string} student_id
   * @param {string} encrypted_old_password AES-CBC 加密
   * @param {string} encrypted_new_password AES-CBC 加密
   * @returns {Promise<{success, student_id, detail}>}
   */
  changePassword(student_id, encrypted_old_password, encrypted_new_password) {
    return http.post('/auth/change-password', {
      student_id,
      encrypted_old_password,
      encrypted_new_password
    })
  }
}