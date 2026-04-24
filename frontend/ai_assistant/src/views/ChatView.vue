<template>
  <div class="chat-view">
    <!-- ==================== 欢迎界面（无消息时） ==================== -->
    <div
      v-if="!chatStore.currentSession || chatStore.currentMessages.length === 0"
      class="welcome-screen"
    >
      <div class="welcome-content">
        <div class="welcome-header">
          <h1>你好！我是校园智助 🎓</h1>
          <p>告诉我你要完成的任务，让我来帮你搞定</p>
        </div>

        <div class="prompt-examples">
          <div class="examples-title">💡 你可以试着问我：</div>
          <div class="example-list">
            <button
              v-for="(example, idx) in examples"
              :key="idx"
              class="example-item"
              @click="fillInput(example.text)"
            >
              <span class="example-icon">{{ example.icon }}</span>
              <span class="example-text">{{ example.text }}</span>
              <span class="example-arrow">→</span>
            </button>
          </div>
        </div>

        <div class="quick-actions">
          <button
            v-for="action in quickActions"
            :key="action.label"
            class="action-btn"
            @click="fillInput(action.prompt)"
          >
            <span>{{ action.icon }}</span>
            {{ action.label }}
          </button>
        </div>
      </div>
    </div>

    <!-- ==================== 消息列表 ==================== -->
    <div v-else class="messages-area" ref="messagesContainer">
      <div class="messages-inner">
        <!-- 会话信息顶栏 -->
        <div class="session-info-bar">
          <span class="session-badge">
            📝 {{ chatStore.currentSession.title }}
          </span>
          <span class="session-meta">
            {{ chatStore.currentMessages.length }} 条消息 ·
            Session: {{ chatStore.currentSession.id.substring(0, 16) }}...
          </span>
        </div>

        <TransitionGroup name="msg" :key="chatStore.activeSessionId">
          <div
            v-for="msg in chatStore.currentMessages"
            :key="msg.id"
            class="message-row"
            :class="msg.role"
          >
            <!-- 头像 -->
            <div class="message-avatar">
              {{ msg.role === 'user' ? '👤' : '🎓' }}
            </div>

            <!-- 消息主体 -->
            <div class="message-body">
              <!-- 如果用户发了图片，展示缩略图 -->
              <div v-if="msg.image_base64 && msg.role === 'user'" class="msg-image">
                <img :src="'data:image/png;base64,' + msg.image_base64" alt="用户图片" />
              </div>

              <!-- 如果用户发了语音，展示语音气泡 -->
              <div
                v-if="msg.audio_base64 && msg.role === 'user'"
                class="msg-audio"
                @click="playAudio(msg)"
              >
                <div class="audio-bubble">
                  <span class="audio-icon" :class="{ 'playing': msg.isPlaying }">
                    <svg viewBox="0 0 24 24" width="20" height="20" stroke="currentColor" stroke-width="2" fill="none" stroke-linecap="round" stroke-linejoin="round">
                      <path d="M11 5L6 9H2v6h4l5 4z"></path>
                      <path class="wave wave-1" d="M15.54 8.46a5 5 0 0 1 0 7.07"></path>
                      <path class="wave wave-2" d="M19.07 4.93a10 10 0 0 1 0 14.14"></path>
                    </svg>
                  </span>
                  <span class="audio-duration">{{ msg.audioDuration ? msg.audioDuration + '"' : '语音' }}</span>
                </div>
              </div>

              <!-- 消息文本 -->
              <div
                v-if="msg.content || (msg.role === 'assistant' && chatStore.loading && msg.id === chatStore.currentMessages[chatStore.currentMessages.length-1].id)"
                class="message-content"
                :class="{ error: msg.isError, typing: !msg.content }"
              >
                <template v-if="msg.content">
                  <div v-html="renderContent(msg.content)"></div>
                </template>
                <template v-else>
                  <span class="dot"></span>
                  <span class="dot"></span>
                  <span class="dot"></span>
                  <span class="typing-text">正在思考...</span>
                </template>
              </div>

              <!-- 消息元信息 -->
              <div class="message-meta">
                <span class="meta-time">{{ formatTime(msg.timestamp) }}</span>

                <template v-if="msg.role === 'assistant' && !msg.isError">
                  <span class="meta-badge cached" v-if="msg.cached">
                    ⚡ 缓存
                  </span>
                  <span class="meta-badge response-time" v-if="msg.response_time_ms">
                    ⏱ {{ formatResponseTime(msg.response_time_ms) }}
                  </span>
                  <span class="meta-badge did" v-if="msg.did">
                    📱 {{ msg.did.substring(0, 12) }}...
                  </span>
                </template>

                <button
                  class="msg-delete-btn"
                  @click="chatStore.deleteMessage(msg.id)"
                  title="删除此消息"
                >
                  🗑
                </button>
              </div>
            </div>
          </div>
        </TransitionGroup>

        <!-- 底部锚点 -->
        <div ref="bottomAnchor"></div>
      </div>
    </div>

    <!-- ==================== 输入区域 ==================== -->
    <div class="input-area">
      <div class="input-container">
        <!-- 图片预览 -->
        <Transition name="fade">
          <div v-if="imagePreview" class="attachment-preview">
            <img :src="imagePreview" alt="附件预览" />
            <button class="remove-attachment" @click="clearImage" title="移除图片">✕</button>
          </div>
        </Transition>

        <!-- 输入行 -->
        <div class="input-row">
          <div class="input-actions">
            <!-- 语音录制按钮 -->
            <button
              class="action-icon voice-btn"
              :class="{ 'recording': isRecording }"
              @mousedown="startRecording"
              @mouseup="stopRecording"
              @mouseleave="cancelRecording"
              @touchstart.prevent="startRecording"
              @touchend.prevent="stopRecording"
              @touchcancel.prevent="cancelRecording"
              :title="isRecording ? '松开发送' : '按住说话'"
            >
              🎙️
            </button>

            <label class="action-icon" title="上传图片">
              📎
              <input
                type="file"
                accept="image/png,image/jpeg,image/gif,image/webp"
                @change="handleImageUpload"
                ref="fileInput"
                hidden
              />
            </label>
          </div>

          <textarea
            ref="textareaRef"
            v-model="inputText"
            :placeholder="isRecording ? '🎙️ 正在录音，松开发送，移开取消...' : (chatStore.loading ? '正在思考中...' : '在此输入你的问题...')"
            :disabled="chatStore.loading || isRecording"
            @keydown.enter.exact.prevent="handleSend"
            @input="autoResize"
            rows="1"
          />

          <button
            class="send-btn"
            :disabled="(!inputText.trim() && !imageBase64) || chatStore.loading || isRecording"
            @click="handleSend"
            title="发送"
          >
            <span v-if="chatStore.loading" class="spinner-sm"></span>
            <span v-else>📤</span>
          </button>
        </div>

        <!-- 底部提示 -->
        <div class="input-hint">
          <span>Enter 发送 · 支持文本和图片多模态输入</span>
          <span v-if="chatStore.currentSession" class="hint-session">
            Session: {{ chatStore.currentSession.id.substring(0, 16) }}...
          </span>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, nextTick, watch, onMounted } from 'vue'
