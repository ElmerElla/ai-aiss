/**
 * AES-CBC 加密工具
 *
 * 加密格式与后端一致: iv_base64:ciphertext_base64
 * 使用 URL-Safe Base64 编码
 */
import CryptoJS from 'crypto-js'

const AES_KEY = import.meta.env.VITE_AES_SECRET_KEY || 'your_aes_key_16!'

/**
 * WordArray → URL-Safe Base64 字符串
 */
function toUrlSafeBase64(wordArray) {
  return CryptoJS.enc.Base64.stringify(wordArray)
    .replace(/\+/g, '-')
    .replace(/\//g, '_')
    .replace(/=+$/, '')
}

/**
 * 使用 AES-CBC 加密明文
 * @param {string} plainText 明文密码
 * @returns {string} 格式: iv_base64:ciphertext_base64
 */
export function encryptPassword(plainText) {
  const key = CryptoJS.enc.Utf8.parse(AES_KEY)
  const iv = CryptoJS.lib.WordArray.random(16)

  const encrypted = CryptoJS.AES.encrypt(plainText, key, {
    iv,
    mode: CryptoJS.mode.CBC,
    padding: CryptoJS.pad.Pkcs7
  })

  const ivBase64 = toUrlSafeBase64(iv)
  const ciphertextBase64 = toUrlSafeBase64(encrypted.ciphertext)

  return `${ivBase64}:${ciphertextBase64}`
}