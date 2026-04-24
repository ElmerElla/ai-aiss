<template>
  <div class="admin-dashboard-page">
    <header class="topbar">
      <div>
        <h1>课表管理后台</h1>
        <p>
          欢迎，{{ adminAuth.displayName || adminAuth.username }}
          <span class="badge">{{ adminAuth.role || 'admin' }}</span>
        </p>
      </div>
      <div class="topbar-actions">
        <button class="ghost-btn" @click="loadSummary">刷新统计</button>
        <button class="danger-btn" @click="handleLogout">退出登录</button>
      </div>
    </header>

    <section class="summary-grid">
      <article class="metric-card">
        <h3>待处理调课</h3>
        <p>{{ summary.pending_adjustments }}</p>
      </article>
      <article class="metric-card">
        <h3>启用课表</h3>
        <p>{{ summary.active_schedules }}</p>
      </article>
      <article class="metric-card">
        <h3>停用课表</h3>
        <p>{{ summary.cancelled_schedules }}</p>
      </article>
      <article class="metric-card">
        <h3>班级总数</h3>
        <p>{{ summary.total_classes }}</p>
      </article>
      <article class="metric-card">
        <h3>学期总数</h3>
        <p>{{ summary.total_terms }}</p>
      </article>
    </section>

    <section class="panel filter-panel">
      <div class="filter-row">
        <div class="field">
          <label>学期</label>
          <select v-model="filters.term_id">
            <option value="">全部学期</option>
            <option v-for="term in terms" :key="term.term_id" :value="term.term_id">
              {{ term.term_id }} ({{ term.start_date }} ~ {{ term.end_date }})
            </option>
          </select>
        </div>

        <div class="field">
          <label>班级</label>
          <select v-model="filters.class_id">
            <option value="">全部班级</option>
            <option v-for="cls in classes" :key="cls.class_id" :value="cls.class_id">
              {{ cls.class_name }} / {{ cls.major_name }}
            </option>
          </select>
        </div>

        <div class="field">
          <label>状态</label>
          <select v-model="filters.schedule_status">
            <option value="">全部</option>
            <option value="active">active</option>
            <option value="cancelled">cancelled</option>
          </select>
        </div>

        <div class="field">
          <label>第几周</label>
          <select v-model="filters.week_no">
            <option value="">全部周次</option>
            <option v-for="week in weekOptions" :key="week" :value="String(week)">
              第{{ week }}周
            </option>
          </select>
        </div>

        <div class="field field-keyword">
          <label>关键词</label>
          <input
            v-model="filters.keyword"
            type="text"
            placeholder="课程/老师/教室/班级"
            @keyup.enter="applyFilters"
          />
        </div>
      </div>

      <div class="filter-actions">
        <button class="primary-btn" @click="applyFilters">查询</button>
        <button class="ghost-btn" @click="resetFilters">重置</button>
      </div>
    </section>

    <section class="panel table-panel">
      <div class="table-toolbar">
        <p>
          共 {{ total }} 条
          <span v-if="loadingSchedules">（正在加载）</span>
        </p>
        <div>
          <label>每页</label>
          <select v-model.number="filters.limit" @change="applyFilters">
            <option :value="20">20</option>
            <option :value="30">30</option>
            <option :value="50">50</option>
            <option :value="100">100</option>
          </select>
        </div>
      </div>

      <Transition name="fade">
        <div v-if="errorMsg" class="error-msg">{{ errorMsg }}</div>
      </Transition>

      <div class="table-wrap">
        <table>
          <thead>
            <tr>
              <th>课表ID</th>
              <th>学期</th>
              <th>课程</th>
              <th>教师</th>
              <th>教室</th>
              <th>时间</th>
              <th>班级</th>
              <th>状态</th>
              <th>版本</th>
              <th>更新时间</th>
              <th>操作</th>
            </tr>
          </thead>
          <tbody>
            <tr v-if="!loadingSchedules && schedules.length === 0">
              <td colspan="11" class="empty-cell">暂无数据</td>
            </tr>
            <tr v-for="item in schedules" :key="item.schedule_id">
              <td class="mono">{{ item.schedule_id }}</td>
              <td>{{ item.term_id }}</td>
              <td>{{ item.course_name }}</td>
              <td>{{ item.teacher_name }}</td>
              <td>{{ item.room_location }}</td>
              <td>{{ formatScheduleTime(item) }}</td>
              <td>{{ formatClasses(item.classes) }}</td>
              <td>
                <span class="status-chip" :class="item.schedule_status">
                  {{ item.schedule_status }}
                </span>
              </td>
              <td>{{ item.version }}</td>
              <td>{{ formatDateTime(item.updated_at) }}</td>
              <td>
                <button
                  class="mini-btn"
                  :class="item.schedule_status === 'active' ? 'warn' : 'ok'"
                  @click="toggleScheduleStatus(item)"
                >
                  {{ item.schedule_status === 'active' ? '停用' : '启用' }}
                </button>
              </td>
            </tr>
          </tbody>
        </table>
      </div>

      <div class="pagination">
        <button class="ghost-btn" :disabled="currentPage <= 1" @click="prevPage">上一页</button>
        <span>第 {{ currentPage }} / {{ totalPages }} 页</span>
        <button class="ghost-btn" :disabled="currentPage >= totalPages" @click="nextPage">下一页</button>
      </div>
    </section>
  </div>