import { useChatStore } from '@/stores/chat'
import { formatTime, formatResponseTime } from '@/utils/format'
import { marked } from 'marked'

const chatStore = useChatStore()

// ---- 响应式状态 ----
const inputText = ref('')
const imageBase64 = ref(null)
const imagePreview = ref(null)
const messagesContainer = ref(null)
const bottomAnchor = ref(null)
const textareaRef = ref(null)
const fileInput = ref(null)

// ---- 录音相关状态 ----
const isRecording = ref(false)
let mediaRecorder = null
let audioChunks = []
let recordStream = null

// ---- 示例问题 ----
const examples = [
  { icon: '📅', text: '帮我查一下明天下午的课表' },
  { icon: '📈', text: '查询我上学期的成绩' },
  { icon: '📧', text: '帮我查找计算机学院老师的联系方式' },
  { icon: '🎓', text: '我目前的已修总学分是多少？' }
]

// ---- 快捷操作 ----
const quickActions = [
  { icon: '📅', label: '我的课表', prompt: '查询本学期完整课表' },
  { icon: '📊', label: '我的成绩', prompt: '列出我所有的课程成绩' },
  { icon: '👨‍🏫', label: '教师通讯', prompt: '查询全校教师通讯录' },
  { icon: '👤', label: '个人学籍', prompt: '查询我的学籍和个人信息' }
]

