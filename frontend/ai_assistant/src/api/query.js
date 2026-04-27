/**
 * 智能问答 API 模块
 *
 * 功能介绍：
 * -----------
 * 本模块封装了智能问答核心接口，支持多模态输入和流式输出。
 *
 * 接口列表：
 * - POST /query          → 普通问答请求（返回 JSON）
 * - DELETE /sessions     → 清除所有会话缓存
 * - askStream()          → 流式问答（SSE 实时输出）
 *
 * askStream 实现细节：
 * - 使用原生 fetch API 代替 Axios，以支持 ReadableStream
 * - 自动解析 SSE 数据包，逐块回调 onMessage
 * - 兼容 application/json 回退（某些网关可能改写响应格式）
 */
import http from './http'

export const queryApi = {
  /**
   * 发送问题（支持文本/图片/语音多模态）
   */
  ask(params) {
    return http.post('/query', params)
  },

  /**
   * 清除用户的所有 Redis 会话缓存与历史
   */
  clearSessions() {
    return http.delete('/sessions')
  },

  /**
   * 发送问题（支持文本/图片/语音多模态）- 支持流式输出 SSE
   * @param {Object} params 
   * @param {Function} onMessage 接收每次的流数据(包含chunk, done等)
   * @param {Function} onError 接收错误
   */
  async askStream(params, onMessage, onError) {
    try {
      const token = localStorage.getItem('campus_ai_token')
      const headers = { 'Content-Type': 'application/json' }
      if (token) headers['Authorization'] = `Bearer ${token}`

      const response = await fetch('/api/v1/query', {
        method: 'POST',
        headers,
        body: JSON.stringify(params)
      })

      if (!response.ok) {
        let msg = '请求失败'
        try {
          const errData = await response.json()
          msg = errData.detail || msg
        } catch (e) {
          msg = `HTTP ${response.status}: ${response.statusText}`
        }
        throw new Error(msg)
      }

      const contentType = (response.headers.get('content-type') || '').toLowerCase()

      // 兼容线上仍返回 JSON 的场景，避免前端一直处于“正在思考”状态。
      if (contentType.includes('application/json')) {
        const data = await response.json()
        if (data?.answer) {
          onMessage?.({ chunk: data.answer, done: false })
        }
        onMessage?.({
          chunk: '',
          response_time_ms: data?.response_time_ms,
          cached: !!data?.cached,
          done: true
        })
        return
      }

      if (!response.body) {
        throw new Error('响应体为空，无法解析流式输出')
      }

      const reader = response.body.getReader()
      const decoder = new TextDecoder('utf-8')
      let buffer = ''
      let gotDone = false

      const tryParseLine = (line) => {
        const trimmed = line.trim()
        if (!trimmed) return

        // 标准 SSE: data: {...}
        let payload = null
        if (trimmed.startsWith('data:')) {
          payload = trimmed.substring(5).trim()
        } else if (trimmed.startsWith('{') && trimmed.endsWith('}')) {
          // 容错：某些网关可能改写了流格式
          payload = trimmed
        }

        if (!payload || payload === '[DONE]') return

        let data = null
        try {
          data = JSON.parse(payload)
        } catch (err) {
          console.error('Failed to parse stream piece:', payload, err)
          return
        }

        if (data?.error) {
          const streamErr = new Error(String(data.error))
          streamErr.name = 'StreamServerError'
          throw streamErr
        }

        if (data?.done) gotDone = true
        onMessage?.(data)
      }

      while (true) {
        const { done, value } = await reader.read()
        if (value) {
          buffer += decoder.decode(value, { stream: true })
          const lines = buffer.split('\n')
          buffer = lines.pop() || ''
          for (const line of lines) {
            tryParseLine(line)
          }
        }

        if (done) {
          // flush decoder tail + leftover buffer，避免最后一个包无换行时丢失
          buffer += decoder.decode()
          if (buffer.trim()) {
            tryParseLine(buffer)
          }
          break
        }
      }

      // 兜底：如果服务端或网关没发送 done 包，也要结束前端状态
      if (!gotDone) {
        onMessage?.({ chunk: '', done: true, cached: false })
      }
    } catch (err) {
      if (onError) onError(err)
      else throw err
    }
  }
}