</template>

<script setup>
import { computed, onMounted, reactive, ref } from 'vue'
import { useRouter } from 'vue-router'
import { adminApi } from '@/api/admin'
import { useAdminAuthStore } from '@/stores/adminAuth'

const router = useRouter()
const adminAuth = useAdminAuthStore()

const summary = reactive({
  pending_adjustments: 0,
  active_schedules: 0,
  cancelled_schedules: 0,
  total_classes: 0,
  total_terms: 0
})

const terms = ref([])
const classes = ref([])
const schedules = ref([])
const total = ref(0)
const weekOptions = Array.from({ length: 30 }, (_, index) => index + 1)

const filters = reactive({
  term_id: '',
  class_id: '',
  week_no: '',
  schedule_status: '',
  keyword: '',
  limit: 30,
  offset: 0
})

const loadingSchedules = ref(false)
const errorMsg = ref('')

const currentPage = computed(() => Math.floor(filters.offset / filters.limit) + 1)
const totalPages = computed(() => {
  const pages = Math.ceil(total.value / filters.limit)
  return pages > 0 ? pages : 1
})

function buildQueryParams() {
  const params = {
    limit: filters.limit,
    offset: filters.offset
  }
  if (filters.term_id) params.term_id = filters.term_id
  if (filters.class_id) params.class_id = filters.class_id
  if (filters.week_no) params.week_no = Number(filters.week_no)
  if (filters.schedule_status) params.schedule_status = filters.schedule_status
  if (filters.keyword.trim()) params.keyword = filters.keyword.trim()
  return params
}

async function loadMeta() {
  const [termsRes, classesRes] = await Promise.all([adminApi.getTerms(), adminApi.getClasses()])
  terms.value = termsRes.data || []
  classes.value = classesRes.data || []
}

async function loadSummary() {
  const { data } = await adminApi.getSummary()
  summary.pending_adjustments = data.pending_adjustments || 0
  summary.active_schedules = data.active_schedules || 0
  summary.cancelled_schedules = data.cancelled_schedules || 0
  summary.total_classes = data.total_classes || 0
  summary.total_terms = data.total_terms || 0
}

async function loadSchedules() {
  loadingSchedules.value = true
  errorMsg.value = ''

  try {
    const { data } = await adminApi.getSchedules(buildQueryParams())
    schedules.value = data.items || []
    total.value = data.total || 0
  } catch (error) {
    errorMsg.value = error.response?.data?.detail || '加载课表失败，请稍后重试'
    schedules.value = []
    total.value = 0
  } finally {
    loadingSchedules.value = false
  }
}

async function initialize() {
  try {
    await Promise.all([loadMeta(), loadSummary()])
    await loadSchedules()
  } catch (error) {
    errorMsg.value = error.response?.data?.detail || '初始化失败，请检查管理员权限或后端服务'
  }
}

function applyFilters() {
  filters.offset = 0
  loadSchedules()
}

