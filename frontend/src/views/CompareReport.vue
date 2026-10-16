<template>
  <div class="report-page">
    <a-card :bordered="false" class="report-card" :loading="loading">
      <div class="report-top">
        <div>
          <div class="report-title">对比报告</div>
          <div class="report-sub" v-if="report?.generatedAt">
            生成时间：{{ formatTime(report.generatedAt) }}
          </div>
        </div>
        <a-space>
          <a-button
            v-if="report"
            :loading="downloadingPdf"
            @click="downloadPdf"
          >
            <template #icon><DownloadOutlined /></template>
            下载 PDF
          </a-button>
          <a-button v-if="taskId" @click="continueCompare">继续对比</a-button>
          <a-button type="primary" @click="goHome">返回任务列表</a-button>
        </a-space>
      </div>

      <a-empty v-if="!loading && !report" description="暂无对比报告" />

      <template v-else-if="report">
        <div class="section">
          <div class="section-title">任务信息</div>
          <a-descriptions bordered :column="1" size="middle">
            <a-descriptions-item label="任务名称">{{ report.taskName || '-' }}</a-descriptions-item>
            <a-descriptions-item label="源库">
              <span class="source-tag">{{ report.sourceLabel || '-' }}</span>
              <span v-if="report.sourceDb" class="db-name"> / {{ report.sourceDb }}</span>
              <span v-if="report.sourceSchema" class="db-name"> / {{ report.sourceSchema }}</span>
            </a-descriptions-item>
            <a-descriptions-item label="目标库">
              <span class="target-tag">{{ report.targetLabel || '-' }}</span>
              <span v-if="report.targetDb" class="db-name"> / {{ report.targetDb }}</span>
              <span v-if="report.targetSchema" class="db-name"> / {{ report.targetSchema }}</span>
            </a-descriptions-item>
          </a-descriptions>
        </div>

        <div v-if="miniMaps.length" class="section">
          <div class="section-title">字段映射微缩预览</div>
          <div v-for="map in miniMaps" :key="map.targetTable" class="mini-map">
            <div class="mini-map-row">
              <div class="mini-map-main">
                <div class="mini-map-canvas" :style="{ minHeight: `${map.height}px` }">
                  <div class="mini-head-side source">源字段</div>
                  <div class="mini-head-gap" />
                  <div class="mini-head-side target">目标字段</div>
                  <div class="mini-col left">
                    <div
                      v-for="field in map.left"
                      :key="field.key"
                      class="mini-field"
                      :class="{ join: field.isJoin }"
                      :style="{ height: `${ITEM_H}px` }"
                    >
                      <span class="mini-chip source">
                        <span class="chip-table">{{ field.table }}</span>
                        <span class="chip-dot">.</span>
                        <span class="chip-field">{{ field.field }}</span>
                      </span>
                      <span class="mini-dot" />
                    </div>
                  </div>
                  <svg
                    class="mini-svg"
                    :width="GAP_W"
                    :height="map.height"
                    :viewBox="`0 0 ${GAP_W} ${map.height}`"
                  >
                    <path
                      v-for="line in map.joinLines"
                      :key="line.id"
                      :d="line.d"
                      class="mini-path join"
                    />
                    <path
                      v-for="line in map.lines"
                      :key="line.id"
                      :d="line.d"
                      class="mini-path"
                    />
                  </svg>
                  <div class="mini-col right" :style="{ paddingTop: `${map.rightOffset}px` }">
                    <div
                      v-for="field in map.right"
                      :key="field.key"
                      class="mini-field right"
                      :style="{ height: `${ITEM_H}px` }"
                    >
                      <span class="mini-dot target" />
                      <span class="mini-chip target">
                        <span class="chip-table">{{ field.table }}</span>
                        <span class="chip-dot">.</span>
                        <span class="chip-field">{{ field.field }}</span>
                      </span>
                    </div>
                  </div>
                </div>
              </div>
              <div class="mini-head-legend">
                <span class="legend-item">
                  <i class="legend-line solid" />
                  字段映射
                </span>
                <span class="legend-item">
                  <i class="legend-line dash" />
                  跨表关联
                </span>
              </div>
            </div>
          </div>
        </div>

        <div class="section">
          <div class="section-title">对比明细</div>
          <a-empty v-if="!(report.tables || []).length" description="暂无对比表" />
          <div v-else class="detail-list">
            <div
              v-for="(record, tableIndex) in report.tables"
              :key="record.id"
              class="detail-card"
            >
              <div class="detail-card-head">
                <span class="detail-index">{{ tableIndex + 1 }}</span>
                <div class="detail-card-head-text">
                  <div class="detail-card-name">
                    <template v-if="record.sourceTables?.length > 1">
                      {{ record.sourceTables.join(' + ') }}
                    </template>
                    <template v-else>{{ record.sourceTable }}</template>
                    <span class="pair-arrow">↔</span>
                    {{ record.targetTable }}
                  </div>
                  <div class="detail-card-sub">对比数据表</div>
                </div>
              </div>

              <div class="detail-block">
                <div class="detail-block-title">
                  <span class="block-badge">维度</span>
                  对比维度
                </div>
                <div class="detail-block-body scope-row">
                  <div class="scope-block">
                    <div class="scope-label">内容对比字段</div>
                    <div v-if="!record.compareFields?.length" class="muted">未指定（按已映射字段）</div>
                    <div v-else class="chip-list">
                      <span
                        v-for="(field, idx) in record.compareFields"
                        :key="idx"
                        class="info-chip"
                      >
                        {{ field.label }}
                      </span>
                      <span class="mode-chip" :class="record.compareFuzzy ? 'fuzzy' : 'exact'">
                        {{ record.compareFuzzy ? '模糊内容对比' : '精确对比' }}
                      </span>
                    </div>
                  </div>
                  <div class="scope-block">
                    <div class="scope-label">对应关系</div>
                    <div v-if="!record.valueAliases?.length" class="muted">无</div>
                    <div v-else class="chip-list">
                      <span
                        v-for="(alias, idx) in record.valueAliases"
                        :key="idx"
                        class="info-chip alias"
                      >
                        {{ alias.sourceField }}:{{ formatAliasValue(alias.sourceValue) }}
                        =
                        {{ alias.targetField }}:{{ formatAliasValue(alias.targetValue) }}
                      </span>
                    </div>
                  </div>
                  <div class="scope-block">
                    <div class="scope-label">提取匹配规则</div>
                    <div v-if="!record.extractMatchRules?.length" class="muted">无</div>
                    <div v-else class="chip-list">
                      <span
                        v-for="(rule, idx) in record.extractMatchRules"
                        :key="idx"
                        class="info-chip alias"
                      >
                        {{ rule.sourceField }}[{{ rule.sourcePositions }}]
                        =
                        {{ rule.targetField }}[{{ rule.targetPositions }}]
                      </span>
                    </div>
                  </div>
                  <div class="scope-block">
                    <div class="scope-label">模糊搜索条件</div>
                    <div v-if="!hasSearchFilters(record)" class="muted">无</div>
                    <div v-else class="chip-list">
                      <span
                        v-for="(line, idx) in searchFilterDisplay(record, 'source')"
                        :key="`s-${idx}`"
                        class="info-chip"
                        :class="line.kind === 'logic' ? 'logic' : 'source'"
                      >
                        <template v-if="line.kind === 'logic'">{{ line.text }}</template>
                        <template v-else>源 · {{ line.text }}</template>
                      </span>
                      <span
                        v-for="(line, idx) in searchFilterDisplay(record, 'target')"
                        :key="`t-${idx}`"
                        class="info-chip"
                        :class="line.kind === 'logic' ? 'logic' : 'target'"
                      >
                        <template v-if="line.kind === 'logic'">{{ line.text }}</template>
                        <template v-else>目标 · {{ line.text }}</template>
                      </span>
                    </div>
                  </div>
                </div>
              </div>

              <div class="detail-block result-block">
                <div class="detail-block-title">
                  <span class="block-badge result">结果</span>
                  字段内容对比
                </div>
                <div class="detail-block-body">
                  <div v-if="!record.compared" class="muted">
                    {{
                      reportHasFilteredStats
                        ? '当前报告按筛选条件仅统计当前对比表'
                        : '未进行内容对比'
                    }}
                  </div>
                  <div v-else-if="record.statsMode === 'filtered'" class="result-panel">
                    <div class="result-main ok">
                      <template v-if="record.sourceTotal === record.targetTotal">
                        按当前筛选条件：源数据 {{ record.sourceTotal }} 条 = 目标数据 {{ record.targetTotal }} 条
                      </template>
                      <template v-else>
                        按当前筛选条件：源数据 {{ record.sourceTotal }} 条，目标数据 {{ record.targetTotal }} 条
                      </template>
                    </div>
                    <div v-if="record.sourceTotal !== record.targetTotal" class="result-extra">
                      按较少一侧计一致数量：{{ record.matched }}
                    </div>
                    <div v-if="record.leftOnly" class="result-extra warn">源侧多出：{{ record.leftOnly }}</div>
                    <div v-if="record.rightOnly" class="result-extra warn">目标侧多出：{{ record.rightOnly }}</div>
                  </div>
                  <div v-else class="result-panel">
                    <div class="result-grid">
                      <div class="result-metric">
                        <span class="metric-label">源侧数量</span>
                        <span class="metric-value">{{ record.sourceTotal }}</span>
                      </div>
                      <div class="result-metric">
                        <span class="metric-label">目标侧数量</span>
                        <span class="metric-value">{{ record.targetTotal }}</span>
                      </div>
                      <div class="result-metric ok">
                        <span class="metric-label">一致数量</span>
                        <span class="metric-value">{{ record.matched }}</span>
                      </div>
                      <div class="result-metric warn">
                        <span class="metric-label">源侧不一致</span>
                        <span class="metric-value">{{ record.leftOnly }}</span>
                      </div>
                      <div class="result-metric warn">
                        <span class="metric-label">目标侧不一致</span>
                        <span class="metric-value">{{ record.rightOnly }}</span>
                      </div>
                    </div>
                  </div>
                </div>
              </div>
            </div>
          </div>

          <div class="notes-card">
            <div class="notes-head">
              <div>
                <div class="notes-title">对比报表说明</div>
                <div class="notes-sub">可补充本次对比结论、注意事项或其他说明</div>
              </div>
              <a-button type="primary" :loading="savingNotes" @click="saveNotes">保存说明</a-button>
            </div>
            <a-textarea
              v-model:value="reportNotes"
              :rows="5"
              :maxlength="2000"
              show-count
              placeholder="请输入对比报表说明…"
              class="notes-input"
            />
          </div>
        </div>
      </template>
    </a-card>
  </div>