// ---- Markdown 渲染 ----
marked.setOptions({
  breaks: true,
  gfm: true
})

function renderContent(content) {
  if (!content) return ''
  try {
    return marked.parse(content)
  } catch {
    return content.replace(/\n/g, '<br/>')
  }
}

// ---- textarea 自适应高度 ----
function autoResize() {
  const el = textareaRef.value
  if (!el) return
  el.style.height = 'auto'
  el.style.height = Math.min(el.scrollHeight, 160) + 'px'
}

// ---- 滚动到底部 ----
function scrollToBottom() {
  nextTick(() => {
    bottomAnchor.value?.scrollIntoView({ behavior: 'smooth' })
  })
}

// ---- 填充输入框 ----
function fillInput(text) {
  inputText.value = text
  nextTick(() => {
    autoResize()
    textareaRef.value?.focus()
  })
}

// ---- 发送消息 ----
async function handleSend() {
  const text = inputText.value.trim()
  if (!text && !imageBase64.value) return
  if (chatStore.loading) return

  const params = {}
  if (text) params.text = text
  if (imageBase64.value) params.image_base64 = imageBase64.value

  // 清空输入
  inputText.value = ''
  clearImage()
  nextTick(() => autoResize())
  scrollToBottom()

  try {
    await chatStore.sendMessage(params)
  } catch {
    // 错误已在 store 中处理并添加到消息列表
  }
  scrollToBottom()
}

// ---- 图片上传 ----
function handleImageUpload(e) {
  const file = e.target.files?.[0]
  if (!file) return

  // 限制 5MB
  if (file.size > 5 * 1024 * 1024) {
    alert('图片大小不能超过 5MB')
    e.target.value = ''
    return
  }

  const reader = new FileReader()
  reader.onload = (event) => {
    const rawDataUrl = event.target.result

    // 如果图片相对较小 (< 800KB)，直接使用，不压缩
    if (file.size < 800 * 1024) {
      imageBase64.value = rawDataUrl.split(',')[1]
      imagePreview.value = rawDataUrl
      return
    }

    // 否则在前端进行压缩，避免超过服务器网关/Nginx的上传限制（默认通常为1MB）
    const img = new Image()
    img.onload = () => {
      const canvas = document.createElement('canvas')
      const ctx = canvas.getContext('2d')
      
      // 限制最大自适应尺寸为 1024
      const MAX_SIZE = 1024
      let width = img.width
      let height = img.height

      if (width > height && width > MAX_SIZE) {
        height = Math.round((height * MAX_SIZE) / width)
        width = MAX_SIZE
      } else if (height > MAX_SIZE) {
        width = Math.round((width * MAX_SIZE) / height)
        height = MAX_SIZE
      }

      canvas.width = width
      canvas.height = height
      ctx.drawImage(img, 0, 0, width, height)

      // 输出为 jpeg 格式，质量设为 0.7 进一步压缩体积
      const compressedDataUrl = canvas.toDataURL('image/jpeg', 0.7)
      imageBase64.value = compressedDataUrl.split(',')[1]
      imagePreview.value = compressedDataUrl
    }
    img.src = rawDataUrl
  }
  reader.readAsDataURL(file)
  e.target.value = ''
}

function clearImage() {
  imageBase64.value = null
  imagePreview.value = null
}

// ---- 语音输入 ----
let recordingStartTime = 0