function resetFilters() {
  filters.term_id = ''
  filters.class_id = ''
  filters.week_no = ''
  filters.schedule_status = ''
  filters.keyword = ''
  filters.limit = 30
  filters.offset = 0
  loadSchedules()
}

function prevPage() {
  if (currentPage.value <= 1) return
  filters.offset = Math.max(0, filters.offset - filters.limit)
  loadSchedules()
}

function nextPage() {
  if (currentPage.value >= totalPages.value) return
  filters.offset += filters.limit
  loadSchedules()
}

function formatClasses(items) {
  if (!items?.length) return '-'
  return items.map((item) => item.class_name).join('、')
}

function formatScheduleTime(item) {
  const dayMap = {
    1: '周一',
    2: '周二',
    3: '周三',
    4: '周四',
    5: '周五',
    6: '周六',
    7: '周日'
  }
  const dayLabel = dayMap[item.day_of_week] || `周${item.day_of_week}`
  const patternLabel = item.week_pattern === 'odd' ? '单周' : item.week_pattern === 'even' ? '双周' : '全周'
  return `第${item.week_no}周 ${dayLabel} 第${item.start_period}-${item.end_period}节 (${patternLabel})`
}

function formatDateTime(value) {
  if (!value) return '-'
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return String(value)
  return date.toLocaleString('zh-CN', { hour12: false })
}

async function toggleScheduleStatus(item) {
  const isActive = item.schedule_status === 'active'
  const targetStatus = isActive ? 'cancelled' : 'active'

  const confirmed = window.confirm(
    isActive
      ? `确认停用课表 ${item.schedule_id} 吗？`
      : `确认启用课表 ${item.schedule_id} 吗？`
  )
  if (!confirmed) return

  let reason = ''
  if (isActive) {
    reason = window.prompt('请输入停用原因（可选）', '') || ''
  }

  try {
    await adminApi.updateScheduleStatus(item.schedule_id, targetStatus, reason)
    await Promise.all([loadSchedules(), loadSummary()])
  } catch (error) {
    errorMsg.value = error.response?.data?.detail || '更新课表状态失败'
  }
}

function handleLogout() {
  adminAuth.logout()
  router.replace({ name: 'AdminLogin' })
}

onMounted(() => {
  initialize()
})
</script>

<style scoped>
.admin-dashboard-page {
  min-height: 100vh;
  padding: 18px;
  background:
    radial-gradient(circle at top right, rgba(42, 111, 219, 0.08), transparent 40%),
    radial-gradient(circle at bottom left, rgba(255, 152, 0, 0.08), transparent 42%),
    #f5f8ff;
}

.topbar {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  gap: 12px;
  margin-bottom: 16px;
}

.topbar h1 {
  font-size: 28px;
  color: #1d4f99;
  margin-bottom: 6px;
}

.topbar p {
  color: var(--text-muted);
  display: flex;
  gap: 8px;
  align-items: center;
}

.badge {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  border-radius: 999px;
  padding: 2px 10px;
  font-size: 12px;
  color: #1d4f99;
  border: 1px solid rgba(29, 79, 153, 0.25);
  background: rgba(29, 79, 153, 0.06);
}

.topbar-actions {
  display: flex;
  gap: 10px;
}

.panel {
  background: #fff;
  border: 1px solid var(--border-light);
  border-radius: var(--radius-md);
  box-shadow: var(--shadow-sm);
  padding: 14px;
  margin-bottom: 14px;
}

.summary-grid {
  display: grid;
  grid-template-columns: repeat(5, minmax(0, 1fr));
  gap: 10px;
  margin-bottom: 14px;
}

.metric-card {
  background: #fff;
  border-radius: var(--radius-md);
  border: 1px solid var(--border-light);
  box-shadow: var(--shadow-sm);
  padding: 12px;
}

.metric-card h3 {
  font-size: 13px;
  color: var(--text-muted);
  margin-bottom: 8px;
}

.metric-card p {
  font-size: 24px;
  font-weight: 700;
  color: #204f92;
}

.filter-row {
  display: grid;
  grid-template-columns: 1fr 1fr 180px 160px 1.2fr;
  gap: 10px;
}

.field label {
  display: block;
  font-size: 12px;
  color: var(--text-muted);
  margin-bottom: 5px;
}

