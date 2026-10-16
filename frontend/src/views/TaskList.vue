<template>
  <div class="task-page">
    <div class="page-header">
      <div class="task-filters">
        <a-input
          v-model:value="keyword"
          allow-clear
          class="filter-name"
          placeholder="任务名称模糊搜索"
          @pressEnter="applyFilters"
        />
        <a-select
          v-model:value="statusFilter"
          allow-clear
          class="filter-status"
          placeholder="任务状态"
          :options="statusOptions"
        />
        <a-range-picker
          v-model:value="createdRange"
          class="filter-time"
          :placeholder="['创建开始时间', '创建结束时间']"
        />
        <a-space :size="8" class="filter-actions">
          <a-button type="primary" @click="applyFilters">查询</a-button>
          <a-button @click="resetFilters">重置</a-button>
        </a-space>
      </div>
      <a-button type="primary" size="large" @click="openCreate">
        <template #icon><PlusOutlined /></template>
        创建
      </a-button>
    </div>

    <a-card :bordered="false" class="table-card">
      <a-table
        row-key="id"
        :columns="columns"
        :data-source="filteredTasks"
        :loading="loading"
        :scroll="{ x: tableScrollX }"
        :pagination="{ pageSize: 10, showTotal: (t) => `共 ${t} 条` }"
      >
        <template #bodyCell="{ column, record }">
          <template v-if="column.key === 'name'">
            <a-tooltip :title="record.name">
              <span class="task-name">{{ shortTaskName(record.name) }}</span>
            </a-tooltip>
          </template>
          <template v-else-if="column.key === 'source'">
            <span class="source-tag">{{ formatDs(record.source) }}</span>
          </template>
          <template v-else-if="column.key === 'target'">
            <span class="target-tag">{{ formatDs(record.target) }}</span>
          </template>
          <template v-else-if="column.key === 'status'">
            <a-tag :color="record.status === 'completed' ? 'success' : 'processing'">
              {{ record.status === 'completed' ? '已完成' : '进行中' }}
            </a-tag>
          </template>
          <template v-else-if="column.key === 'created_at'">
            {{ formatTime(record.created_at) }}
          </template>
          <template v-else-if="column.key === 'action'">
            <a-space class="action-space" :size="4">
              <a-button type="link" @click="startCompare(record)">
                {{ record.status === 'completed' ? '继续对比' : '开始对比' }}
              </a-button>
              <a-button type="link" @click="openEdit(record)">编辑</a-button>
              <a-button type="link" :loading="copyingId === record.id" @click="copyTask(record)">
                复制
              </a-button>
              <a-button
                v-if="record.status === 'completed' && record.report"
                type="link"
                @click="viewReport(record)"
              >
                查看报告
              </a-button>
              <a-popconfirm title="确定删除该任务？" @confirm="remove(record)">
                <a-button type="link" danger>删除</a-button>
              </a-popconfirm>
            </a-space>
          </template>
        </template>
      </a-table>
    </a-card>

    <a-modal
      v-model:open="formOpen"
      :title="editingId ? '编辑数据对比任务' : '创建数据对比任务'"
      width="min(980px, calc(100vw - 32px))"
      :confirm-loading="saving"
      :ok-text="editingId ? '保存' : '创建任务'"
      cancel-text="取消"
      @ok="submit"
    >
      <a-form layout="vertical" class="name-form">
        <a-form-item label="任务名称" required>
          <a-input v-model:value="form.name" placeholder="例如：生产库 vs 测试库结构核对" />
        </a-form-item>
      </a-form>
      <a-row :gutter="16">
        <a-col :span="12">
          <a-card title="源数据源" size="small" class="ds-card source">
            <DataSourceForm ref="sourceFormRef" v-model="form.source" />
          </a-card>
        </a-col>
        <a-col :span="12">
          <a-card title="目标数据源" size="small" class="ds-card target">
            <DataSourceForm ref="targetFormRef" v-model="form.target" />
          </a-card>
        </a-col>
      </a-row>
    </a-modal>
  </div>
</template>

<script setup>
import { computed, onBeforeUnmount, onMounted, reactive, ref, nextTick } from 'vue'
import { useRouter } from 'vue-router'
import { PlusOutlined } from '@ant-design/icons-vue'
import { message } from 'ant-design-vue'
import dayjs from 'dayjs'
import api from '../api'
import DataSourceForm from '../components/DataSourceForm.vue'

const FILTER_STORAGE_KEY = 'dbcmp.taskList.filters'

