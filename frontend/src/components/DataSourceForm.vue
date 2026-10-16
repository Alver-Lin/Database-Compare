<template>
  <div class="ds-form">
    <a-form layout="vertical">
      <a-form-item label="历史数据源">
        <a-select
          v-model:value="historyId"
          allow-clear
          show-search
          option-filter-prop="label"
          placeholder="选择历史连接，自动填入"
          :options="historyOptions"
          :not-found-content="historyLoading ? '加载中...' : '暂无历史数据源'"
          @change="onHistoryChange"
        />
      </a-form-item>
      <a-form-item label="数据源类型">
        <a-select v-model:value="local.db_type" @change="onTypeChange">
          <a-select-option value="mysql">MySQL</a-select-option>
          <a-select-option value="mariadb">MariaDB</a-select-option>
          <a-select-option value="postgresql">PostgreSQL</a-select-option>
          <a-select-option value="sqlite">SQLite</a-select-option>
          <a-select-option value="dameng">达梦</a-select-option>
          <a-select-option value="oceanbase">OceanBase</a-select-option>
          <a-select-option value="oracle">Oracle</a-select-option>
        </a-select>
      </a-form-item>
      <template v-if="local.db_type === 'sqlite'">
        <a-form-item label="数据库文件路径">
          <a-input v-model:value="local.database" placeholder="例如 C:\\data\\demo_source.db" />
        </a-form-item>
      </template>
      <template v-else>
        <a-row :gutter="12">
          <a-col :span="16">
            <a-form-item label="主机地址">
              <a-input
                v-model:value="local.host"
                :placeholder="hostPlaceholder"
                @blur="normalizeEndpoint"
              />
            </a-form-item>
          </a-col>
          <a-col :span="8">
            <a-form-item label="端口">
              <a-input-number v-model:value="local.port" :min="1" :max="65535" style="width: 100%" />
            </a-form-item>
          </a-col>
        </a-row>
        <a-form-item label="用户名">
          <a-input v-model:value="local.user" :placeholder="userPlaceholder" />
        </a-form-item>
        <a-form-item label="密码">
          <a-input-password v-model:value="local.password" placeholder="请输入密码" />
        </a-form-item>
        <a-form-item v-if="local.db_type === 'oceanbase'" label="租户模式">
          <a-select v-model:value="local.ob_mode">
            <a-select-option value="auto">自动识别</a-select-option>
            <a-select-option value="mysql">MySQL 租户</a-select-option>
            <a-select-option value="oracle">Oracle 租户</a-select-option>
          </a-select>
        </a-form-item>
        <a-form-item :label="databaseLabel">
          <a-input v-model:value="local.database" :placeholder="databasePlaceholder" />
        </a-form-item>
      </template>
    </a-form>
    <div class="ds-actions">
      <a-button :loading="testing" @click="test">测试连接</a-button>
      <span v-if="status === 'ok'" class="ok">连接成功</span>
      <span v-else-if="status === 'fail'" class="fail">连接失败</span>
    </div>
  </div>
</template>

<script setup>
import { computed, onMounted, reactive, ref, watch } from 'vue'
import { message } from 'ant-design-vue'
import api from '../api'

const props = defineProps({
  modelValue: { type: Object, required: true },
})
const emit = defineEmits(['update:modelValue'])

const local = reactive({
  ...props.modelValue,
  ob_mode: props.modelValue?.ob_mode || 'auto',
})
const testing = ref(false)
const status = ref('')
const historyId = ref(undefined)
const historyLoading = ref(false)
const historyItems = ref([])

const historyOptions = computed(() =>
  historyItems.value.map((item) => ({ value: item.id, label: item.label })),
)

watch(
  local,
  () => emit('update:modelValue', { ...local }),
  { deep: true },
)

watch(
  () => props.modelValue,
  (val) => Object.assign(local, val),
)

const defaultPorts = {
  mysql: 3306,
  mariadb: 3306,
  postgresql: 5432,
  oceanbase: 2881,
  oracle: 1521,
  dameng: 5236,
}
const defaultUsers = {
  mysql: 'root',
  mariadb: 'root',
  postgresql: 'postgres',
  oceanbase: 'root@sys',
  oracle: 'system',
  dameng: 'SYSDBA',
}

const databaseLabel = computed(() => {
  if (local.db_type === 'oracle') return '服务名'
  if (local.db_type === 'dameng') return '默认模式（可选）'
  if (local.db_type === 'oceanbase' && local.ob_mode === 'oracle') return '服务名 / 租户名'
  return '默认数据库（可选）'
})