</template>

<script setup>
import { computed, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { message } from 'ant-design-vue'
import { DownloadOutlined } from '@ant-design/icons-vue'
import dayjs from 'dayjs'
import api from '../api'

const props = defineProps({
  id: { type: [String, Number], required: true },
})

const router = useRouter()
const loading = ref(false)
const savingNotes = ref(false)
const downloadingPdf = ref(false)
const report = ref(null)
const taskId = ref(null)
const reportNotes = ref('')

const ITEM_H = 40
const GAP_W = 132

const reportHasFilteredStats = computed(() =>
  (report.value?.tables || []).some((item) => item.statsMode === 'filtered'),
)

function hasSearchFilters(record) {
  const source = record?.searchFilters?.source || []
  const target = record?.searchFilters?.target || []
  return source.length > 0 || target.length > 0
}

function searchFilterLogicLabel(logic, fallback = 'and') {
  const value = String(logic || fallback || 'and').toLowerCase()
  return value === 'or' ? '或' : '且'
}

function searchFilterLines(record, side) {
  const modeLabel = {
    include: '包含',
    exclude: '不包含',
    equals: '等于',
    not_equals: '不等于',
  }
  const fallbackKey = side === 'source' ? 'sourceLogic' : 'targetLogic'
  const fallback = record?.searchFilters?.[fallbackKey] || 'and'
  return (record?.searchFilters?.[side] || []).map((item, idx) => {
    const field = item.field || '全部字段'
    const mode = modeLabel[item.mode] || (item.negate ? '不包含' : '包含')
    const keywords = (item.keywords || []).join(' / ')
    return {
      text: `${field} ${mode} ${keywords}`,
      logic: idx === 0 ? 'and' : searchFilterLogicLabel(item.logic, fallback),
    }
  })
}

function searchFilterDisplay(record, side) {
  const lines = searchFilterLines(record, side)
  if (!lines.length) return []
  if (lines.length === 1) return [{ kind: 'cond', text: lines[0].text }]
  const items = []
  lines.forEach((line, idx) => {
    if (idx > 0) items.push({ kind: 'logic', text: line.logic })
    items.push({ kind: 'cond', text: line.text })
  })
  return items
}

const miniMaps = computed(() => {
  const tables = report.value?.tables || []
  const byTarget = new Map()

  for (const row of tables) {
    const targetTable = row.targetTable
    if (!targetTable) continue
    if (!byTarget.has(targetTable)) {
      byTarget.set(targetTable, { links: [], joins: row.sourceJoins || [] })
    }
    const bucket = byTarget.get(targetTable)
    if (row.sourceJoins?.length) bucket.joins = row.sourceJoins
    for (const col of row.columns || []) {
      if (!col?.source || !col?.target) continue
      const sourceTable = col.sourceTable || row.sourceTable
      if (!sourceTable || String(sourceTable).includes(' + ')) continue
      bucket.links.push({
        sourceTable,
        source: col.source,
        target: col.target,
        sourceKey: `${sourceTable}.${col.source}`,
        targetKey: `${targetTable}.${col.target}`,
      })
    }
  }

  const rootJoins = report.value?.sourceJoins || {}
  for (const [targetTable, joins] of Object.entries(rootJoins)) {
    if (!byTarget.has(targetTable)) continue
    if (joins?.length) byTarget.get(targetTable).joins = joins
  }

  const maps = []
  for (const [targetTable, bucket] of byTarget.entries()) {
    const links = []
    const seenCol = new Set()
    for (const link of bucket.links) {
      const id = `${link.sourceKey}->${link.targetKey}`
      if (seenCol.has(id)) continue
      seenCol.add(id)
      links.push(link)
    }

    const left = []
    const right = []
    const leftIndex = new Map()
    const rightIndex = new Map()

    function splitKey(key) {
      const i = String(key).lastIndexOf('.')
      if (i <= 0) return { table: '', field: String(key) }
      return { table: String(key).slice(0, i), field: String(key).slice(i + 1) }
    }
    function ensureLeft(key, opts = {}) {
      if (leftIndex.has(key)) {
        if (opts.isJoin) left[leftIndex.get(key)].isJoin = true
        return leftIndex.get(key)
      }
      const parts = splitKey(key)
      const idx = left.length
      leftIndex.set(key, idx)
      left.push({
        key,
        label: key,
        table: parts.table,
        field: parts.field,
        isJoin: !!opts.isJoin,
      })
      return idx
    }
    function ensureRight(key) {
      if (rightIndex.has(key)) return rightIndex.get(key)
      const parts = splitKey(key)
      const idx = right.length
      rightIndex.set(key, idx)
      right.push({
        key,
        label: key,
        table: parts.table,
        field: parts.field,
      })
      return idx
    }

    const joins = bucket.joins || []
    const primary =
      joins[0]?.leftTable ||
      links.find((l) => l.sourceTable)?.sourceTable ||
      ''

    for (const link of links) {
      if (primary && link.sourceTable !== primary) continue
      ensureLeft(link.sourceKey)
      ensureRight(link.targetKey)
    }
    for (const join of joins) {
      if (!join?.leftTable || !join?.leftField || !join?.rightTable || !join?.rightField) continue
      ensureLeft(`${join.leftTable}.${join.leftField}`, { isJoin: true })
      ensureLeft(`${join.rightTable}.${join.rightField}`, { isJoin: true })
    }
    for (const link of links) {
      if (primary && link.sourceTable === primary) continue
      ensureLeft(link.sourceKey)
      ensureRight(link.targetKey)
    }
    for (const link of links) ensureRight(link.targetKey)

    if (!left.length && !right.length) continue

    const height = Math.max(left.length, 1) * ITEM_H
    const rightOffset = Math.max(0, Math.floor(((left.length - right.length) * ITEM_H) / 2))

    const lines = []
    const seenLink = new Set()
    for (const link of links) {
      const id = `${link.sourceKey}->${link.targetKey}`
      if (seenLink.has(id)) continue
      seenLink.add(id)
      const li = leftIndex.get(link.sourceKey)
      const ri = rightIndex.get(link.targetKey)
      const y1 = li * ITEM_H + ITEM_H / 2
      const y2 = ri * ITEM_H + ITEM_H / 2 + rightOffset
      const mid = GAP_W / 2
      lines.push({
        id,
        y1,
        y2,
        d: `M 0 ${y1} C ${mid} ${y1}, ${mid} ${y2}, ${GAP_W} ${y2}`,
      })
    }

    const joinLines = []
    const seenJoin = new Set()
    for (const join of joins) {
      if (!join?.leftTable || !join?.leftField || !join?.rightTable || !join?.rightField) continue
      const aKey = `${join.leftTable}.${join.leftField}`
      const bKey = `${join.rightTable}.${join.rightField}`
      const id = `join:${aKey}=${bKey}`
      if (seenJoin.has(id)) continue
      seenJoin.add(id)
      const li = leftIndex.get(aKey)
      const ri = leftIndex.get(bKey)
      if (li == null || ri == null) continue
      const y1 = li * ITEM_H + ITEM_H / 2
      const y2 = ri * ITEM_H + ITEM_H / 2
      const bulge = Math.min(GAP_W * 0.42, 48)
      joinLines.push({
        id,
        y1,
        y2,
        d: `M 0 ${y1} C ${bulge} ${y1}, ${bulge} ${y2}, 0 ${y2}`,
      })
    }

    // Mark join-only fields (appear in join but not in column mappings)
    const mappedLeft = new Set(links.map((l) => l.sourceKey))
    for (const field of left) {
      if (!mappedLeft.has(field.key)) field.isJoin = true
    }

    maps.push({
      targetTable,
      left,
      right,
      lines,
      joinLines,
      rightOffset,
      height,
    })
  }
  return maps
})

function formatAliasValue(value) {
  const text = String(value ?? '')
  return text === '' ? '(空)' : text
}

function formatTime(value) {
  return value ? dayjs(value).format('YYYY-MM-DD HH:mm:ss') : '-'
}

function goHome() {
  router.push({ name: 'tasks' })
}

function continueCompare() {
  router.push({ name: 'compare', params: { id: props.id } })
}

function safePdfFilename(name) {
  const base = String(name || '对比报告').trim() || '对比报告'
  return `${base.replace(/[\\/:*?"<>|]/g, '_')}-对比报告.pdf`
}

async function downloadPdf() {
  if (!report.value || downloadingPdf.value) return
  downloadingPdf.value = true
  try {
    const blob = await api.downloadReportPdf(props.id)
    if (!(blob instanceof Blob)) {
      throw new Error('下载失败：返回内容无效')
    }
    if (blob.type && blob.type.includes('application/json')) {
      const text = await blob.text()
      let detail = '下载失败'
      try {
        const data = JSON.parse(text)
        detail = data.detail || detail
      } catch {
        /* ignore */
      }
      throw new Error(detail)
    }
    const url = URL.createObjectURL(blob)
    const link = document.createElement('a')
    link.href = url
    link.download = safePdfFilename(report.value.taskName)
    document.body.appendChild(link)
    link.click()
    link.remove()
    URL.revokeObjectURL(url)
    message.success('PDF 已开始下载')
  } catch (err) {
    if (!err?.response) {
      message.error(err?.message || '下载 PDF 失败')
    }
  } finally {
    downloadingPdf.value = false
  }
}

async function saveNotes() {
  if (!report.value || !taskId.value) return
  savingNotes.value = true
  try {
    const nextReport = {
      ...report.value,
      description: reportNotes.value || '',
    }
    await api.updateTask(props.id, { report: nextReport })
    report.value = nextReport
    message.success('对比报表说明已保存')
  } finally {
    savingNotes.value = false
  }
}

async function load() {
  loading.value = true
  try {
    const task = await api.getTask(props.id)
    taskId.value = task.id
    report.value = task.report || null
    reportNotes.value = task.report?.description || ''
  } finally {
    loading.value = false
  }
}

onMounted(load)
</script>

<style scoped>
.report-card {
  border-radius: 12px;
}

.report-top {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  margin-bottom: 20px;
  gap: 16px;
}

.report-title {
  font-size: 18px;
  font-weight: 650;
}

.report-sub {
  margin-top: 6px;
  color: #667085;
  font-size: 13px;
}

.section {
  margin-bottom: 24px;
}

.section-title {
  font-weight: 650;
  margin-bottom: 12px;
  font-size: 15px;
}

.db-name {
  color: #475467;
  margin-left: 4px;
}

.col-list {
  display: flex;
  flex-direction: column;
  gap: 4px;
  line-height: 1.5;
}

.detail-list {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.detail-card {
  border: 1px solid #e4eaf3;
  border-radius: 14px;
  background: linear-gradient(180deg, #ffffff 0%, #f8fafc 100%);
  box-shadow: 0 8px 24px rgba(15, 23, 42, 0.04);
  overflow: hidden;
}

.detail-card-head {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 16px 18px;
  background: linear-gradient(135deg, rgba(47, 111, 237, 0.08), rgba(18, 183, 106, 0.06));
  border-bottom: 1px solid #e8eef6;
}

.detail-index {
  flex: 0 0 28px;
  width: 28px;
  height: 28px;
  border-radius: 999px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  background: #2f6fed;
  color: #fff;
  font-size: 13px;
  font-weight: 700;
}

.detail-card-name {
  font-size: 15px;
  font-weight: 650;
  color: #1d2939;
  line-height: 1.4;
}

.pair-arrow {
  display: inline-block;
  margin: 0 8px;
  color: #667085;
  font-weight: 500;
}

.detail-card-sub {
  margin-top: 2px;
  font-size: 12px;
  color: #98a2b3;
}

.detail-block {
  padding: 16px 18px;
}

.detail-block + .detail-block {
  border-top: 1px solid #eef2f6;
}

.detail-block-title {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 13px;
  font-weight: 650;
  color: #344054;
  margin-bottom: 12px;
}

.block-badge {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  min-width: 40px;
  padding: 0 8px;
  height: 22px;
  border-radius: 999px;
  background: #eef4ff;
  color: #2f6fed;
  font-size: 12px;
  font-weight: 650;
}

.block-badge.result {
  background: #e8f8ef;
  color: #039855;
}

.detail-block-body {
  color: #475467;
  line-height: 1.55;
}

.scope-row {
  display: flex;
  align-items: stretch;
  gap: 12px;
}

.scope-row .scope-block {
  flex: 1;
  min-width: 0;
  padding: 12px 14px;
  border-radius: 12px;
  background: #ffffff;
  border: 1px solid #eef2f6;
}

.scope-label {
  font-weight: 650;
  color: #344054;
  margin-bottom: 10px;
}

.chip-list {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}

.info-chip {
  display: inline-flex;
  align-items: center;
  max-width: 100%;
  padding: 4px 10px;
  border-radius: 999px;
  background: #f2f4f7;
  color: #344054;
  font-size: 12px;
  line-height: 1.4;
  word-break: break-all;
}

.info-chip.alias {
  background: #fff7ed;
  color: #b54708;
}

.info-chip.source {
  background: #eff6ff;
  color: #175cd3;
}

.info-chip.target {
  background: #ecfdf3;
  color: #067647;
}

.info-chip.logic {
  background: #f2f4f7;
  color: #667085;
  font-weight: 650;
  min-width: 28px;
  justify-content: center;
}

.mode-chip {
  display: inline-flex;
  align-items: center;
  padding: 4px 10px;
  border-radius: 999px;
  font-size: 12px;
  font-weight: 600;
}

.mode-chip.fuzzy {
  background: #f4f3ff;
  color: #5925dc;
}

.mode-chip.exact {
  background: #f2f4f7;
  color: #475467;
}

.result-block {
  background: linear-gradient(180deg, rgba(3, 152, 85, 0.03), transparent);
}

.result-panel {
  padding: 14px 16px;
  border-radius: 12px;
  background: #ffffff;
  border: 1px solid #d1fadf;
}

.result-main {
  font-size: 15px;
  font-weight: 650;
  line-height: 1.5;
}

.result-main.ok,
.stats .ok,
.result-metric.ok .metric-value {
  color: #039855;
}

.result-extra {
  margin-top: 6px;
  color: #475467;
}

.result-extra.warn,
.stats .warn,
.result-metric.warn .metric-value {
  color: #b54708;
}

.result-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(120px, 1fr));
  gap: 10px;
}

.result-metric {
  padding: 10px 12px;
  border-radius: 10px;
  background: #f8fafc;
  border: 1px solid #eef2f6;
}

.metric-label {
  display: block;
  font-size: 12px;
  color: #98a2b3;
  margin-bottom: 4px;
}

.metric-value {
  font-size: 18px;
  font-weight: 700;
  color: #1d2939;
}

.notes-card {
  margin-top: 16px;
  padding: 16px 18px 18px;
  border: 1px solid #e4eaf3;
  border-radius: 14px;
  background: #ffffff;
  box-shadow: 0 8px 24px rgba(15, 23, 42, 0.04);
}

.notes-head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 12px;
  margin-bottom: 12px;
}