async function startRecording() {
  if (chatStore.loading) return
  try {
    recordStream = await navigator.mediaDevices.getUserMedia({ audio: true })
    mediaRecorder = new MediaRecorder(recordStream)
    audioChunks = []

    mediaRecorder.ondataavailable = (e) => {
      if (e.data.size > 0) {
        audioChunks.push(e.data)
      }
    }

    mediaRecorder.onstop = async () => {
      // 停止麦克风
      recordStream.getTracks().forEach(track => track.stop())
      recordStream = null

      if (!isRecording.value) return // 如果被手动取消，直接返回不发送

      const duration = Date.now() - recordingStartTime
      isRecording.value = false

      // 1. 前端判断：录音时间太短（小于1秒）
      if (duration < 1000) {
        alert('录音时间太短，请重试')
        return
      }

      const audioBlob = new Blob(audioChunks, { type: 'audio/webm' }) 
      
      // 2. 前端判断：没有声音数据或文件极小
      if (audioBlob.size < 500) {
        alert('未检测到声音或声音过小，请大声重试')
        return
      }

      const reader = new FileReader()
      reader.onload = async () => {
        const dataUrl = reader.result
        const base64Audio = dataUrl.split(',')[1]

        try {
          // 由于后端在完全静音时可能会抛出 502/报错，我们如果收到错误可以在 catch 里静默或提示
          await chatStore.sendMessage({ 
            audio_base64: base64Audio,
            audioDuration: Math.round(duration / 1000) 
          })
        } catch (err) {
          // 在 store 里其实已经把报错信息当作 assistant 消息推到了页面上（如“音频处理失败”），
          // 所以这里不需要额外 alert，保留在流中作为一个错误记录即可。
        }
        scrollToBottom()
      }
      reader.readAsDataURL(audioBlob)
    }

    recordingStartTime = Date.now()
    mediaRecorder.start()
    isRecording.value = true
  } catch (err) {
    console.error('麦克风权限错误:', err)
    alert('无法访问麦克风，请检查浏览器权限设置！')
  }
}

function stopRecording() {
  if (mediaRecorder && mediaRecorder.state === 'recording') {
    mediaRecorder.stop()
  } else {
    isRecording.value = false
  }
}

function cancelRecording() {
  if (isRecording.value) {
    isRecording.value = false // 将标志位置为 false，onstop 时判断该标志位则不会发送
    if (mediaRecorder && mediaRecorder.state === 'recording') {
      mediaRecorder.stop()
    }
  }
}

// ---- 播放语音 ----
let currentAudioPlayer = null

function playAudio(msg) {
  if (!msg.audio_base64) return

  // 如果已经在播放，点击则停止
  if (msg.isPlaying) {
    if (currentAudioPlayer) {
      currentAudioPlayer.pause()
    }
    msg.isPlaying = false
    return
  }

  // 停止之前正在播放的其他语音
  if (currentAudioPlayer) {
    const prevMsg = chatStore.currentMessages.find(m => m.isPlaying)
    if (prevMsg) prevMsg.isPlaying = false
    currentAudioPlayer.pause()
  }

  // 播放新的语音 (使用 webm 或直接用 base64 data URI)
  // 如果你在 Safari 可能对 webm 支持不佳，Chrome/Firefox 上是可以直接播的
  const audioSrc = 'data:audio/webm;base64,' + msg.audio_base64
  currentAudioPlayer = new window.Audio(audioSrc)
  
  msg.isPlaying = true

  currentAudioPlayer.onended = () => {
    msg.isPlaying = false
  }
  
  currentAudioPlayer.onerror = () => {
    msg.isPlaying = false
    alert('无法播放此语音格式')
  }

  currentAudioPlayer.play().catch(e => {
    console.error('播放失败', e)
    msg.isPlaying = false
  })
}

// ---- 监听消息变化自动滚底 ----
watch(
  () => chatStore.currentMessages.length,
  () => scrollToBottom()
)

onMounted(() => scrollToBottom())
</script>

<style scoped>
.chat-view {
  display: flex;
  flex-direction: column;
  flex: 1;
  height: 100%;
  overflow: hidden;
}

/* ==================== 欢迎界面 ==================== */
.welcome-screen {
  flex: 1;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 40px 20px;
  overflow-y: auto;
}
.welcome-content {
  max-width: 680px;
  width: 100%;
  text-align: center;
}
.welcome-header h1 {
  font-size: 32px;
  font-weight: 700;
  color: var(--primary);
  margin-bottom: 10px;
}
.welcome-header p {
  font-size: 17px;
  color: var(--text-secondary);
  margin-bottom: 36px;
}