const router = useRouter()
const loading = ref(false)
const saving = ref(false)
const copyingId = ref(null)
const formOpen = ref(false)
const editingId = ref(null)
const tasks = ref([])
const keyword = ref('')
const statusFilter = ref()
const createdRange = ref()
const appliedKeyword = ref('')
const appliedStatus = ref()
const appliedCreatedRange = ref()
const statusOptions = [
  { value: 'in_progress', label: '进行中' },
  { value: 'completed', label: '已完成' },
]
const sourceFormRef = ref(null)
const targetFormRef = ref(null)

function serializeRange(range) {
  if (!range?.[0] || !range?.[1]) return null
  return [range[0].toISOString(), range[1].toISOString()]
}

function parseRange(raw) {
  if (!raw?.[0] || !raw?.[1]) return undefined
  const start = dayjs(raw[0])
  const end = dayjs(raw[1])
  return start.isValid() && end.isValid() ? [start, end] : undefined
}

function saveFilters() {
  try {
    sessionStorage.setItem(
      FILTER_STORAGE_KEY,
      JSON.stringify({
        keyword: keyword.value || '',
        status: statusFilter.value ?? null,
        createdRange: serializeRange(createdRange.value),
        appliedKeyword: appliedKeyword.value || '',
        appliedStatus: appliedStatus.value ?? null,
        appliedCreatedRange: serializeRange(appliedCreatedRange.value),
      }),
    )
  } catch {
    /* ignore quota / private mode */
  }
}

function restoreFilters() {
  try {
    const raw = sessionStorage.getItem(FILTER_STORAGE_KEY)
    if (!raw) return
    const data = JSON.parse(raw)
    keyword.value = data.keyword || ''
    statusFilter.value = data.status || undefined
    createdRange.value = parseRange(data.createdRange)
    appliedKeyword.value = data.appliedKeyword || ''
    appliedStatus.value = data.appliedStatus || undefined
    appliedCreatedRange.value = parseRange(data.appliedCreatedRange)
  } catch {
    /* ignore broken cache */
  }
}

const emptyDs = (port) => ({
  db_type: port === 5432 ? 'postgresql' : 'mysql',
  host: '127.0.0.1',
  port,
  user: '',
  password: '',
  database: '',
  ob_mode: 'auto',
})

const form = reactive({
  name: '',
  source: emptyDs(3306),
  target: emptyDs(3306),
})

const columns = [
  { title: '任务名称', dataIndex: 'name', key: 'name', width: 176 },
  { title: '任务状态', key: 'status', width: 100 },
  { title: '创建时间', dataIndex: 'created_at', key: 'created_at', width: 188 },
  { title: '源数据源', key: 'source', width: 268 },
  { title: '目标数据源', key: 'target', width: 268 },
  { title: '操作', key: 'action', width: 392 },
]

const tableScrollX = columns.reduce((sum, column) => sum + (column.width || 0), 0)

const filteredTasks = computed(() => {
  const text = appliedKeyword.value.trim().toLowerCase()
  return tasks.value.filter((task) => {
    if (text && !String(task.name || '').toLowerCase().includes(text)) return false
    if (appliedStatus.value === 'completed' && task.status !== 'completed') return false
    if (appliedStatus.value === 'in_progress' && task.status === 'completed') return false
    const range = appliedCreatedRange.value
    if (range?.[0] && range?.[1]) {
      const time = dayjs(task.created_at)
      if (!time.isValid()) return false
      if (time.isBefore(range[0].startOf('day')) || time.isAfter(range[1].endOf('day'))) return false
    }
    return true
  })
})

function applyFilters() {
  appliedKeyword.value = keyword.value
  appliedStatus.value = statusFilter.value
  appliedCreatedRange.value = createdRange.value
  saveFilters()
}

function resetFilters() {
  keyword.value = ''
  statusFilter.value = undefined
  createdRange.value = undefined
  appliedKeyword.value = ''
  appliedStatus.value = undefined
  appliedCreatedRange.value = undefined
  saveFilters()
}

function shortTaskName(name) {
  const text = String(name || '')
  return text.length > 10 ? `${text.slice(0, 10)}…` : text
}

function dbTypeLabel(dbType) {
  const key = (dbType || '').toLowerCase()
  return { dameng: '达梦', oceanbase: 'OceanBase', oracle: 'Oracle' }[key] || (dbType || '').toUpperCase()
}

function formatDs(ds) {
  if (!ds) return '-'
  const type = dbTypeLabel(ds.db_type)
  if ((ds.db_type || '').toLowerCase() === 'sqlite') {
    const path = ds.database || ''
    const name = path.split(/[/\\]/).pop()
    return `SQLITE ${name}`
  }
  return `${type} ${ds.host}:${ds.port}`
}

function formatTime(value) {
  return value ? dayjs(value).format('YYYY-MM-DD HH:mm:ss') : '-'
}