.notes-title {
  font-size: 14px;
  font-weight: 650;
  color: #1d2939;
}

.notes-sub {
  margin-top: 4px;
  font-size: 12px;
  color: #98a2b3;
}

.notes-input :deep(textarea) {
  border-radius: 10px;
  min-height: 120px;
  resize: vertical;
}

@media (max-width: 900px) {
  .scope-row {
    flex-direction: column;
  }

  .notes-head {
    flex-direction: column;
  }
}

.stats {
  display: flex;
  flex-direction: column;
  gap: 2px;
  line-height: 1.55;
}

.muted {
  color: #98a2b3;
}

.source-tag,
.target-tag {
  font-weight: 600;
}

.mini-map {
  margin-bottom: 16px;
  padding: 14px 18px 16px;
  border: 1px solid #e8eef6;
  border-radius: 14px;
  background:
    radial-gradient(120% 80% at 0% 0%, rgba(47, 111, 237, 0.06), transparent 55%),
    radial-gradient(120% 80% at 100% 100%, rgba(18, 183, 106, 0.06), transparent 55%),
    #fbfcfe;
  overflow-x: auto;
}

.mini-map-row {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 24px;
}

.mini-map-main {
  min-width: 0;
}

.mini-map-canvas {
  display: inline-grid;
  grid-template-columns: max-content 132px max-content;
  grid-template-rows: auto auto;
  align-items: start;
  column-gap: 0;
  row-gap: 10px;
}