/* 示例列表 */
.prompt-examples {
  background: white;
  border: 1px solid var(--border);
  border-radius: var(--radius-lg);
  padding: 24px;
  margin-bottom: 28px;
  text-align: left;
}
.examples-title {
  font-size: 14px;
  font-weight: 600;
  color: var(--text-secondary);
  margin-bottom: 14px;
}
.example-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
}
.example-item {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 12px 16px;
  background: #f8faff;
  border: 1px solid transparent;
  border-radius: var(--radius-sm);
  font-size: 14px;
  color: var(--text-secondary);
  transition: var(--transition);
  text-align: left;
}
.example-item:hover {
  background: var(--primary-light);
  border-color: var(--primary);
  color: var(--primary);
}
.example-icon {
  font-size: 20px;
  flex-shrink: 0;
}
.example-text {
  flex: 1;
}
.example-arrow {
  opacity: 0;
  transition: var(--transition);
  color: var(--primary);
}
.example-item:hover .example-arrow {
  opacity: 1;
}

/* 快捷操作 */
.quick-actions {
  display: flex;
  gap: 12px;
  justify-content: center;
  flex-wrap: wrap;
}
.action-btn {
  background: white;
  border: 1px solid var(--border);
  border-radius: var(--radius-md);
  padding: 12px 22px;
  font-size: 14px;
  color: var(--primary);
  font-weight: 600;
  display: flex;
  align-items: center;
  gap: 8px;
  transition: var(--transition);
}
.action-btn:hover {
  background: var(--primary-light);
  border-color: var(--primary);
  box-shadow: var(--shadow-sm);
}

/* ==================== 消息区域 ==================== */
.messages-area {
  flex: 1;
  overflow-y: auto;
  padding: 16px 0;
}
.messages-inner {
  max-width: 820px;
  margin: 0 auto;
  padding: 0 24px;
  display: flex;
  flex-direction: column;
  gap: 20px;
}

/* 会话信息条 */
.session-info-bar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 10px 16px;
  background: #f5f8fc;
  border-radius: var(--radius-sm);
  font-size: 12px;
  flex-wrap: wrap;
  gap: 8px;
}
.session-badge {
  font-weight: 600;
  color: var(--text-secondary);
}
.session-meta {
  color: var(--text-light);
  font-family: monospace;
  font-size: 11px;
}

/* 消息行 */
.message-row {
  display: flex;
  gap: 14px;
  animation: msgSlideIn 0.35s ease;
}
@keyframes msgSlideIn {
  from {
    opacity: 0;
    transform: translateY(10px);
  }
  to {
    opacity: 1;
    transform: translateY(0);
  }
}
.message-row.user {
  flex-direction: row-reverse;
}

/* 头像 */
.message-avatar {
  width: 40px;
  height: 40px;
  border-radius: 50%;
  background: var(--primary-light);
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 18px;
  flex-shrink: 0;
}
.message-row.user .message-avatar {
  background: var(--accent-light);
}

/* 消息主体 */
.message-body {
  max-width: 72%;
  min-width: 0;
}

/* 用户图片 */
.msg-image {
  margin-bottom: 8px;
}
.msg-image img {
  max-width: 240px;
  max-height: 180px;
  border-radius: var(--radius-sm);
  border: 1px solid var(--border);
}

/* 语音气泡 */
.msg-audio {
  margin-bottom: 8px;
  display: flex;
  justify-content: flex-end;
}
.audio-bubble {
  background: var(--primary);
  color: white;
  padding: 10px 16px;
  border-radius: var(--radius-lg);
  border-top-right-radius: 4px;
  display: inline-flex;
  align-items: center;
  gap: 12px;
  cursor: pointer;
  min-width: 80px;
  user-select: none;
  transition: opacity 0.2s;
}
.audio-bubble:active {
  opacity: 0.8;
}
.audio-duration {
  font-size: 14px;
  font-weight: 500;
}
/* 语音播放动画图标 */
.audio-icon {
  display: flex;
  align-items: center;
}
.audio-icon .wave {
  opacity: 0;
  transition: opacity 0.2s;
}
.audio-icon.playing .wave-1 {
  animation: audio-wave 1s infinite;
  animation-delay: 0.1s;
}
.audio-icon.playing .wave-2 {
  animation: audio-wave 1s infinite;
  animation-delay: 0.3s;
}
@keyframes audio-wave {
  0%, 100% { opacity: 0; }
  50% { opacity: 1; }
}