const databasePlaceholder = computed(() => {
  if (local.db_type === 'oracle') return 'ORCLPDB1，使用 SID 时填 SID:ORCL'
  if (local.db_type === 'dameng') return '可选，仅用于默认选中模式，勿填 DMSERVER'
  if (local.db_type === 'oceanbase' && local.ob_mode === 'oracle') {
    return '可空；用户名已含 @租户 时可不填'
  }
  if (local.db_type === 'oceanbase') return '可空；Oracle 租户请选 Oracle 模式或自动识别'
  return '连接后仍可在对比中选择库'
})

const userPlaceholder = computed(() => defaultUsers[local.db_type] || 'root')

const hostPlaceholder = computed(() => {
  if (local.db_type === 'oceanbase') return '主机名/IP，也可粘贴 jdbc:oceanbase://host:2881/db'
  if (local.db_type === 'oracle') return '127.0.0.1'
  if (local.db_type === 'dameng') return '127.0.0.1'
  return '127.0.0.1'
})

function normalizeEndpoint() {
  const raw = String(local.host || '').trim()
  if (!raw) return
  let text = raw
  if (/^jdbc:/i.test(text)) text = text.replace(/^jdbc:/i, '')
  if (!text.includes('://') && !text.includes('/') && !text.includes(':')) return

  if (text.includes('://')) text = text.split('://', 2)[1]
  text = text.split('?', 1)[0].split('#', 1)[0].trim()
  if (!text) return

  let path = ''
  if (text.includes('/')) {
    const parts = text.split('/')
    text = parts[0]
    path = parts.slice(1).join('/').replace(/^\/+|\/+$/g, '')
  }

  let host = text
  let port
  if (text.startsWith('[')) {
    const end = text.indexOf(']')
    if (end !== -1) {
      host = text.slice(1, end)
      const rest = text.slice(end + 1)
      if (rest.startsWith(':') && /^\d+$/.test(rest.slice(1))) port = Number(rest.slice(1))
    }
  } else if ((text.match(/:/g) || []).length === 1) {
    const [maybeHost, maybePort] = text.split(':')
    if (/^\d+$/.test(maybePort)) {
      host = maybeHost
      port = Number(maybePort)
    }
  }

  if (host) local.host = host
  if (port != null) local.port = port
  else if (!local.port && defaultPorts[local.db_type]) local.port = defaultPorts[local.db_type]
  if (path && !String(local.database || '').trim()) local.database = path.split('/')[0]
}

function onTypeChange(type) {
  historyId.value = undefined
  const ports = Object.values(defaultPorts)
  if (type === 'sqlite') {
    local.host = 'local'
    local.port = 0
    local.user = 'sqlite'
    local.password = ''
    return
  }
  const knownUsers = new Set(['', 'sqlite', ...Object.values(defaultUsers)])
  if (knownUsers.has(local.user || '')) local.user = defaultUsers[type] || 'root'
  if (local.host === 'local') local.host = '127.0.0.1'
  if (local.port === 0 || ports.includes(local.port)) {
    local.port = defaultPorts[type] || 3306
  }
  if (type === 'oceanbase' && !local.ob_mode) local.ob_mode = 'auto'
  if (type !== 'oceanbase') local.ob_mode = 'auto'
}

function onHistoryChange(id) {
  status.value = ''
  if (!id) return
  const item = historyItems.value.find((entry) => entry.id === id)
  if (!item?.config) return
  Object.assign(local, {
    db_type: item.config.db_type || 'mysql',
    host: item.config.host || '',
    port: item.config.port ?? 3306,
    user: item.config.user || '',
    password: item.config.password || '',
    database: item.config.database || '',
    ob_mode: item.config.ob_mode || 'auto',
  })
}

async function loadHistory() {
  historyId.value = undefined
  status.value = ''
  historyLoading.value = true
  try {
    historyItems.value = await api.listDatasources()
  } catch {
    historyItems.value = []
  } finally {
    historyLoading.value = false
  }
}

async function test() {
  normalizeEndpoint()
  testing.value = true
  status.value = ''
  try {
    const res = await api.testConnection({ ...local })
    if (res?.ob_mode) local.ob_mode = res.ob_mode
    status.value = 'ok'
    message.success(res.message || '连接成功')
  } catch {
    status.value = 'fail'
  } finally {
    testing.value = false
  }
}

onMounted(loadHistory)

defineExpose({ reloadHistory: loadHistory })
</script>

<style scoped>
.ds-actions {
  display: flex;
  align-items: center;
  gap: 12px;
}

.ok {
  color: #15803d;
  font-size: 13px;
}

.fail {
  color: #dc2626;
  font-size: 13px;
}
</style>