.field select,
.field input {
  width: 100%;
  height: 36px;
  border: 1px solid var(--border);
  border-radius: var(--radius-sm);
  padding: 0 10px;
  font-size: 13px;
}

.field select:focus,
.field input:focus {
  border-color: var(--primary);
  box-shadow: 0 0 0 3px rgba(42, 111, 219, 0.1);
}

.filter-actions {
  display: flex;
  gap: 8px;
  margin-top: 12px;
}

.table-toolbar {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 10px;
}

.table-toolbar p {
  font-size: 13px;
  color: var(--text-muted);
}

.table-toolbar label {
  font-size: 12px;
  color: var(--text-muted);
  margin-right: 6px;
}

.table-toolbar select {
  border: 1px solid var(--border);
  border-radius: var(--radius-sm);
  height: 32px;
  padding: 0 8px;
}

.table-wrap {
  width: 100%;
  overflow: auto;
  border: 1px solid var(--border-light);
  border-radius: var(--radius-sm);
}

table {
  width: 100%;
  border-collapse: collapse;
  min-width: 1350px;
}

th,
td {
  border-bottom: 1px solid var(--border-light);
  text-align: left;
  font-size: 13px;
  padding: 9px 10px;
  vertical-align: top;
}

th {
  background: #f7faff;
  color: #335f9d;
  position: sticky;
  top: 0;
  z-index: 1;
}

.mono {
  font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, Liberation Mono, Courier New, monospace;
  font-size: 12px;
}

.status-chip {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  min-width: 82px;
  padding: 2px 8px;
  border-radius: 999px;
  font-size: 12px;
  font-weight: 600;
  border: 1px solid;
}

.status-chip.active {
  color: var(--success);
  background: #edf7ef;
  border-color: #bae3c0;
}

.status-chip.cancelled {
  color: var(--danger);
  background: #fdecec;
  border-color: #f6c7c7;
}

.empty-cell {
  text-align: center;
  color: var(--text-muted);
  padding: 30px 0;
}

.error-msg {
  border-radius: var(--radius-sm);
  background: var(--danger-light);
  color: var(--danger);
  border: 1px solid #ffcdd2;
  padding: 10px 12px;
  font-size: 13px;
  margin-bottom: 10px;
}

.pagination {
  margin-top: 12px;
  display: flex;
  justify-content: flex-end;
  align-items: center;
  gap: 10px;
}

.primary-btn,
.ghost-btn,
.danger-btn,
.mini-btn {
  border-radius: var(--radius-sm);
  border: none;
  height: 36px;
  padding: 0 14px;
  font-size: 13px;
  transition: var(--transition);
}

.primary-btn {
  background: var(--primary);
  color: #fff;
}

.primary-btn:hover {
  background: var(--primary-hover);
}

.ghost-btn {
  background: #fff;
  border: 1px solid var(--border);
  color: var(--text-secondary);
}

.ghost-btn:hover:not(:disabled) {
  border-color: var(--primary);
  color: var(--primary);
}

.danger-btn {
  color: #fff;
  background: linear-gradient(120deg, #d94f45, #ec6a5c);
}

.danger-btn:hover {
  filter: brightness(0.98);
}

.mini-btn {
  height: 30px;
  min-width: 58px;
  padding: 0 10px;
  font-size: 12px;
}

.mini-btn.warn {
  background: #ffe8e3;
  color: #cb4f43;
  border: 1px solid #f0bab3;
}

.mini-btn.ok {
  background: #e8f4eb;
  color: #2a7a4b;
  border: 1px solid #c0e2cc;
}

button:disabled {
  opacity: 0.62;
  cursor: not-allowed;
}

@media (max-width: 1280px) {
  .summary-grid {
    grid-template-columns: repeat(3, minmax(0, 1fr));
  }

  .filter-row {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
}

@media (max-width: 768px) {
  .admin-dashboard-page {
    padding: 12px;
  }

  .topbar {
    flex-direction: column;
    align-items: stretch;
  }

  .summary-grid {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }

  .filter-row {
    grid-template-columns: 1fr;
  }

  .pagination {
    justify-content: center;
  }
}
</style>