/* 消息气泡 */
.message-content {
  padding: 14px 18px;
  border-radius: var(--radius-lg);
  font-size: 14px;
  line-height: 1.75;
  word-break: break-word;
}
.message-row.assistant .message-content {
  background: white;
  border: 1px solid var(--border);
  border-top-left-radius: 4px;
}
.message-row.user .message-content {
  background: var(--primary);
  color: white;
  border-top-right-radius: 4px;
}
.message-content.error {
  background: var(--danger-light);
  border-color: #ffcdd2;
  color: var(--danger);
}

/* Markdown 内容样式 */
.message-content :deep(p) {
  margin: 4px 0;
}
.message-content :deep(p:first-child) {
  margin-top: 0;
}
.message-content :deep(p:last-child) {
  margin-bottom: 0;
}
.message-content :deep(ul),
.message-content :deep(ol) {
  padding-left: 20px;
  margin: 8px 0;
}
.message-content :deep(li) {
  margin: 3px 0;
}
.message-content :deep(code) {
  background: rgba(0, 0, 0, 0.06);
  padding: 2px 6px;
  border-radius: 4px;
  font-size: 13px;
  font-family: 'Menlo', 'Monaco', 'Consolas', monospace;
}
.message-content :deep(pre) {
  background: #1e1e2e;
  color: #cdd6f4;
  padding: 16px;
  border-radius: var(--radius-sm);
  overflow-x: auto;
  margin: 10px 0;
  font-size: 13px;
}
.message-content :deep(pre code) {
  background: none;
  padding: 0;
  color: inherit;
}
.message-content :deep(table) {
  border-collapse: collapse;
  width: 100%;
  margin: 10px 0;
  font-size: 13px;
}
.message-content :deep(th),
.message-content :deep(td) {
  border: 1px solid var(--border);
  padding: 8px 12px;
  text-align: left;
}
.message-content :deep(th) {
  background: #f5f8fc;
  font-weight: 600;
}
.message-content :deep(blockquote) {
  border-left: 3px solid var(--primary);
  padding-left: 12px;
  margin: 8px 0;
  color: var(--text-muted);
}
.message-content :deep(a) {
  color: var(--primary);
  text-decoration: underline;
}
.message-content :deep(strong) {
  font-weight: 600;
}
/* 用户消息中的 code 反色 */
.message-row.user .message-content :deep(code) {
  background: rgba(255, 255, 255, 0.2);
  color: white;
}

/* 消息元信息 */
.message-meta {
  display: flex;
  align-items: center;
  gap: 6px;
  margin-top: 6px;
  flex-wrap: wrap;
}
.message-row.user .message-meta {
  justify-content: flex-end;
}
.meta-time {
  font-size: 11px;
  color: var(--text-light);
}
.meta-badge {
  font-size: 10px;
  padding: 2px 8px;
  border-radius: 10px;
  font-weight: 500;
  white-space: nowrap;
}
.meta-badge.cached {
  background: var(--success-light);
  color: var(--success);
}
.meta-badge.response-time {
  background: #f5f5f5;
  color: var(--text-muted);
}
.meta-badge.did {
  background: var(--warning-light);
  color: #b27600;
  font-family: monospace;
  font-size: 9px;
}
.msg-delete-btn {
  background: none;
  font-size: 12px;
  opacity: 0;
  transition: var(--transition);
  padding: 2px 4px;
  border-radius: 4px;
}
.message-row:hover .msg-delete-btn {
  opacity: 0.4;
}
.msg-delete-btn:hover {
  opacity: 1 !important;
  background: var(--danger-light);
}

/* 输入指示器 */
.typing {
  display: flex;
  gap: 6px;
  align-items: center;
  padding: 16px 20px;
}
.dot {
  width: 8px;
  height: 8px;
  background: var(--primary);
  border-radius: 50%;
  animation: bounce 1.4s ease-in-out infinite;
  opacity: 0.4;
}
.dot:nth-child(2) {
  animation-delay: 0.2s;
}
.dot:nth-child(3) {
  animation-delay: 0.4s;
}
@keyframes bounce {
  0%,
  80%,
  100% {
    transform: scale(1);
    opacity: 0.4;
  }
  40% {
    transform: scale(1.3);
    opacity: 1;
  }
}
.typing-text {
  font-size: 12px;
  color: var(--text-light);
  margin-left: 6px;
}