function cloneDs(ds) {
  return {
    db_type: ds?.db_type || 'mysql',
    host: ds?.host || '',
    port: ds?.port ?? 3306,
    user: ds?.user || '',
    password: ds?.password || '',
    database: ds?.database || '',
    ob_mode: ds?.ob_mode || 'auto',
  }
}

async function load() {
  loading.value = true
  try {
    tasks.value = await api.listTasks()
  } finally {
    loading.value = false
  }
}

function openCreate() {
  editingId.value = null
  form.name = ''
  form.source = emptyDs(3306)
  form.target = emptyDs(3306)
  formOpen.value = true
  nextTick(() => {
    sourceFormRef.value?.reloadHistory?.()
    targetFormRef.value?.reloadHistory?.()
  })
}

async function openEdit(record) {
  saving.value = true
  try {
    const task = await api.getTask(record.id, { include_password: true })
    editingId.value = task.id
    form.name = task.name || ''
    form.source = cloneDs(task.source)
    form.target = cloneDs(task.target)
    formOpen.value = true
    nextTick(() => {
      sourceFormRef.value?.reloadHistory?.()
      targetFormRef.value?.reloadHistory?.()
    })
  } finally {
    saving.value = false
  }
}

function validateForm() {
  if (!form.name.trim()) {
    message.warning('请填写任务名称')
    return false
  }
  if (!form.source.host || (!form.source.user && form.source.db_type !== 'sqlite')) {
    message.warning('请完善源数据源信息')
    return false
  }
  if (form.source.db_type === 'sqlite' && !form.source.database) {
    message.warning('请填写源 SQLite 文件路径')
    return false
  }
  if (form.source.db_type === 'oracle' && !String(form.source.database || '').trim()) {
    message.warning('请填写源 Oracle 服务名')
    return false
  }
  if (!form.target.host || (!form.target.user && form.target.db_type !== 'sqlite')) {
    message.warning('请完善目标数据源信息')
    return false
  }
  if (form.target.db_type === 'sqlite' && !form.target.database) {
    message.warning('请填写目标 SQLite 文件路径')
    return false
  }
  if (form.target.db_type === 'oracle' && !String(form.target.database || '').trim()) {
    message.warning('请填写目标 Oracle 服务名')
    return false
  }
  return true
}

async function submit() {
  if (!validateForm()) return
  saving.value = true
  try {
    const payload = {
      name: form.name.trim(),
      source: { ...form.source },
      target: { ...form.target },
    }
    if (editingId.value) {
      await api.updateTask(editingId.value, payload)
      message.success('任务已保存')
    } else {
      await api.createTask(payload)
      message.success('任务已创建')
    }
    formOpen.value = false
    editingId.value = null
    await load()
  } finally {
    saving.value = false
  }
}

function startCompare(record) {
  router.push({ name: 'compare', params: { id: record.id } })
}

function viewReport(record) {
  router.push({ name: 'compare-report', params: { id: record.id } })
}

async function copyTask(record) {
  copyingId.value = record.id
  try {
    const copied = await api.copyTask(record.id)
    message.success(`已复制为进行中任务：${copied.name || ''}`)
    await load()
  } finally {
    copyingId.value = null
  }
}

async function remove(record) {
  await api.deleteTask(record.id)
  message.success('已删除')
  await load()
}

onMounted(() => {
  restoreFilters()
  load()
})

onBeforeUnmount(() => {
  saveFilters()
})
</script>

<style scoped>
.task-filters {
  display: flex;
  flex: 1;
  flex-wrap: wrap;
  align-items: center;
  gap: 12px;
  min-width: 0;
}

.filter-name {
  width: 220px;
}

.filter-status {
  width: 140px;
}

.filter-time {
  width: 280px;
}

.filter-actions {
  flex: 0 0 auto;
}

.table-card {
  border-radius: 12px;
  overflow: hidden;
}

.table-card :deep(.ant-table-content) {
  overflow-x: auto !important;
}

.table-card :deep(.ant-table-content > table) {
  table-layout: fixed !important;
  width: 1392px !important;
  min-width: 1392px;
}

.action-space {
  white-space: nowrap;
}

.action-space :deep(.ant-btn-link) {
  padding-inline: 4px;
}

.table-card :deep(.ant-table-thead > tr > th),
.table-card :deep(.ant-table-tbody > tr > td) {
  padding-left: 12px;
  padding-right: 12px;
}

.table-card :deep(.source-tag),
.table-card :deep(.target-tag) {
  white-space: nowrap;
}

.task-name {
  display: inline-block;
  max-width: 10em;
  overflow: hidden;
  white-space: nowrap;
  vertical-align: bottom;
  cursor: default;
}

.name-form {
  margin-bottom: 8px;
}

.ds-card.source :deep(.ant-card-head) {
  background: #f0f5ff;
}

.ds-card.target :deep(.ant-card-head) {
  background: #f0fdf4;
}
</style>