.mini-head-side {
  font-size: 12px;
  font-weight: 650;
  letter-spacing: 0.02em;
  line-height: 1;
  align-self: end;
}

.mini-head-side.source {
  color: #175cd3;
  justify-self: end;
  padding-right: 19px; /* align with chips (gap 10 + dot 9) */
}

.mini-head-side.target {
  color: #087443;
  justify-self: start;
  padding-left: 19px;
}

.mini-head-gap {
  width: 132px;
  height: 1px;
}

.mini-head-legend {
  display: flex;
  flex-direction: column;
  align-items: flex-start;
  justify-content: flex-start;
  gap: 8px;
  padding-top: 2px;
  flex-shrink: 0;
}

.legend-item {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  font-size: 11px;
  color: #667085;
  white-space: nowrap;
}

.legend-line {
  display: inline-block;
  width: 18px;
  height: 0;
  border-top: 2px solid #2f6fed;
}

.legend-line.dash {
  border-top-style: dashed;
}

.mini-col {
  display: flex;
  flex-direction: column;
}

.mini-field {
  display: flex;
  align-items: center;
  gap: 10px;
  box-sizing: border-box;
  padding: 0 2px;
  width: 100%;
}

.mini-field:not(.right) {
  justify-content: flex-end;
}

.mini-field.right {
  justify-content: flex-start;
}