/* 消息列表动画 */
.msg-enter-active {
  transition: all 0.35s ease;
}
.msg-enter-from {
  opacity: 0;
  transform: translateY(12px);
}

/* ==================== 输入区域 ==================== */
.input-area {
  background: white;
  border-top: 1px solid var(--border);
  padding: 16px 24px 20px;
}
.input-container {
  max-width: 820px;
  margin: 0 auto;
}

/* 附件预览 */
.attachment-preview {
  margin-bottom: 12px;
  position: relative;
  display: inline-block;
}
.attachment-preview img {
  max-height: 120px;
  max-width: 220px;
  border-radius: var(--radius-sm);
  border: 1px solid var(--border);
  box-shadow: var(--shadow-sm);
}
.remove-attachment {
  position: absolute;
  top: -8px;
  right: -8px;
  width: 24px;
  height: 24px;
  border-radius: 50%;
  background: var(--danger);
  color: white;
  font-size: 12px;
  display: flex;
  align-items: center;
  justify-content: center;
  box-shadow: var(--shadow-sm);
}
.remove-attachment:hover {
  transform: scale(1.1);
}

/* 输入行 */
.input-row {
  display: flex;
  align-items: flex-end;
  gap: 10px;
}
.input-actions {
  display: flex;
  gap: 4px;
  padding-bottom: 10px;
}
.action-icon {
  cursor: pointer;
  font-size: 20px;
  padding: 6px;
  transition: var(--transition);
  border-radius: 6px;
  display: flex;
  align-items: center;
}
.action-icon:hover {
  background: var(--primary-light);
}

.voice-btn {
  user-select: none;
  -webkit-user-select: none;
}
.voice-btn.recording {
  color: var(--danger);
  animation: pulse 1.5s infinite;
  background: rgba(239, 68, 68, 0.1);
}
@keyframes pulse {
  0% { transform: scale(1); }
  50% { transform: scale(1.15); }
  100% { transform: scale(1); }
}

.input-row textarea {
  flex: 1;
  padding: 13px 16px;
  border: 1.5px solid var(--border);
  border-radius: var(--radius-md);
  font-size: 15px;
  resize: none;
  max-height: 160px;
  line-height: 1.5;
  transition: var(--transition);
  background: #fafcff;
}
.input-row textarea:focus {
  border-color: var(--primary);
  background: white;
  box-shadow: 0 0 0 3px rgba(42, 111, 219, 0.08);
}
.input-row textarea:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.send-btn {
  width: 50px;
  height: 50px;
  border-radius: 50%;
  background: var(--primary);
  color: white;
  font-size: 20px;
  display: flex;
  align-items: center;
  justify-content: center;
  transition: var(--transition);
  flex-shrink: 0;
}
.send-btn:hover:not(:disabled) {
  background: var(--primary-dark);
  box-shadow: var(--shadow-md);
  transform: scale(1.05);
}
.send-btn:disabled {
  background: #b8c9e8;
  cursor: not-allowed;
}

.spinner-sm {
  width: 18px;
  height: 18px;
  border: 2.5px solid rgba(255, 255, 255, 0.3);
  border-top-color: white;
  border-radius: 50%;
  animation: spin 0.6s linear infinite;
}

/* 底部提示 */
.input-hint {
  display: flex;
  justify-content: space-between;
  font-size: 11px;
  color: var(--text-light);
  margin-top: 8px;
  padding: 0 4px;
}
.hint-session {
  font-family: monospace;
  font-size: 10px;
  color: #c0c8d8;
}

/* ==================== 响应式 ==================== */
@media (max-width: 768px) {
  .welcome-header h1 {
    font-size: 24px;
  }
  .welcome-header p {
    font-size: 15px;
  }
  .message-body {
    max-width: 85%;
  }
  .messages-inner {
    padding: 0 16px;
  }
  .input-area {
    padding: 12px 16px 16px;
  }
  .quick-actions {
    gap: 8px;
  }
  .action-btn {
    padding: 10px 16px;
    font-size: 13px;
  }
}
</style>