.mini-chip {
  display: inline-flex;
  align-items: baseline;
  max-width: 320px;
  padding: 5px 10px;
  border-radius: 8px;
  border: 1px solid transparent;
  font-size: 12px;
  line-height: 1.35;
  white-space: nowrap;
}

.mini-chip.source {
  background: #eff4ff;
  border-color: #d6e4ff;
  color: #1d2939;
}

.mini-chip.target {
  background: #edfcf2;
  border-color: #aaefc6;
  color: #1d2939;
}

.mini-field.join .mini-chip.source {
  background: #f5f8ff;
  border-style: dashed;
  border-color: #b2ccff;
}

.chip-table {
  color: #667085;
  font-weight: 500;
}

.chip-dot {
  color: #98a2b3;
}

.chip-field {
  color: #101828;
  font-weight: 650;
}

.mini-svg {
  display: block;
  overflow: visible;
}

.mini-path {
  fill: none;
  stroke: #2f6fed;
  stroke-width: 1.8;
  stroke-linecap: round;
}

.mini-path.join {
  stroke: #2f6fed;
  stroke-dasharray: 5 4;
  stroke-width: 1.6;
  opacity: 0.9;
}

.mini-dot {
  flex-shrink: 0;
  width: 9px;
  height: 9px;
  border-radius: 50%;
  background: #2f6fed;
  box-shadow: 0 0 0 3px rgba(47, 111, 237, 0.12);
}

.mini-field.join .mini-dot {
  background: #2f6fed;
  box-shadow: 0 0 0 3px rgba(47, 111, 237, 0.08);
  outline: 1px dashed rgba(47, 111, 237, 0.55);
  outline-offset: 1px;
}

.mini-dot.target {
  background: #12b76a;
  box-shadow: 0 0 0 3px rgba(18, 183, 106, 0.14);
}
</style>
