<template>
  <div class="wizard-page">
    <a-card :bordered="false" class="wizard-card">
      <div class="wizard-top">
        <div>
          <div class="task-name">{{ task?.name || '对比任务' }}</div>
          <div class="task-ds" v-if="task">
            <span class="source-tag">{{ formatDs(task.source) }}</span>
            <span class="arrow">→</span>
            <span class="target-tag">{{ formatDs(task.target) }}</span>
          </div>
        </div>
        <a-button @click="goHome">返回任务列表</a-button>
      </div>

      <a-steps :current="current" class="steps" size="small">
        <a-step title="选择库表" description="选择源库与目标库" />
        <a-step title="对比数据表" description="表名数量与关联" />
        <a-step title="对比数据表内容" description="字段结构关联" />
        <a-step title="对比数据字段内容" description="字段值对比" />
      </a-steps>

      <div class="step-body">
        <div v-show="current === 0" class="db-step">
          <div class="pair-bar">
            <a-checkbox v-model:checked="syncDbScroll">同步滚动</a-checkbox>
          </div>
          <a-row :gutter="16">
            <a-col :span="12">
              <a-card title="源数据库" size="small">
                <a-spin :spinning="loading.sourceDb">
                  <a-input
                    v-model:value="dbKeyword.source"
                    placeholder="搜索数据库"
                    allow-clear
                    class="mb"
                  />
                  <div class="db-list" ref="sourceDbListRef" @scroll="onDbScroll('source')">
                    <div
                      v-for="name in filteredDbs('source')"
                      :key="name"
                      class="db-item"
                      :class="{ active: state.sourceDb === name }"
                      @click="selectDb('source', name)"
                    >
                      {{ name }}
                    </div>
                    <div v-if="!filteredDbs('source').length" class="empty">暂无数据库</div>
                  </div>
                  <div v-if="schemas.source.length" class="schema-row">
                    Schema
                    <a-select
                      v-model:value="state.sourceSchema"
                      style="width: 100%; margin-top: 8px"
                      :options="schemaOptions('source')"
                      @change="onSchemaChange('source')"
                    />
                  </div>
                </a-spin>
              </a-card>
            </a-col>
            <a-col :span="12">
              <a-card title="目标数据库" size="small">
                <a-spin :spinning="loading.targetDb">
                  <a-input
                    v-model:value="dbKeyword.target"
                    placeholder="搜索数据库"
                    allow-clear
                    class="mb"
                  />
                  <div class="db-list" ref="targetDbListRef" @scroll="onDbScroll('target')">
                    <div
                      v-for="name in filteredDbs('target')"
                      :key="name"
                      class="db-item"
                      :class="{ active: state.targetDb === name }"
                      @click="selectDb('target', name)"
                    >
                      {{ name }}
                    </div>
                    <div v-if="!filteredDbs('target').length" class="empty">暂无数据库</div>
                  </div>
                  <div v-if="schemas.target.length" class="schema-row">
                    Schema
                    <a-select
                      v-model:value="state.targetSchema"
                      style="width: 100%; margin-top: 8px"
                      :options="schemaOptions('target')"
                      @change="onSchemaChange('target')"
                    />
                  </div>
                </a-spin>
              </a-card>
            </a-col>
          </a-row>
        </div>

        <div v-show="current === 1">
          <MappingCanvas
            left-title="源数据表"
            right-title="目标数据表"
            unit="张表"
            allow-shared-target
            :left-items="tableItems.source"
            :right-items="tableItems.target"
            :left-loading="loading.sourceTables"
            :right-loading="loading.targetTables"
            v-model:mappings="state.tableMappings"
          />
        </div>

        <div v-show="current === 2">
          <div class="pair-bar">
            <template v-if="targetTableOptions.length > 1">
              <span>目标表</span>
              <a-tag
                v-for="opt in targetTableOptions"
                :key="opt.value"
                class="target-chip"
                :color="opt.value === currentTargetTable ? 'blue' : undefined"
                @click="selectTargetTable(opt.value)"
              >
                {{ opt.label }}
              </a-tag>
            </template>
            <template v-else>
              <span class="target-label">目标表：{{ tableDisplayLabel('target', currentTargetTable) }}</span>
            </template>
            <span class="pair-hint">展开源表后，可连到右侧目标字段；也可点两个源表字段互连做跨表关联（支持一对多，如 sys.id 同时连 duty_catalog_sys 与 datakey）。源侧或目标侧均可单独勾选字段，仅作下一步展示，不参与匹配</span>
          </div>
          <MappingCanvas
            left-title="源数据表"
            right-title="目标数据表结构"
            unit="列"
            allow-left-joins
            allow-shared-target
            allow-display-only
            :left-groups="columnLeftGroups"
            :right-items="columnItems.target"
            :left-loading="loading.sourceColumns"
            :right-loading="loading.targetColumns"
            :dim-unmatched="false"
            :search-reset-key="`${currentTargetTable || ''}`"
            v-model:mappings="allColumnMappingsForTarget"
            v-model:left-joins="currentLeftJoins"
            v-model:display-selections="currentDisplaySelections"
            @update:display-selections="onDisplaySelectionsPersist"
          />
        </div>

        <div v-show="current === 3">
          <div class="pair-bar">
            <template v-if="contentTargetOptions.length > 1">
              <span class="target-label">当前源数据表：{{ tableDisplayLabel('source', currentContentSource) }}；当前目标表：</span>
              <a-tag
                v-for="opt in contentTargetOptions"
                :key="opt.value"
                class="target-chip"
                :color="opt.value === currentContentTarget ? 'blue' : undefined"
                @click="selectContentTarget(opt.value)"
              >
                {{ opt.label }}
              </a-tag>
            </template>
            <template v-else>
              <span class="target-label">
                当前源数据表：{{ tableDisplayLabel('source', currentContentSource) }}；当前目标表：{{ tableDisplayLabel('target', currentContentTarget) }}
              </span>
            </template>
            <a-button @click="openAliasModal">
              对应关系{{ aliasRuleTotal ? `（${aliasRuleTotal}）` : '' }}
            </a-button>
          </div>
          <div v-if="singleCompareActive" class="single-compare-banner">
            <span>
              正在单条字段对比：匹配
              <b class="ok">{{ singleCompareStats.match }}</b>
              ，不匹配
              <b class="bad">{{ singleCompareStats.mismatch }}</b>
              （蓝线=匹配，红线=不匹配）
            </span>
            <a-button size="small" @click="exitSingleCompare">退出单条对比</a-button>
          </div>
          <MappingCanvas
            left-title="源数据表字段内容"
            right-title="目标数据字段内容"
            unit="行"
            virtual
            dot-link-only
            :left-items="rowItems.source"
            :right-items="rowItems.target"
            :left-count="rowTotals.source"
            :right-count="rowTotals.target"
            :mapped-count="rowMatchedTotal"
            :left-match-total="hasRowSearchKeywords('source') ? searchTotals.source : hideMappedRows ? unmatchedTotals.source : null"
            :right-match-total="hasRowSearchKeywords('target') ? searchTotals.target : hideMappedRows ? unmatchedTotals.target : null"
            :left-loading="loading.sourceRows"
            :right-loading="loading.targetRows"
            :dim-unmatched="false"
            v-model:mappings="state.rowMappings"
            v-model:hide-mapped="hideMappedRows"
            hide-mapped-enabled
            server-search
            :search-reset-key="`${currentContentTarget || state.currentTablePair || ''}#${searchUiEpoch}`"
            :left-search-fields="rowSearchFieldOptions.source"
            :right-search-fields="rowSearchFieldOptions.target"
            :left-search-seed="rowSearchConditions.source"
            :right-search-seed="rowSearchConditions.target"
            :left-search-logic-seed="rowSearchLogic.source"
            :right-search-logic-seed="rowSearchLogic.target"
            :field-links="singleCompareFieldLinks"
            :full-compare-fn="compareAllFieldContent"
            show-export
            @edit-match="onRowEditMatch"
            @clear-match="onClearRowMatch"
            @search="onRowSearch"
            @export-rows="openExportRowsModal"
          />
        </div>
      </div>

      <div class="wizard-footer">
        <div v-if="current === 3" class="pager">
          <span>每页条数</span>
          <a-select
            v-model:value="rowPageSize"
            style="width: 120px"
            :options="rowPageSizeOptions"
            @change="onRowPageSizeChange"
          />
          <a-pagination
            v-model:current="rowPage"
            :page-size="rowPageSize"
            :total="rowPageTotal"
            size="small"
              :show-total="rowPageTotalText"
            @change="loadRows"
          />
        </div>
        <div v-else class="pager"></div>
        <div class="footer-actions">
          <a-button v-if="current > 0" @click="prev">上一步</a-button>
          <a-button v-if="current < 3" type="primary" :loading="loading.next" @click="next">
            下一步
          </a-button>
          <a-button v-else type="primary" :loading="loading.finish" @click="finish">完成</a-button>
        </div>
      </div>
    </a-card>

    <a-modal
      v-model:open="aliasModalOpen"
      title="字段匹配规则"
      :width="900"
      :footer="null"
      destroy-on-close
    >
      <a-tabs v-model:activeKey="aliasModalTab">
        <a-tab-pane key="value" tab="值对应关系">
          <div class="alias-hint">
            仅可选择上一步已连线的字段。设置
            <code>status:3 = version_status:PUBLISHED</code> 后，点「内容对比」时会视为相等。字段值可留空，用于匹配空字符串或 NULL。
          </div>
          <div class="alias-form">
            <a-select
              v-model:value="aliasDraft.sourceField"
              show-search
              allow-clear
              option-filter-prop="label"
              placeholder="源字段"
              style="width: 160px"
              :options="sourceAliasFieldOptions"
              :not-found-content="aliasFieldEmptyText"
              @change="onAliasFieldChange('source')"
            />
            <a-auto-complete
              v-model:value="aliasDraft.sourceValue"
              :options="sourceValueOptions"
              placeholder="源字段值（可空）"
              style="width: 150px"
              allow-clear
            />
            <span class="alias-eq">=</span>
            <a-select
              v-model:value="aliasDraft.targetField"
              show-search
              allow-clear
              option-filter-prop="label"
              placeholder="目标字段"
              style="width: 160px"
              :options="targetAliasFieldOptions"
              :not-found-content="aliasFieldEmptyText"
              @change="onAliasFieldChange('target')"
            />
            <a-auto-complete
              v-model:value="aliasDraft.targetValue"
              :options="targetValueOptions"
              placeholder="目标字段值（可空）"
              style="width: 150px"
              allow-clear
            />
            <a-button type="primary" @click="addValueAlias">添加</a-button>
          </div>
          <a-table
            row-key="id"
            size="small"
            :pagination="false"
            :data-source="aliasTableRows"
            :columns="aliasTableColumns"
            :locale="{ emptyText: '还没有对应关系' }"
          >
            <template #bodyCell="{ column, record }">
              <template v-if="column.key === 'rule'">
                <span class="alias-rule">
                  {{ record.sourceField }}:{{ formatAliasValue(record.sourceValue) }} =
                  {{ record.targetField }}:{{ formatAliasValue(record.targetValue) }}
                </span>
              </template>
              <template v-else-if="column.key === 'action'">
                <a-button type="link" danger size="small" @click="removeValueAlias(record.id)">删除</a-button>
              </template>
            </template>
          </a-table>
        </a-tab-pane>

        <a-tab-pane key="extract" tab="提取匹配规则">
          <div class="alias-hint">
            按字符位置抽取子串后精准相等。从前往后：<code>1245</code> 表示第 1、2、4、5 位；
            从后往前：<code>-1245</code> 表示倒数第 1、2、4、5 位（-1=最后一位）。
            超过 9 或正负混用请用逗号：<code>1,2,-2,-1</code>。
            同一字段对可添加多条规则，满足其中任意一条即可匹配。
          </div>
          <div class="alias-form">
            <a-select
              v-model:value="extractDraft.sourceField"
              show-search
              allow-clear
              option-filter-prop="label"
              placeholder="源字段"
              style="width: 160px"
              :options="sourceAliasFieldOptions"
              :not-found-content="aliasFieldEmptyText"
              @change="onExtractFieldChange('source')"
            />
            <a-input
              v-model:value="extractDraft.sourcePositions"
              placeholder="源取位，如 1245 或 -1245"
              style="width: 150px"
              allow-clear
            />
            <span class="alias-eq">=</span>
            <a-select
              v-model:value="extractDraft.targetField"
              show-search
              allow-clear
              option-filter-prop="label"
              placeholder="目标字段"
              style="width: 160px"
              :options="targetAliasFieldOptions"
              :not-found-content="aliasFieldEmptyText"
              @change="onExtractFieldChange('target')"
            />
            <a-input
              v-model:value="extractDraft.targetPositions"
              placeholder="目标取位，如 4578 或 -5421"
              style="width: 150px"
              allow-clear
            />
            <a-button type="primary" @click="addExtractRule">添加</a-button>
          </div>
          <a-table
            row-key="id"
            size="small"
            :pagination="false"
            :data-source="extractTableRows"
            :columns="extractTableColumns"
            :locale="{ emptyText: '还没有提取匹配规则' }"
          >
            <template #bodyCell="{ column, record }">
              <template v-if="column.key === 'rule'">
                <span class="alias-rule">
                  {{ record.sourceField }}[{{ record.sourcePositions }}] =
                  {{ record.targetField }}[{{ record.targetPositions }}]
                </span>
              </template>
              <template v-else-if="column.key === 'action'">
                <a-button type="link" danger size="small" @click="removeExtractRule(record.id)">删除</a-button>
              </template>
            </template>
          </a-table>
        </a-tab-pane>
      </a-tabs>
    </a-modal>

    <a-modal
      v-model:open="compareFieldsModalOpen"
      title="选择对比字段"
      :width="640"
      :footer="null"
      destroy-on-close
      :maskClosable="false"
      @cancel="cancelCompareFieldsModal"
    >
      <div class="alias-hint">
        勾选参与行匹配的字段。建议只选能唯一确定一行的关键字段；展示字段可不勾选。已选
        {{ compareFieldChecked.length }}/{{ compareFieldOptions.length }}。
      </div>
      <div class="compare-field-toolbar">
        <a-button size="small" @click="selectAllCompareFields">全选</a-button>
        <a-button size="small" @click="clearCompareFields">全不选</a-button>
        <a-button size="small" @click="invertCompareFields">反选</a-button>
      </div>
      <div class="compare-field-list">
        <a-checkbox-group v-model:value="compareFieldChecked" class="compare-field-group">
          <label
            v-for="item in compareFieldOptions"
            :key="item.value"
            class="compare-field-item"
            :class="{ checked: isCompareFieldChecked(item.value) }"
          >
            <span
              class="compare-field-mark"
              :class="isCompareFieldChecked(item.value) ? 'yes' : 'no'"
            >
              {{ isCompareFieldChecked(item.value) ? '√' : '×' }}
            </span>
            <a-checkbox :value="item.value">{{ item.label }}</a-checkbox>
          </label>
        </a-checkbox-group>
      </div>
      <div class="compare-field-footer">
        <div class="compare-fuzzy-hint">
          模糊对比会忽略 JSON 数组 / 逗号分隔 / 纯字符串等格式差异，只要内容能对应即可。
        </div>
        <div class="compare-field-actions">
          <a-button @click="cancelCompareFieldsModal">取消</a-button>
          <a-button :loading="compareFieldsSubmitting" @click="openSingleComparePicker">
            指定单条对比
          </a-button>
          <a-button :loading="compareFieldsSubmitting" @click="confirmCompareFieldsModal(false)">
            精确对比
          </a-button>
          <a-button
            type="primary"
            :loading="compareFieldsSubmitting"
            @click="confirmCompareFieldsModal(true)"
          >
            模糊内容对比
          </a-button>
        </div>
      </div>
    </a-modal>

    <a-modal
      v-model:open="exportRowsModalOpen"
      title="导出字段内容"
      :width="780"
      :footer="null"
      destroy-on-close
      :maskClosable="false"
    >
      <div class="alias-hint">
        按当前筛选条件导出。可分别勾选源表 / 目标表字段；Excel 含两个工作表：源数据表字段内容、目标数据表字段内容。首行为字段名，其后为数据行。
      </div>
      <div class="export-rows-grid">
        <div class="export-rows-pane">
          <div class="export-rows-pane-head">
            <a-checkbox
              :checked="exportIncludeSource"
              :indeterminate="exportSourceIndeterminate"
              @change="(e) => toggleExportSide('source', !!(e?.target?.checked ?? e))"
            >
              源表数据
            </a-checkbox>
            <span class="export-rows-count">已选 {{ exportSourceChecked.length }}/{{ exportSourceOptions.length }}</span>
          </div>
          <div class="export-rows-tools">
            <a-button size="small" @click="selectAllExportFields('source')">全选</a-button>
            <a-button size="small" @click="clearExportFields('source')">全不选</a-button>
          </div>
          <div class="export-rows-list">
            <a-checkbox-group v-model:value="exportSourceChecked" class="export-rows-group">
              <label
                v-for="item in exportSourceOptions"
                :key="item.value"
                class="export-rows-item"
              >
                <a-checkbox :value="item.value">{{ item.label }}</a-checkbox>
              </label>
            </a-checkbox-group>
            <div v-if="!exportSourceOptions.length" class="export-rows-empty">暂无可选源字段</div>
          </div>
        </div>
        <div class="export-rows-pane">
          <div class="export-rows-pane-head">
            <a-checkbox
              :checked="exportIncludeTarget"
              :indeterminate="exportTargetIndeterminate"
              @change="(e) => toggleExportSide('target', !!(e?.target?.checked ?? e))"
            >
              目标表数据
            </a-checkbox>
            <span class="export-rows-count">已选 {{ exportTargetChecked.length }}/{{ exportTargetOptions.length }}</span>
          </div>
          <div class="export-rows-tools">
            <a-button size="small" @click="selectAllExportFields('target')">全选</a-button>
            <a-button size="small" @click="clearExportFields('target')">全不选</a-button>
          </div>
          <div class="export-rows-list">
            <a-checkbox-group v-model:value="exportTargetChecked" class="export-rows-group">
              <label
                v-for="item in exportTargetOptions"
                :key="item.value"
                class="export-rows-item"
              >
                <a-checkbox :value="item.value">{{ item.label }}</a-checkbox>
              </label>
            </a-checkbox-group>
            <div v-if="!exportTargetOptions.length" class="export-rows-empty">暂无可选目标字段</div>
          </div>
        </div>
      </div>
      <div class="export-rows-footer">
        <div class="export-rows-hint">
          将使用当前左右筛选条件；单次最多导出 50000 行/侧。
        </div>
        <div class="compare-field-actions">
          <a-button @click="exportRowsModalOpen = false">取消</a-button>
          <a-button type="primary" :loading="exportRowsSubmitting" @click="confirmExportRows">
            导出 Excel
          </a-button>
        </div>
      </div>
    </a-modal>

    <a-modal
      v-model:open="singleCompareModalOpen"
      title="指定单条对比"
      :width="960"
      :footer="null"
      destroy-on-close
      :maskClosable="false"
      @cancel="cancelSingleComparePicker"
    >
      <div class="alias-hint">
        分别搜索并选中源表、目标表各一条记录，系统将按勾选字段做字段级对比：匹配蓝线，不匹配红线。
      </div>
      <div class="single-compare-grid">
        <div class="single-compare-pane">
          <div class="single-compare-pane-title">源表单条</div>
          <a-input-search
            v-model:value="singleCompareSearch.source"
            placeholder="输入关键词搜索源表记录，回车查询"
            enter-button="搜索"
            :loading="singleCompareLoading.source"
            allow-clear
            @search="searchSingleCompareCandidates('source')"
          />
          <div class="single-compare-list">
            <div
              v-for="item in singleCompareCandidates.source"
              :key="item.key"
              class="single-compare-card"
              :class="{ selected: singleCompareSelected.source?.key === item.key }"
              @click="singleCompareSelected.source = item"
            >
              <div class="single-compare-card-title">{{ item.preview }}</div>
              <div class="single-compare-card-meta">行号 {{ item.index }}</div>
            </div>
            <div v-if="!singleCompareCandidates.source.length" class="single-compare-empty">
              {{ singleCompareSearched.source ? '暂无匹配记录' : '输入关键词搜索，或使用当前页记录' }}
            </div>
          </div>
        </div>
        <div class="single-compare-pane">
          <div class="single-compare-pane-title">目标表单条</div>
          <a-input-search
            v-model:value="singleCompareSearch.target"
            placeholder="输入关键词搜索目标表记录，回车查询"
            enter-button="搜索"
            :loading="singleCompareLoading.target"
            allow-clear
            @search="searchSingleCompareCandidates('target')"
          />
          <div class="single-compare-list">
            <div
              v-for="item in singleCompareCandidates.target"
              :key="item.key"
              class="single-compare-card"
              :class="{ selected: singleCompareSelected.target?.key === item.key }"
              @click="singleCompareSelected.target = item"
            >
              <div class="single-compare-card-title">{{ item.preview }}</div>
              <div class="single-compare-card-meta">行号 {{ item.index }}</div>
            </div>
            <div v-if="!singleCompareCandidates.target.length" class="single-compare-empty">
              {{ singleCompareSearched.target ? '暂无匹配记录' : '输入关键词搜索，或使用当前页记录' }}
            </div>
          </div>
        </div>
      </div>
      <div class="single-compare-footer">
        <a-checkbox v-model:checked="singleCompareFuzzy">模糊匹配字段值</a-checkbox>
        <div class="compare-field-actions">
          <a-button @click="cancelSingleComparePicker">取消</a-button>
          <a-button
            type="primary"
            :loading="singleCompareSubmitting"
            @click="confirmSingleCompare"
          >
            开始字段对比
          </a-button>
        </div>
      </div>
    </a-modal>
  </div>
</template>

<script setup>
import { computed, nextTick, onMounted, reactive, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import { message } from 'ant-design-vue'
import api from '../api'
import MappingCanvas from '../components/MappingCanvas.vue'

const props = defineProps({
  id: { type: [String, Number], required: true },
})

const router = useRouter()
const task = ref(null)
const current = ref(0)
const dbKeyword = reactive({ source: '', target: '' })
const sourceDbListRef = ref(null)
const targetDbListRef = ref(null)
const syncDbScroll = ref(false)
const rowPage = ref(1)
const rowPageSize = ref(100)
const hideMappedRows = ref(false)
const hasRowMatch = ref(false)
const unmatchedTotals = reactive({ source: 0, target: 0 })
const rowMatchedTotal = ref(null)
const searchTotals = reactive({ source: 0, target: 0 })
const rowSearchConditions = reactive({ source: [], target: [] })
const rowSearchLogic = reactive({ source: 'and', target: 'and' })

function normalizeSearchLogic(logic) {
  return String(logic || 'and').trim().toLowerCase() === 'or' ? 'or' : 'and'
}
const rowSearchByPair = reactive({})
const searchUiEpoch = ref(0)
let restoringContentMatch = false
const rowPageSizeOptions = [
  { value: 100, label: '100 条' },
  { value: 200, label: '200 条' },
  { value: 500, label: '500 条' },
  { value: 1000, label: '1000 条' },
]
let syncingDbScroll = false

function onDbScroll(side) {
  if (!syncDbScroll.value || syncingDbScroll) return
  const fromEl = side === 'source' ? sourceDbListRef.value : targetDbListRef.value
  const toEl = side === 'source' ? targetDbListRef.value : sourceDbListRef.value
  if (!fromEl || !toEl) return
  const fromMax = Math.max(0, fromEl.scrollHeight - fromEl.clientHeight)
  const toMax = Math.max(0, toEl.scrollHeight - toEl.clientHeight)
  syncingDbScroll = true
  toEl.scrollTop = fromMax <= 0 ? 0 : (fromEl.scrollTop / fromMax) * toMax
  requestAnimationFrame(() => {
    syncingDbScroll = false
  })
}
const databases = reactive({ source: [], target: [] })
const schemas = reactive({ source: [], target: [] })

const state = reactive({
  sourceDb: '',
  targetDb: '',
  sourceSchema: '',
  targetSchema: '',
  tableMappings: [],
  columnMappings: {},
  valueAliases: {},
  extractMatchRules: {},
  contentStats: {},
  contentCompareFields: {},
  sourceJoins: {},
  displayFields: {},
  currentTablePair: '',
  rowMappings: [],
})

const loading = reactive({
  sourceDb: false,
  targetDb: false,
  sourceTables: false,
  targetTables: false,
  sourceColumns: false,
  targetColumns: false,
  sourceRows: false,
  targetRows: false,
  next: false,
  finish: false,
})

const tableItems = reactive({ source: [], target: [] })
const columnItems = reactive({ source: [], target: [] })
const rowItems = reactive({ source: [], target: [] })
const rowTotals = reactive({ source: 0, target: 0 })
const aliasModalOpen = ref(false)
const aliasModalTab = ref('value')
const compareFieldsModalOpen = ref(false)
const compareFieldOptions = ref([])
const compareFieldChecked = ref([])
const compareFieldsSubmitting = ref(false)
let compareFieldsResolver = null
const singleCompareModalOpen = ref(false)
const singleCompareSubmitting = ref(false)
const singleCompareFuzzy = ref(false)
const singleCompareActive = ref(false)
const singleCompareFieldLinks = ref([])
const singleCompareStats = reactive({ match: 0, mismatch: 0 })
const singleCompareSearch = reactive({ source: '', target: '' })
const singleCompareLoading = reactive({ source: false, target: false })
const singleCompareSearched = reactive({ source: false, target: false })
const singleCompareCandidates = reactive({ source: [], target: [] })
const singleCompareSelected = reactive({ source: null, target: null })
const singleCompareColumns = ref([])
const exportRowsModalOpen = ref(false)
const exportRowsSubmitting = ref(false)
const exportSourceOptions = ref([])
const exportTargetOptions = ref([])
const exportSourceChecked = ref([])
const exportTargetChecked = ref([])
const aliasDraft = reactive({
  sourceField: undefined,
  sourceValue: '',
  targetField: undefined,
  targetValue: '',
})
const extractDraft = reactive({
  sourceField: undefined,
  sourcePositions: '',
  targetField: undefined,
  targetPositions: '',
})
const sourceValueOptions = ref([])
const targetValueOptions = ref([])
const aliasTableColumns = [
  { title: '对应规则', key: 'rule', dataIndex: 'rule' },
  { title: '操作', key: 'action', width: 80 },
]
const extractTableColumns = [
  { title: '提取规则', key: 'rule', dataIndex: 'rule' },
  { title: '操作', key: 'action', width: 80 },
]
const sourceColumnCache = reactive({})
const targetColumnOrderCache = reactive({})

const tablePairOptions = computed(() =>
  state.tableMappings.map((m) => ({
    value: `${m.source}::${m.target}`,
    label: `${m.source}  ↔  ${m.target}`,
  })),
)

function tableDisplayLabel(side, name) {
  if (!name) return '-'
  const item = (tableItems[side] || []).find((t) => t.key === name)
  const comment = item?.description?.trim()
  return comment ? `${name}（${comment}）` : name
}

const targetTableOptions = computed(() => {
  const seen = new Set()
  return state.tableMappings
    .filter((m) => m.target && !seen.has(m.target) && seen.add(m.target))
    .map((m) => ({ value: m.target, label: tableDisplayLabel('target', m.target) }))
})

const currentTargetTable = computed({
  get() {
    return (state.currentTablePair || '').split('::')[1] || undefined
  },
  set(target) {
    const sources = state.tableMappings.filter((m) => m.target === target).map((m) => m.source)
    const currentSource = (state.currentTablePair || '').split('::')[0] || ''
    const preferred = sources.includes(currentSource) ? currentSource : sources[0]
    state.currentTablePair = preferred && target ? `${preferred}::${target}` : ''
  },
})

const sourceTablesForTarget = computed(() =>
  state.tableMappings
    .filter((m) => m.target === currentTargetTable.value)
    .map((m) => m.source)
    .filter(Boolean),
)

const currentSourceTable = computed({
  get() {
    return (state.currentTablePair || '').split('::')[0] || undefined
  },
  set(source) {
    const target = currentTargetTable.value
    state.currentTablePair = source && target ? `${source}::${target}` : ''
  },
})

const columnLeftGroups = computed(() =>
  sourceTablesForTarget.value.map((name) => ({
    key: name,
    title: tableDisplayLabel('source', name),
    items: (sourceColumnCache[name] || []).map((item) => ({
      ...item,
      key: `${name}::${item.key}`,
      fieldKey: item.key,
      groupKey: name,
    })),
  })),
)

const allColumnMappingsForTarget = computed({
  get() {
    const target = currentTargetTable.value
    if (!target) return []
    const result = []
    for (const src of sourceTablesForTarget.value) {
      for (const m of state.columnMappings[`${src}::${target}`] || []) {
        result.push({ source: `${src}::${m.source}`, target: m.target })
      }
    }
    return result
  },
  set(mappings) {
    const target = currentTargetTable.value
    if (!target) return
    const byTable = Object.fromEntries(sourceTablesForTarget.value.map((name) => [name, []]))
    for (const m of mappings || []) {
      const sep = String(m.source).indexOf('::')
      if (sep < 0) continue
      const table = String(m.source).slice(0, sep)
      const field = String(m.source).slice(sep + 2)
      if (!byTable[table]) continue
      byTable[table].push({ source: field, target: m.target })
    }
    for (const src of sourceTablesForTarget.value) {
      state.columnMappings[`${src}::${target}`] = byTable[src] || []
    }
  },
})

const currentLeftJoins = computed({
  get() {
    const target = currentTargetTable.value
    if (!target) return []
    return (state.sourceJoins[target] || []).map((item) => ({
      source: `${item.leftTable}::${item.leftField}`,
      target: `${item.rightTable}::${item.rightField}`,
    }))
  },
  set(joins) {
    const target = currentTargetTable.value
    if (!target) return
    state.sourceJoins[target] = (joins || [])
      .map((m) => {
        const leftSep = String(m.source).indexOf('::')
        const rightSep = String(m.target).indexOf('::')
        if (leftSep < 0 || rightSep < 0) return null
        return {
          leftTable: String(m.source).slice(0, leftSep),
          leftField: String(m.source).slice(leftSep + 2),
          rightTable: String(m.target).slice(0, rightSep),
          rightField: String(m.target).slice(rightSep + 2),
        }
      })
      .filter(Boolean)
  },
})

const currentDisplaySelections = computed({
  get() {
    const target = currentTargetTable.value
    if (!target) return { left: [], right: [] }
    const saved = state.displayFields[target] || {}
    return {
      left: Array.isArray(saved.left) ? saved.left.slice() : [],
      right: Array.isArray(saved.right) ? saved.right.slice() : [],
    }
  },
  set(val) {
    const target = currentTargetTable.value
    if (!target) return
    state.displayFields = {
      ...state.displayFields,
      [target]: {
        left: Array.isArray(val?.left) ? val.left.slice() : [],
        right: Array.isArray(val?.right) ? val.right.slice() : [],
      },
    }
  },
})

let displayPersistTimer = 0
function onDisplaySelectionsPersist() {
  clearTimeout(displayPersistTimer)
  displayPersistTimer = window.setTimeout(() => {
    persist().catch(() => {})
  }, 280)
}

const contentPairOptions = computed(() => {
  const result = []
  const seen = new Set()
  for (const m of state.tableMappings) {
    const pairKey = `${m.source}::${m.target}`
    const hasCols = (state.columnMappings[pairKey] || []).length > 0
    if (!hasCols) continue
    if (seen.has(pairKey)) continue
    seen.add(pairKey)
    const joins = state.sourceJoins[m.target] || []
    const inJoin = joins.some((j) => j.leftTable === m.source || j.rightTable === m.source)
    result.push({
      value: pairKey,
      label: inJoin ? `${m.source} ↔ ${m.target}（跨表）` : `${m.source} ↔ ${m.target}`,
    })
  }
  return result
})

const contentTargetOptions = computed(() => {
  const seen = new Set()
  return contentPairOptions.value
    .map((item) => item.value.split('::')[1])
    .filter((target) => target && !seen.has(target) && seen.add(target))
    .map((target) => ({ value: target, label: tableDisplayLabel('target', target) }))
})

function sourcesWithColumnsForTarget(target) {
  if (!target) return []
  return state.tableMappings
    .filter((m) => m.target === target && (state.columnMappings[`${m.source}::${m.target}`] || []).length)
    .map((m) => m.source)
}

function tablesReachableFrom(start, joins) {
  const seen = new Set([start])
  const queue = [start]
  while (queue.length) {
    const table = queue.shift()
    for (const join of joins || []) {
      let other = null
      if (join.leftTable === table) other = join.rightTable
      else if (join.rightTable === table) other = join.leftTable
      if (other && !seen.has(other)) {
        seen.add(other)
        queue.push(other)
      }
    }
  }
  return seen
}

function pickPrimarySource(target) {
  const sources = sourcesWithColumnsForTarget(target)
  if (!sources.length) return ''
  const joins = state.sourceJoins[target] || []
  if (!joins.length) return sources.includes(target) ? target : sources[0]

  let best = sources[0]
  let bestScore = -1
  for (const cand of sources) {
    const reachable = tablesReachableFrom(cand, joins)
    const mappedReach = sources.filter((s) => reachable.has(s)).length
    const participates = joins.some((j) => j.leftTable === cand || j.rightTable === cand) ? 1 : 0
    const sameName = cand === target ? 1 : 0
    const leftPref = joins.some((j) => j.leftTable === cand) ? 0.5 : 0
    const score = mappedReach * 10 + participates * 5 + sameName * 2 + leftPref
    if (score > bestScore) {
      bestScore = score
      best = cand
    }
  }
  return best
}

function isCrossTableContent(target) {
  const joins = state.sourceJoins[target] || []
  if (!joins.length) return false
  const sources = sourcesWithColumnsForTarget(target)
  if (!sources.length) return false
  // Enable whenever a mapped source participates in a join (partner may be join-only).
  if (sources.length > 1) return true
  return joins.some((j) => sources.includes(j.leftTable) || sources.includes(j.rightTable))
}

function allTargetMappedCols(target, primary) {
  const merged = targetMappedColsForContent(target)
  if (merged.length) return merged
  return (state.columnMappings[`${primary}::${target}`] || []).map((m) => ({
    source: m.target,
    target: m.target,
  }))
}

const currentContentTarget = computed({
  get() {
    return (state.currentTablePair || '').split('::')[1] || undefined
  },
  set(target) {
    const primary = pickPrimarySource(target)
    state.currentTablePair = primary && target ? `${primary}::${target}` : ''
  },
})

const currentContentSource = computed(() => {
  const target = currentContentTarget.value
  if (target) {
    const primary = pickPrimarySource(target)
    if (primary) return primary
  }
  return (state.currentTablePair || '').split('::')[0] || ''
})

const currentColumnMappings = computed({
  get() {
    return state.columnMappings[state.currentTablePair] || []
  },
  set(val) {
    state.columnMappings[state.currentTablePair] = val
  },
})

function currentContentMatchColumns() {
  const target = currentContentTarget.value || currentPair().target
  const primary = pickPrimarySource(target) || currentPair().source
  if (!target || !primary) return []
  return buildContentMatchColumns(target, primary)
}

const sourceAliasFieldOptions = computed(() => {
  const seen = new Set()
  return currentContentMatchColumns()
    .filter((m) => m.source && m.target && !seen.has(m.source) && seen.add(m.source))
    .map((m) => ({ value: m.source, label: m.source }))
})

const targetAliasFieldOptions = computed(() => {
  const seen = new Set()
  return currentContentMatchColumns()
    .filter((m) => m.source && m.target && !seen.has(m.target) && seen.add(m.target))
    .map((m) => ({ value: m.target, label: m.target }))
})

const aliasFieldEmptyText = computed(() =>
  currentColumnMappings.value.length ? '无匹配字段' : '请先在上一步连线字段',
)

const rowSearchFieldOptions = computed(() => {
  const target = currentContentTarget.value || currentPair().target
  const primary = pickPrimarySource(target) || currentPair().source
  const sourceByTable = new Map()
  const targetOpts = []
  const sourceSeen = new Set()
  const targetSeen = new Set()

  const pushSource = (table, field) => {
    if (!field || !table) return
    // 主表字段保持裸名以兼容历史筛选；关联表用 table::field，避免重名冲突
    const value = table === primary ? field : `${table}::${field}`
    if (sourceSeen.has(value)) return
    sourceSeen.add(value)
    if (!sourceByTable.has(table)) sourceByTable.set(table, [])
    sourceByTable.get(table).push({ value, label: field })
  }
  const pushTarget = (field) => {
    if (!field || targetSeen.has(field)) return
    targetSeen.add(field)
    targetOpts.push({ value: field, label: field })
  }

  if (target && primary) {
    // 按源表列出已连线字段（不按目标字段去重，也不按内容对比勾选裁剪，避免漏表如 duty_catalog）
    const seenPair = new Set()
    for (const src of sourcesWithColumnsForTarget(target)) {
      for (const m of state.columnMappings[`${src}::${target}`] || []) {
        if (!m?.source) continue
        const key = `${src}::${m.source}`
        if (seenPair.has(key)) continue
        seenPair.add(key)
        pushSource(src, m.source)
        if (m.target) pushTarget(m.target)
      }
    }
    if (!sourceByTable.size) {
      for (const col of buildContentMatchColumns(target, primary)) {
        const table = col.source_table || primary
        for (const field of mappingSourceFields(col)) {
          pushSource(table, field)
        }
        if (col.target) pushTarget(col.target)
      }
    }
    if (!targetOpts.length) {
      for (const col of allTargetMappedCols(target, primary)) {
        pushTarget(col.target)
      }
    }
  }

  const display = state.displayFields[target] || {}
  for (const key of display.left || []) {
    const sep = String(key).indexOf('::')
    if (sep < 0) {
      pushSource(primary, key)
      continue
    }
    pushSource(String(key).slice(0, sep), String(key).slice(sep + 2))
  }
  for (const field of display.right || []) {
    pushTarget(field)
  }

  const tableOrder = []
  const seenTable = new Set()
  const pushTable = (name) => {
    if (!name || seenTable.has(name) || !sourceByTable.has(name)) return
    seenTable.add(name)
    tableOrder.push(name)
  }
  pushTable(primary)
  for (const name of sourcesWithColumnsForTarget(target)) pushTable(name)
  for (const name of sourceByTable.keys()) pushTable(name)

  const sourceOpts = tableOrder.map((table) => ({
    label: tableDisplayLabel('source', table) || table,
    options: sourceByTable.get(table) || [],
  }))

  return { source: sourceOpts, target: targetOpts }
})

const currentValueAliases = computed(() => state.valueAliases[state.currentTablePair] || [])
const currentExtractMatchRules = computed(
  () => state.extractMatchRules[state.currentTablePair] || [],
)
const aliasRuleTotal = computed(
  () => currentValueAliases.value.length + currentExtractMatchRules.value.length,
)
const aliasTableRows = computed(() =>
  currentValueAliases.value.map((item, index) => ({
    id: index,
    sourceField: item.sourceField,
    sourceValue: item.sourceValue,
    targetField: item.targetField,
    targetValue: item.targetValue,
  })),
)
const extractTableRows = computed(() =>
  currentExtractMatchRules.value.map((item, index) => ({
    id: index,
    sourceField: item.sourceField,
    sourcePositions: item.sourcePositions,
    targetField: item.targetField,
    targetPositions: item.targetPositions,
  })),
)

function hasRowSearchKeywords(side) {
  return (rowSearchConditions[side] || []).some(
    (cond) => Array.isArray(cond?.keywords) && cond.keywords.some((item) => String(item ?? '').trim()),
  )
}

const rowPageTotal = computed(() => {
  const sourceTotal = hasRowSearchKeywords('source')
    ? searchTotals.source
    : hideMappedRows.value
      ? unmatchedTotals.source
      : rowTotals.source
  const targetTotal = hasRowSearchKeywords('target')
    ? searchTotals.target
    : hideMappedRows.value
      ? unmatchedTotals.target
      : rowTotals.target
  return Math.max(sourceTotal || 0, targetTotal || 0)
})

function rowPageTotalText(total) {
  if (hasRowSearchKeywords('source') || hasRowSearchKeywords('target')) return `共 ${total} 行匹配`
  if (hideMappedRows.value) return `共 ${total} 行未配对`
  return `共 ${total} 行`
}

function formatDs(ds) {
  if (!ds) return '-'
  if ((ds.db_type || '').toLowerCase() === 'sqlite') {
    const path = ds.database || ''
    return `SQLITE ${path.split(/[/\\]/).pop()}`
  }
  const key = (ds.db_type || '').toLowerCase()
  const type = { dameng: '达梦', oceanbase: 'OceanBase', oracle: 'Oracle' }[key] || (ds.db_type || '').toUpperCase()
  return `${type} ${ds.host}:${ds.port}`
}

function goHome() {
  router.push({ name: 'tasks' })
}

function filteredDbs(side) {
  const kw = dbKeyword[side].trim().toLowerCase()
  return databases[side].filter((name) => !kw || name.toLowerCase().includes(kw))
}

function schemaOptions(side) {
  return schemas[side].map((s) => ({ value: s, label: s }))
}

async function loadTask() {
  task.value = await api.getTask(props.id)
  const saved = task.value.session_state
  if (saved) {
    Object.assign(state, {
      sourceDb: saved.sourceDb || '',
      targetDb: saved.targetDb || '',
      sourceSchema: saved.sourceSchema || '',
      targetSchema: saved.targetSchema || '',
      tableMappings: saved.tableMappings || [],
      columnMappings: saved.columnMappings || {},
      valueAliases: saved.valueAliases || {},
      extractMatchRules: saved.extractMatchRules || {},
      contentStats: saved.contentStats || {},
      contentCompareFields: saved.contentCompareFields || {},
      sourceJoins: saved.sourceJoins || {},
      displayFields: saved.displayFields || {},
      currentTablePair: saved.currentTablePair || '',
      rowMappings: [],
    })
    if (typeof saved.current === 'number') current.value = saved.current
    Object.keys(rowSearchByPair).forEach((key) => delete rowSearchByPair[key])
    Object.assign(rowSearchByPair, saved.rowSearchByPair || {})
  }
  hydratePersistedCompareFromReport(task.value?.report)
  restoreRowSearch(state.currentTablePair)
}

function normalizeSearchMode(mode, negate = false) {
  const value = String(mode || '').trim()
  if (['include', 'exclude', 'equals', 'not_equals'].includes(value)) return value
  return negate ? 'exclude' : 'include'
}

function cloneSearchConditions(list, fallbackLogic = 'and') {
  const fallback = normalizeSearchLogic(fallbackLogic)
  return (Array.isArray(list) ? list : [])
    .map((item, idx) => {
      const mode = normalizeSearchMode(item?.mode, item?.negate)
      return {
        field: String(item?.field || '').trim(),
        keywords: Array.isArray(item?.keywords)
          ? item.keywords.map((kw) => String(kw ?? '').trim()).filter(Boolean)
          : [],
        mode,
        negate: mode === 'exclude' || mode === 'not_equals',
        logic: idx === 0 ? 'and' : normalizeSearchLogic(item?.logic || fallback),
      }
    })
    .filter((item) => item.keywords.length)
}

function deriveSearchLogic(list) {
  const conditions = Array.isArray(list) ? list : []
  if (conditions.length <= 1) return 'and'
  const logics = conditions.slice(1).map((item) => normalizeSearchLogic(item.logic))
  if (logics.length && logics.every((item) => item === logics[0])) return logics[0]
  return logics[0] || 'and'
}

function rememberRowSearch(pairKey = state.currentTablePair) {
  if (!pairKey) return
  const source = cloneSearchConditions(rowSearchConditions.source, rowSearchLogic.source)
  const target = cloneSearchConditions(rowSearchConditions.target, rowSearchLogic.target)
  rowSearchByPair[pairKey] = {
    source,
    target,
    sourceLogic: deriveSearchLogic(source),
    targetLogic: deriveSearchLogic(target),
  }
}

function restoreRowSearch(pairKey = state.currentTablePair) {
  const saved = pairKey ? rowSearchByPair[pairKey] : null
  rowSearchConditions.source = cloneSearchConditions(saved?.source || [], saved?.sourceLogic)
  rowSearchConditions.target = cloneSearchConditions(saved?.target || [], saved?.targetLogic)
  rowSearchLogic.source = normalizeSearchLogic(saved?.sourceLogic || deriveSearchLogic(rowSearchConditions.source))
  rowSearchLogic.target = normalizeSearchLogic(saved?.targetLogic || deriveSearchLogic(rowSearchConditions.target))
  searchUiEpoch.value += 1
}

function hydratePersistedCompareFromReport(report) {
  if (!report?.tables?.length) return
  for (const table of report.tables) {
    const key = table.id
    if (!key) continue
    if (!rowSearchByPair[key] && (table.searchFilters?.source?.length || table.searchFilters?.target?.length)) {
      const source = cloneSearchConditions(
        table.searchFilters.source || [],
        table.searchFilters?.sourceLogic,
      )
      const target = cloneSearchConditions(
        table.searchFilters.target || [],
        table.searchFilters?.targetLogic,
      )
      rowSearchByPair[key] = {
        source,
        target,
        sourceLogic: normalizeSearchLogic(table.searchFilters?.sourceLogic || deriveSearchLogic(source)),
        targetLogic: normalizeSearchLogic(table.searchFilters?.targetLogic || deriveSearchLogic(target)),
      }
    }
    if (table.valueAliases?.length && !(state.valueAliases[key] || []).length) {
      state.valueAliases[key] = table.valueAliases.map((item) => ({
        sourceField: item.sourceField,
        sourceValue: item.sourceValue,
        targetField: item.targetField,
        targetValue: item.targetValue,
      }))
    }
    if (table.extractMatchRules?.length && !(state.extractMatchRules[key] || []).length) {
      state.extractMatchRules[key] = table.extractMatchRules.map((item) => ({
        sourceField: item.sourceField,
        sourcePositions: item.sourcePositions,
        targetField: item.targetField,
        targetPositions: item.targetPositions,
      }))
    }
    if (
      table.compared &&
      !state.contentStats[key] &&
      (table.statsMode === 'full' || table.statsMode === 'filtered')
    ) {
      state.contentStats[key] = {
        sourceTotal: table.sourceTotal ?? 0,
        targetTotal: table.targetTotal ?? 0,
        matched: table.matched ?? 0,
        leftOnly: table.leftOnly ?? 0,
        rightOnly: table.rightOnly ?? 0,
      }
    }
    if (table.compareFields?.length && !state.contentCompareFields[table.targetTable]?.selected?.length) {
      state.contentCompareFields[table.targetTable] = {
        selected: table.compareFields.map((field) => {
          if (field.sourceTable || field.source || field.target) {
            return `${field.sourceTable || ''}::${field.source || ''}->${field.target || ''}`
          }
          return field.label || ''
        }).filter(Boolean),
        fuzzy: !!table.compareFuzzy,
      }
    }
  }
}

function sessionPayload() {
  rememberRowSearch()
  return {
    current: current.value,
    sourceDb: state.sourceDb,
    targetDb: state.targetDb,
    sourceSchema: state.sourceSchema,
    targetSchema: state.targetSchema,
    tableMappings: state.tableMappings,
    columnMappings: state.columnMappings,
    valueAliases: state.valueAliases,
    extractMatchRules: state.extractMatchRules,
    contentStats: state.contentStats,
    contentCompareFields: state.contentCompareFields,
    sourceJoins: state.sourceJoins,
    displayFields: state.displayFields,
    currentTablePair: state.currentTablePair,
    rowSearchByPair: { ...rowSearchByPair },
  }
}

async function persist() {
  await api.updateTask(props.id, {
    session_state: sessionPayload(),
    status: 'in_progress',
  })
}

function rememberContentStats(pairKey, result) {
  if (!pairKey || !result) return
  state.contentStats[pairKey] = {
    sourceTotal: result.source_total ?? 0,
    targetTotal: result.target_total ?? 0,
    matched: result.matched ?? 0,
    leftOnly: result.left_only ?? 0,
    rightOnly: result.right_only ?? 0,
    filtered: !!result.filtered,
  }
}

function buildRowMatchConditions(side) {
  const conditions = Array.isArray(rowSearchConditions[side]) ? rowSearchConditions[side] : []
  return conditions
    .map((item, idx) => {
      const mode = normalizeSearchMode(item.mode, item.negate)
      return {
        search_columns: item.field ? [item.field] : [],
        keywords: Array.isArray(item.keywords)
          ? item.keywords.map((kw) => String(kw ?? '').trim()).filter(Boolean)
          : [],
        mode,
        negate: mode === 'exclude' || mode === 'not_equals',
        logic: idx === 0 ? 'and' : normalizeSearchLogic(item.logic || rowSearchLogic[side]),
      }
    })
    .filter((item) => item.keywords.length)
}

function rowMatchFilterPayload() {
  return {
    source_conditions: buildRowMatchConditions('source'),
    target_conditions: buildRowMatchConditions('target'),
    source_condition_logic: normalizeSearchLogic(rowSearchLogic.source),
    target_condition_logic: normalizeSearchLogic(rowSearchLogic.target),
  }
}

function hasActiveRowSearchFilters() {
  return buildRowMatchConditions('source').length > 0 || buildRowMatchConditions('target').length > 0
}

async function loadDatabases() {
  loading.sourceDb = true
  loading.targetDb = true
  try {
    const [s, t] = await Promise.all([
      api.databases(props.id, 'source'),
      api.databases(props.id, 'target'),
    ])
    databases.source = s.databases || []
    databases.target = t.databases || []
    if (!state.sourceDb && databases.source.length === 1) {
      await selectDb('source', databases.source[0])
    }
    if (!state.targetDb && databases.target.length === 1) {
      await selectDb('target', databases.target[0])
    }
  } finally {
    loading.sourceDb = false
    loading.targetDb = false
  }
}

function pruneTableMappingsToCatalog() {
  const sourceNames = new Set(tableItems.source.map((t) => t.key))
  const targetNames = new Set(tableItems.target.map((t) => t.key))
  const before = (state.tableMappings || []).length
  state.tableMappings = (state.tableMappings || []).filter(
    (m) => sourceNames.has(m.source) && targetNames.has(m.target),
  )
  return Math.max(0, before - state.tableMappings.length)
}

function clearColumnCaches(side = 'both') {
  if (side === 'source' || side === 'both') {
    for (const key of Object.keys(sourceColumnCache)) delete sourceColumnCache[key]
    columnItems.source = []
  }
  if (side === 'target' || side === 'both') {
    for (const key of Object.keys(targetColumnOrderCache)) delete targetColumnOrderCache[key]
    columnItems.target = []
  }
}

async function selectDb(side, name) {
  const prev = side === 'source' ? state.sourceDb : state.targetDb
  if (side === 'source') state.sourceDb = name
  else state.targetDb = name
  await loadSchemas(side, name)
  // 切换数据库后，旧库里的表映射/字段缓存会失效，需按新库目录清理
  if (prev && prev !== name && state.sourceDb && state.targetDb) {
    await loadTables()
    const removed = pruneTableMappingsToCatalog()
    clearColumnCaches(side)
    if (removed > 0) {
      message.info(`已切换数据库，清除了 ${removed} 条在新库中不存在的表映射`)
    }
    await persist()
  }
}

async function loadSchemas(side, database) {
  try {
    const res = await api.schemas(props.id, side, database)
    schemas[side] = res.schemas || []
    if (side === 'source') {
      if (!schemas.source.includes(state.sourceSchema)) {
        state.sourceSchema = schemas.source.includes('public') ? 'public' : schemas.source[0] || ''
      }
    } else if (!schemas.target.includes(state.targetSchema)) {
      state.targetSchema = schemas.target.includes('public') ? 'public' : schemas.target[0] || ''
    }
  } catch {
    schemas[side] = []
  }
}

async function onSchemaChange(side) {
  state.currentTablePair = ''
  columnItems.source = []
  columnItems.target = []
  await loadTables()
  pruneTableMappingsToCatalog()
  clearColumnCaches(side)
  await persist()
}

function toTableItem(table) {
  const tags = [table.table_type || 'TABLE']
  if (table.row_estimate != null) tags.push(`约 ${table.row_estimate} 行`)
  return {
    key: table.name,
    title: table.name,
    description: table.comment || '',
    tags,
  }
}

function formatSampleValue(value) {
  if (value === null || value === undefined) return 'NULL'
  const text = String(value)
  return text.length > 40 ? `${text.slice(0, 40)}…` : text
}

function samplesFromRows(rows, columnName, max = 5) {
  const seen = new Set()
  const out = []
  for (const row of rows || []) {
    if (!Object.prototype.hasOwnProperty.call(row, columnName)) continue
    const raw = row[columnName]
    const key = raw === null || raw === undefined ? '__NULL__' : String(raw)
    if (seen.has(key)) continue
    seen.add(key)
    out.push(formatSampleValue(raw))
    if (out.length >= max) break
  }
  return out
}

function toColumnItem(col, samples = []) {
  const tags = [col.column_type]
  if (col.key === 'PRI') tags.push('主键')
  if (!col.nullable) tags.push('非空')
  const comment = (col.comment || '').trim()
  return {
    key: col.name,
    title: col.name,
    description: comment || `默认值: ${col.default ?? 'NULL'}`,
    sample: samples.length ? samples.join(' / ') : '',
    tags,
  }
}

function mappingSourceFields(mapping) {
  if (Array.isArray(mapping?.sources) && mapping.sources.length) {
    return mapping.sources.filter(Boolean)
  }
  const name = String(mapping?.source || '')
  if (name.includes('+')) {
    const parts = name.split('+').map((p) => p.trim()).filter(Boolean)
    if (parts.length) return parts
  }
  return name ? [name] : []
}

function formatCompositeSourceValue(row, mapping) {
  const fields = mappingSourceFields(mapping)
  if (!fields.length) return 'NULL'
  return fields.map((field) => formatRowCell(row?.[field])).join('+')
}

function collapseManyToOneMappings(mappings, defaultTable = '') {
  const groups = new Map()
  const order = []
  for (const m of mappings || []) {
    if (!m?.source || !m?.target) continue
    const table = m.source_table || defaultTable || ''
    const key = `${table}::${m.target}`
    if (!groups.has(key)) {
      groups.set(key, {
        target: m.target,
        source_table: m.source_table || (defaultTable || undefined),
        sources: [],
      })
      order.push(key)
    }
    const group = groups.get(key)
    for (const field of mappingSourceFields(m)) {
      if (!group.sources.includes(field)) group.sources.push(field)
    }
  }
  return order.map((key) => {
    const group = groups.get(key)
    const source = group.sources.join('+')
    return {
      source,
      target: group.target,
      source_table: group.source_table,
      sources: group.sources.slice(),
    }
  })
}

function serializeMatchColumns(columns) {
  return (columns || []).map((m) => {
    const sources = mappingSourceFields(m)
    const payload = {
      source: m.source || sources.join('+'),
      target: m.target,
    }
    if (m.source_table) payload.source_table = m.source_table
    if (sources.length > 1) payload.source_fields = sources
    return payload
  })
}

function rowSignature(row, mappedCols, side) {
  if (mappedCols.length) {
    const picked = mappedCols.map((m) =>
      side === 'source' ? formatCompositeSourceValue(row, m) : formatRowCell(row[m.target]),
    )
    return JSON.stringify(picked)
  }
  if (Object.prototype.hasOwnProperty.call(row, 'id')) return `id:${row.id}`
  const keys = Object.keys(row).sort()
  return JSON.stringify(keys.map((k) => [k, row[k]]))
}

function formatRowCell(value) {
  if (value === null || value === undefined) return 'NULL'
  const text = String(value)
  return text === '' ? 'NULL' : text
}

function toRowItem(row, index, mappedCols, side, mapped = false, compareSelected = null) {
  const fields = mappedCols.map((m) => {
    const key = side === 'source' ? m.source : m.target
    const value = side === 'source' ? formatCompositeSourceValue(row, m) : formatRowCell(row[key])
    return {
      kind: 'field',
      field: key,
      label: key,
      value,
      text: `${key}=${value}`,
      unequal: false,
      compareMark: compareMarkForColumn(m, compareSelected),
    }
  })
  return {
    key: `row-${index}`,
    title: fields.map((f) => f.text).join('\n') || `第 ${index + 1} 行`,
    fieldLines: fields,
    lineCount: Math.max(fields.length, 1),
    matchValue: rowSignature(row, mappedCols, side),
    mapped,
  }
}

function toQualifiedSourceRowItem(index, fieldLines, matchValue, mapped = false) {
  const lines = (fieldLines || [])
    .map((line) => {
      if (!line) return null
      if (typeof line === 'object') {
        const value = line.value ?? ''
        const label = line.label ?? line.field ?? ''
        const text =
          line.text ||
          (line.table ? `${line.table}.${label}=${value}` : `${label}=${value}`)
        return {
          kind: line.kind || 'field',
          table: line.table || '',
          field: line.field || label,
          label,
          value,
          text,
          unequal: !!line.unequal,
          compareMark: line.compareMark === true || line.compareMark === false ? line.compareMark : null,
          displayOnly: !!line.displayOnly,
        }
      }
      return {
        kind: 'field',
        label: '',
        value: String(line),
        text: String(line),
        unequal: false,
        compareMark: null,
        displayOnly: false,
      }
    })
    .filter(Boolean)
  return {
    key: `row-${index}`,
    title: lines.map((l) => l.text).join('\n') || `第 ${index + 1} 行`,
    fieldLines: lines,
    lineCount: Math.max(lines.length, 1),
    matchValue,
    mapped,
  }
}

function targetMappedColsForContent(target) {
  const seen = new Set()
  const cols = []
  for (const src of sourcesWithColumnsForTarget(target)) {
    for (const m of state.columnMappings[`${src}::${target}`] || []) {
      if (!m.target || seen.has(m.target)) continue
      seen.add(m.target)
      cols.push({ source: m.target, target: m.target })
    }
  }
  return sortMappingsByTargetOrder(cols, target)
}

function buildContentMatchColumns(target, primary) {
  const cross = isCrossTableContent(target)
  let cols
  if (!cross) {
    cols = (state.columnMappings[`${primary}::${target}`] || []).map((m) => ({
      source: m.source,
      target: m.target,
      source_table: primary,
    }))
    cols = collapseManyToOneMappings(cols, primary)
  } else {
    cols = []
    for (const src of sourcesWithColumnsForTarget(target)) {
      for (const m of state.columnMappings[`${src}::${target}`] || []) {
        if (!m.target || !m.source) continue
        cols.push({ source: m.source, target: m.target, source_table: src })
      }
    }
    cols = collapseManyToOneMappings(cols)
  }
  return sortMappingsByTargetOrder(cols, target)
}

function targetColumnOrder(target) {
  if (!target) return []
  if (targetColumnOrderCache[target]?.length) return targetColumnOrderCache[target]
  if (columnItems.target.length && currentPair().target === target) {
    return columnItems.target.map((item) => item.key)
  }
  return []
}

function sortMappingsByTargetOrder(mappings, target) {
  const list = mappings || []
  if (!list.length) return []
  const order = targetColumnOrder(target)
  if (!order.length) return list.slice()
  const rank = new Map(order.map((name, index) => [name, index]))
  return list
    .map((item, index) => ({ item, index }))
    .sort((a, b) => {
      const ra = rank.has(a.item.target) ? rank.get(a.item.target) : Number.MAX_SAFE_INTEGER
      const rb = rank.has(b.item.target) ? rank.get(b.item.target) : Number.MAX_SAFE_INTEGER
      if (ra !== rb) return ra - rb
      return a.index - b.index
    })
    .map((entry) => entry.item)
}

function collectOrderedSourceMappings(target) {
  const cols = []
  for (const src of sourcesWithColumnsForTarget(target)) {
    for (const m of state.columnMappings[`${src}::${target}`] || []) {
      if (!m.target || !m.source) continue
      cols.push({ source: m.source, target: m.target, source_table: src })
    }
  }
  return sortMappingsByTargetOrder(collapseManyToOneMappings(cols), target)
}

function matchColumnKey(col) {
  return `${col.source_table || ''}::${col.source}->${col.target}`
}

function matchColumnLabel(col) {
  const sourceLabel = col.source || mappingSourceFields(col).join('+')
  const left = col.source_table ? `${col.source_table}.${sourceLabel}` : sourceLabel
  return `${left}  →  ${col.target}`
}

function isCompareFieldChecked(value) {
  return compareFieldChecked.value.includes(value)
}

function compareSelectedKeySet(target) {
  const saved = state.contentCompareFields[target]
  if (!saved?.selected?.length) return null
  return new Set(saved.selected)
}

function compareMarkForColumn(col, compareSelected) {
  if (!compareSelected) return null
  if (compareSelected.has(matchColumnKey(col))) return true
  for (const key of compareSelected) {
    if (col.target && key.endsWith(`->${col.target}`)) return true
    if (col.source && col.target) {
      const suffix = `::${col.source}->${col.target}`
      if (key === suffix || key.endsWith(suffix)) return true
    }
  }
  return false
}

function filterMatchColumns(cols, target) {
  const saved = state.contentCompareFields[target]
  if (!saved?.selected?.length) return cols
  const selected = new Set(saved.selected)
  const filtered = cols.filter((col) => selected.has(matchColumnKey(col)))
  return filtered.length ? filtered : cols
}

function resolveCompareFieldChecked(cols, target) {
  const allKeys = cols.map(matchColumnKey)
  const saved = state.contentCompareFields[target]
  if (!saved?.selected) return allKeys
  const selectedSet = new Set(saved.selected || [])
  const catalogSet = new Set(saved.catalog || [])
  const checked = allKeys.filter((key) => selectedSet.has(key) || !catalogSet.has(key))
  return checked.length ? checked : allKeys
}

function promptCompareFields(cols, target) {
  compareFieldOptions.value = cols.map((col) => ({
    value: matchColumnKey(col),
    label: matchColumnLabel(col),
    col,
  }))
  compareFieldChecked.value = resolveCompareFieldChecked(cols, target)
  compareFieldsModalOpen.value = true
  return new Promise((resolve) => {
    compareFieldsResolver = resolve
  })
}

function selectAllCompareFields() {
  compareFieldChecked.value = compareFieldOptions.value.map((item) => item.value)
}

function clearCompareFields() {
  compareFieldChecked.value = []
}

function invertCompareFields() {
  const set = new Set(compareFieldChecked.value)
  compareFieldChecked.value = compareFieldOptions.value
    .map((item) => item.value)
    .filter((key) => !set.has(key))
}

function cancelCompareFieldsModal() {
  if (!compareFieldsResolver) {
    compareFieldsModalOpen.value = false
    return
  }
  compareFieldsModalOpen.value = false
  const resolve = compareFieldsResolver
  compareFieldsResolver = null
  resolve(null)
}

function confirmCompareFieldsModal(fuzzy = false) {
  if (!compareFieldChecked.value.length) {
    message.warning('请至少勾选一个对比字段')
    return
  }
  const checked = new Set(compareFieldChecked.value)
  const selectedCols = compareFieldOptions.value
    .filter((item) => checked.has(item.value))
    .map((item) => item.col)
  const target = currentContentTarget.value || currentPair().target
  if (target) {
    state.contentCompareFields[target] = {
      selected: compareFieldChecked.value.slice(),
      catalog: compareFieldOptions.value.map((item) => item.value),
      fuzzy: !!fuzzy,
    }
  }
  compareFieldsModalOpen.value = false
  const resolve = compareFieldsResolver
  compareFieldsResolver = null
  resolve?.({ columns: selectedCols, fuzzy: !!fuzzy })
}

function persistCompareFieldSelection(fuzzy = false) {
  const checked = new Set(compareFieldChecked.value)
  const selectedCols = compareFieldOptions.value
    .filter((item) => checked.has(item.value))
    .map((item) => item.col)
  const target = currentContentTarget.value || currentPair().target
  if (target) {
    state.contentCompareFields[target] = {
      selected: compareFieldChecked.value.slice(),
      catalog: compareFieldOptions.value.map((item) => item.value),
      fuzzy: !!fuzzy,
    }
  }
  return selectedCols
}

function rowPreviewText(item) {
  if (!item) return ''
  const lines = (item.fieldLines || [])
    .filter((line) => lineMetaSafe(line).kind !== 'join')
    .slice(0, 4)
    .map((line) => {
      const meta = lineMetaSafe(line)
      return `${meta.label || meta.field || ''}=${formatRowCell(meta.value)}`
    })
  if (lines.length) return lines.join(' · ')
  return String(item.title || item.key || '')
}

function lineMetaSafe(line) {
  if (line && typeof line === 'object') {
    return {
      kind: line.kind || 'field',
      field: line.field || line.label || '',
      label: line.label || line.field || '',
      value: line.value,
      table: line.table || '',
    }
  }
  return { kind: 'field', field: '', label: '', value: line, table: '' }
}

function toSingleCompareCandidate(item) {
  const index = rowIndex(item.key)
  return {
    key: item.key,
    index,
    preview: rowPreviewText(item),
    item,
  }
}

function seedSingleCompareCandidates() {
  singleCompareCandidates.source = (rowItems.source || []).slice(0, 40).map(toSingleCompareCandidate)
  singleCompareCandidates.target = (rowItems.target || []).slice(0, 40).map(toSingleCompareCandidate)
  singleCompareSearched.source = false
  singleCompareSearched.target = false
  singleCompareSelected.source = null
  singleCompareSelected.target = null
  singleCompareSearch.source = ''
  singleCompareSearch.target = ''
}

function openSingleComparePicker() {
  if (!compareFieldChecked.value.length) {
    message.warning('请至少勾选一个对比字段')
    return
  }
  const target = currentContentTarget.value || currentPair().target
  singleCompareFuzzy.value = !!state.contentCompareFields[target]?.fuzzy
  const selectedCols = persistCompareFieldSelection(!!singleCompareFuzzy.value)
  singleCompareColumns.value = selectedCols
  compareFieldsModalOpen.value = false
  const resolve = compareFieldsResolver
  compareFieldsResolver = null
  resolve?.(null)
  seedSingleCompareCandidates()
  singleCompareModalOpen.value = true
}

function cancelSingleComparePicker() {
  singleCompareModalOpen.value = false
}

function normalizeCompareToken(value) {
  if (value === null || value === undefined) return ''
  const text = String(value).trim()
  if (!text || text.toUpperCase() === 'NULL') return ''
  return text
}

function splitCompareTokens(text) {
  const raw = normalizeCompareToken(text)
  if (!raw) return []
  try {
    const parsed = JSON.parse(raw)
    if (Array.isArray(parsed)) {
      return parsed.map((item) => normalizeCompareToken(item)).filter(Boolean).sort()
    }
  } catch {
    /* plain text */
  }
  return raw
    .split(/[,，;；|]/)
    .map((item) => item.trim())
    .filter(Boolean)
    .sort()
}

function aliasMakesEqual(sourceField, sourceVal, targetField, targetVal, aliases) {
  const sv = normalizeCompareToken(sourceVal)
  const tv = normalizeCompareToken(targetVal)
  for (const alias of aliases || []) {
    if (alias.sourceField !== sourceField || alias.targetField !== targetField) continue
    if (
      normalizeCompareToken(alias.sourceValue) === sv &&
      normalizeCompareToken(alias.targetValue) === tv
    ) {
      return true
    }
  }
  return false
}

function extractCharsByPositions(value, positions) {
  if (!positions?.length) return null
  // 空/NULL 按空串取位；其余保留原始字符（含小数点、加号等）
  const raw =
    value === null || value === undefined
      ? ''
      : String(value).trim().toUpperCase() === 'NULL'
        ? ''
        : String(value)
  const n = raw.length
  const chars = []
  for (const pos of positions) {
    let idx = -1
    if (pos > 0) idx = pos - 1
    else if (pos < 0) idx = n + pos
    else return null
    if (idx < 0 || idx >= n) return null
    chars.push(raw[idx])
  }
  return chars.join('')
}

function extractMakesEqual(sourceField, sourceVal, targetField, targetVal, extractRules) {
  const rules = (extractRules || []).filter(
    (item) => item.sourceField === sourceField && item.targetField === targetField,
  )
  if (!rules.length) return null
  for (const rule of rules) {
    const left = extractCharsByPositions(sourceVal, parsePositionSpec(rule.sourcePositions))
    const right = extractCharsByPositions(targetVal, parsePositionSpec(rule.targetPositions))
    if (left != null && right != null && left === right) return true
  }
  return false
}

function fieldValuesEqual(
  sourceField,
  sourceVal,
  targetField,
  targetVal,
  aliases,
  fuzzy,
  extractRules = [],
) {
  if (aliasMakesEqual(sourceField, sourceVal, targetField, targetVal, aliases)) return true
  const extracted = extractMakesEqual(
    sourceField,
    sourceVal,
    targetField,
    targetVal,
    extractRules,
  )
  if (extracted === true) return true
  if (extracted === false) {
    // 有提取规则但都未命中：仍允许整值相等或模糊兜底
  }
  const sv = normalizeCompareToken(sourceVal)
  const tv = normalizeCompareToken(targetVal)
  if (sv === tv) return true
  if (!fuzzy) return false
  const left = splitCompareTokens(sv)
  const right = splitCompareTokens(tv)
  if (!left.length && !right.length) return true
  if (left.length !== right.length) return false
  return left.every((item, idx) => item === right[idx])
}

function getSourceFieldValue(row, mapping, enrichedLines = []) {
  const fields = mappingSourceFields(mapping)
  const table = mapping.source_table || ''
  if (table && enrichedLines.length) {
    const hit = enrichedLines.find((line) => {
      const meta = lineMetaSafe(line)
      if (meta.kind === 'join' || meta.kind === 'display') return false
      const field = meta.field || meta.label
      return meta.table === table && (field === mapping.source || fields.includes(field))
    })
    if (hit) return lineMetaSafe(hit).value
  }
  if (fields.length > 1) return formatCompositeSourceValue(row, mapping)
  if (fields.length === 1) return row?.[fields[0]]
  return row?.[mapping.source]
}

async function searchSingleCompareCandidates(side) {
  const pair = currentPair()
  const target = pair.target
  const primary = pickPrimarySource(target) || pair.source
  if (!primary || !target) {
    message.warning('请先选择对比表对')
    return
  }
  const keyword = String(singleCompareSearch[side] || '').trim()
  if (!keyword) {
    seedSingleCompareCandidates()
    if (side === 'source') singleCompareSelected.source = null
    else singleCompareSelected.target = null
    return
  }
  const mappedCols =
    side === 'source'
      ? buildContentMatchColumns(target, primary)
      : allTargetMappedCols(target, primary)
  singleCompareLoading[side] = true
  try {
    const database = side === 'source' ? state.sourceDb : state.targetDb
    const table = side === 'source' ? primary : target
    const schemaName = side === 'source' ? state.sourceSchema : state.targetSchema
    const columns =
      side === 'source'
        ? [
            ...new Set(
              mappedCols
                .filter((item) => !item.source_table || item.source_table === table)
                .flatMap((item) => mappingSourceFields(item)),
            ),
          ]
        : [...new Set(mappedCols.map((item) => item.target).filter(Boolean))]
    const result = await api.searchRows(props.id, {
      ...rowPairPayload(),
      side,
      database,
      table,
      schema_name: schemaName || undefined,
      columns,
      conditions: [
        {
          search_columns: columns,
          keywords: [keyword],
          mode: 'include',
          negate: false,
          logic: 'and',
        },
      ],
      condition_logic: 'and',
      offset: 0,
      limit: 30,
      source_joins: side === 'source' ? buildContentMatchJoins(target) : [],
    })
    const rows = result.rows || []
    const indices = result.indices || []
    const compareSelected = new Set(singleCompareColumns.value.map((col) => matchColumnKey(col)))
    singleCompareCandidates[side] = rows.map((row, i) => {
      const index = indices[i] ?? i
      const item =
        side === 'source'
          ? toRowItem(row, index, mappedCols, 'source', false, compareSelected)
          : toRowItem(row, index, mappedCols, 'target', false, compareSelected)
      return toSingleCompareCandidate(item)
    })
    singleCompareSearched[side] = true
    if (side === 'source') singleCompareSelected.source = null
    else singleCompareSelected.target = null
  } catch (err) {
    message.error(err?.response?.data?.detail || err?.message || '搜索失败')
  } finally {
    singleCompareLoading[side] = false
  }
}

async function confirmSingleCompare() {
  if (!singleCompareSelected.source || !singleCompareSelected.target) {
    message.warning('请分别选择源表和目标表各一条记录')
    return
  }
  const cols = singleCompareColumns.value
  if (!cols.length) {
    message.warning('请先勾选对比字段')
    return
  }
  const pair = currentPair()
  const target = pair.target
  const primary = pickPrimarySource(target) || pair.source
  if (!primary || !target) {
    message.warning('请先选择对比表对')
    return
  }
  singleCompareSubmitting.value = true
  try {
    const sourceIndex = singleCompareSelected.source.index
    const targetIndex = singleCompareSelected.target.index
    const [sourcePack, targetPack] = await Promise.all([
      api.rowsByIndices(props.id, {
        side: 'source',
        database: state.sourceDb,
        table: primary,
        schema_name: state.sourceSchema || undefined,
        indices: [sourceIndex],
      }),
      api.rowsByIndices(props.id, {
        side: 'target',
        database: state.targetDb,
        table: target,
        schema_name: state.targetSchema || undefined,
        indices: [targetIndex],
      }),
    ])
    const sourceRow = (sourcePack.rows || [])[0]
    const targetRow = (targetPack.rows || [])[0]
    if (!sourceRow || !targetRow) {
      message.error('未能加载所选记录')
      return
    }

    const joins = state.sourceJoins[target] || []
    const enrichSource =
      isCrossTableContent(target) || joins.some((j) => j.leftTable === primary || j.rightTable === primary)
    if (enrichSource) {
      await loadPartnerIndexesMultiHop(primary, [sourceRow], joins)
    }

    const compareSelected = new Set(cols.map((col) => matchColumnKey(col)))
    const aliases = currentValueAliases.value || []
    const extractRules = currentExtractMatchRules.value || []
    const fuzzy = !!singleCompareFuzzy.value
    let sourceItem
    if (enrichSource) {
      const fieldLines = enrichSourceLinesWithJoins(primary, sourceRow, target, joins, compareSelected)
      sourceItem = toQualifiedSourceRowItem(
        sourceIndex,
        fieldLines,
        rowSignature(sourceRow, cols, 'source'),
      )
    } else {
      sourceItem = toRowItem(sourceRow, sourceIndex, cols, 'source', true, compareSelected)
    }
    const targetItem = toRowItem(targetRow, targetIndex, cols, 'target', true, compareSelected)

    // 只保留勾选字段，便于字段级连线一一对应
    const sourceLines = []
    const targetLines = []
    const fieldLinks = []
    let match = 0
    let mismatch = 0
    for (const col of cols) {
      const sourceVal = getSourceFieldValue(sourceRow, col, sourceItem.fieldLines || [])
      const targetVal = targetRow?.[col.target]
      const sourceFieldKey = col.source || mappingSourceFields(col).join('+')
      const equal = fieldValuesEqual(
        sourceFieldKey,
        sourceVal,
        col.target,
        targetVal,
        aliases,
        fuzzy,
        extractRules,
      )
      const sourceLabel = matchColumnLabel(col).split(' → ')[0] || col.source
      const targetLabel = col.target
      sourceLines.push({
        kind: 'field',
        table: col.source_table || primary,
        field: mappingSourceFields(col).join('+') || col.source,
        label: sourceLabel.includes('.') ? sourceLabel.split('.').pop() : sourceLabel,
        value: formatRowCell(sourceVal),
        text: `${sourceLabel}=${formatRowCell(sourceVal)}`,
        unequal: !equal,
        compareMark: true,
      })
      targetLines.push({
        kind: 'field',
        field: col.target,
        label: targetLabel,
        value: formatRowCell(targetVal),
        text: `${targetLabel}=${formatRowCell(targetVal)}`,
        unequal: !equal,
        compareMark: true,
      })
      fieldLinks.push({
        source: `row-${sourceIndex}`,
        target: `row-${targetIndex}`,
        sourceLine: sourceLines.length - 1,
        targetLine: targetLines.length - 1,
        equal,
      })
      if (equal) match += 1
      else mismatch += 1
    }

    sourceItem = {
      ...sourceItem,
      key: `row-${sourceIndex}`,
      fieldLines: sourceLines,
      lineCount: Math.max(sourceLines.length, 1),
      title: sourceLines.map((f) => f.text).join('\n'),
      mapped: true,
    }
    const targetBuilt = {
      ...targetItem,
      key: `row-${targetIndex}`,
      fieldLines: targetLines,
      lineCount: Math.max(targetLines.length, 1),
      title: targetLines.map((f) => f.text).join('\n'),
      mapped: true,
    }

    singleCompareActive.value = true
    singleCompareFieldLinks.value = fieldLinks
    singleCompareStats.match = match
    singleCompareStats.mismatch = mismatch
    rowItems.source = [sourceItem]
    rowItems.target = [targetBuilt]
    rowTotals.source = 1
    rowTotals.target = 1
    searchTotals.source = 1
    searchTotals.target = 1
    state.rowMappings = [{ source: sourceItem.key, target: targetBuilt.key }]
    hasRowMatch.value = true
    rowMatchedTotal.value = 1
    // 避免 hideMapped 变更触发 loadRows，把刚进入的单条模式清掉
    if (hideMappedRows.value) {
      skipHideReload = true
      hideMappedRows.value = false
      await nextTick()
      skipHideReload = false
    }
    singleCompareModalOpen.value = false
    if (target) {
      state.contentCompareFields[target] = {
        ...(state.contentCompareFields[target] || {}),
        selected: cols.map((col) => matchColumnKey(col)),
        fuzzy,
      }
    }
    await nextTick()
    await nextTick()
    message.success(`单条对比完成：匹配 ${match}，不匹配 ${mismatch}`)
  } catch (err) {
    message.error(err?.response?.data?.detail || err?.message || '单条对比失败')
  } finally {
    singleCompareSubmitting.value = false
  }
}

function exitSingleCompare() {
  clearSingleCompareState()
  loadRows({ restoreMatch: false })
}

function clearSingleCompareState() {
  singleCompareActive.value = false
  singleCompareFieldLinks.value = []
  singleCompareStats.match = 0
  singleCompareStats.mismatch = 0
}

function flattenExportFieldOptions(options) {
  const result = []
  for (const item of options || []) {
    if (Array.isArray(item?.options)) {
      const group = item.label || ''
      for (const child of item.options) {
        if (!child?.value) continue
        result.push({
          value: child.value,
          label: group ? `${group}.${child.label || child.value}` : child.label || child.value,
        })
      }
    } else if (item?.value) {
      result.push({ value: item.value, label: item.label || item.value })
    }
  }
  return result
}

const exportIncludeSource = computed(
  () =>
    !!exportSourceOptions.value.length &&
    exportSourceChecked.value.length === exportSourceOptions.value.length,
)
const exportIncludeTarget = computed(
  () =>
    !!exportTargetOptions.value.length &&
    exportTargetChecked.value.length === exportTargetOptions.value.length,
)
const exportSourceIndeterminate = computed(() => {
  const n = exportSourceChecked.value.length
  return n > 0 && n < exportSourceOptions.value.length
})
const exportTargetIndeterminate = computed(() => {
  const n = exportTargetChecked.value.length
  return n > 0 && n < exportTargetOptions.value.length
})

function openExportRowsModal() {
  const sourceOpts = flattenExportFieldOptions(rowSearchFieldOptions.value.source)
  const targetOpts = flattenExportFieldOptions(rowSearchFieldOptions.value.target)
  if (!sourceOpts.length && !targetOpts.length) {
    message.warning('请先连线字段后再导出')
    return
  }
  exportSourceOptions.value = sourceOpts
  exportTargetOptions.value = targetOpts
  // 默认勾选当前内容对比已选字段；没有则全选
  const target = currentContentTarget.value || currentPair().target
  const selected = state.contentCompareFields[target]?.selected || []
  if (selected.length) {
    const selectedSet = new Set(selected.map(String))
    exportSourceChecked.value = sourceOpts
      .filter((opt) => {
        const bare = String(opt.value).includes('::') ? String(opt.value).split('::').pop() : opt.value
        return (
          selectedSet.has(String(opt.value)) ||
          [...selectedSet].some((key) => key === bare || key.endsWith(`→${bare}`) || key.includes(bare))
        )
      })
      .map((o) => o.value)
    exportTargetChecked.value = targetOpts
      .filter((opt) =>
        [...selectedSet].some(
          (key) => key === opt.value || key.endsWith(opt.value) || key.includes(`→  ${opt.value}`) || key.includes(`→${opt.value}`),
        ),
      )
      .map((o) => o.value)
    if (!exportSourceChecked.value.length) exportSourceChecked.value = sourceOpts.map((o) => o.value)
    if (!exportTargetChecked.value.length) exportTargetChecked.value = targetOpts.map((o) => o.value)
  } else {
    exportSourceChecked.value = sourceOpts.map((o) => o.value)
    exportTargetChecked.value = targetOpts.map((o) => o.value)
  }
  exportRowsModalOpen.value = true
}

function selectAllExportFields(side) {
  if (side === 'source') exportSourceChecked.value = exportSourceOptions.value.map((o) => o.value)
  else exportTargetChecked.value = exportTargetOptions.value.map((o) => o.value)
}

function clearExportFields(side) {
  if (side === 'source') exportSourceChecked.value = []
  else exportTargetChecked.value = []
}

function toggleExportSide(side, checked) {
  if (checked) selectAllExportFields(side)
  else clearExportFields(side)
}

function serializeExportConditions(side) {
  const conditions = Array.isArray(rowSearchConditions[side]) ? rowSearchConditions[side] : []
  return conditions
    .map((item, idx) => {
      const mode = normalizeSearchMode(item.mode, item.negate)
      const keywords = Array.isArray(item.keywords)
        ? item.keywords.map((kw) => String(kw ?? '').trim()).filter(Boolean)
        : []
      if (!keywords.length) return null
      return {
        search_columns: item.field ? [item.field] : [],
        keywords,
        mode,
        negate: mode === 'exclude' || mode === 'not_equals',
        logic: idx === 0 ? 'and' : normalizeSearchLogic(item.logic || rowSearchLogic[side]),
      }
    })
    .filter(Boolean)
}

function downloadBlobFile(blob, filename) {
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = filename
  document.body.appendChild(a)
  a.click()
  a.remove()
  URL.revokeObjectURL(url)
}

async function confirmExportRows() {
  const sourceColumns = exportSourceChecked.value.slice()
  const targetColumns = exportTargetChecked.value.slice()
  if (!sourceColumns.length && !targetColumns.length) {
    message.warning('请至少勾选一侧要导出的字段')
    return
  }
  const pair = currentPair()
  const target = pair.target
  const primary = pickPrimarySource(target) || pair.source
  if (!primary || !target) {
    message.warning('请先选择对比表对')
    return
  }
  exportRowsSubmitting.value = true
  try {
    const result = await api.exportRows(props.id, {
      source_database: state.sourceDb,
      target_database: state.targetDb,
      source_table: primary,
      target_table: target,
      source_schema: state.sourceSchema || undefined,
      target_schema: state.targetSchema || undefined,
      source_columns: sourceColumns,
      target_columns: targetColumns,
      source_conditions: serializeExportConditions('source'),
      target_conditions: serializeExportConditions('target'),
      source_condition_logic: normalizeSearchLogic(rowSearchLogic.source),
      target_condition_logic: normalizeSearchLogic(rowSearchLogic.target),
      source_joins: buildContentMatchJoins(target),
      unmatched_only: !!(hideMappedRows.value && hasRowMatch.value),
      limit: 50000,
    })
    const blob = result instanceof Blob ? result : new Blob([result])
    // axios may return error json as blob
    if (blob.type && blob.type.includes('application/json')) {
      const text = await blob.text()
      let detail = '导出失败'
      try {
        detail = JSON.parse(text)?.detail || detail
      } catch {
        /* ignore */
      }
      throw new Error(detail)
    }
    const filename = `字段内容导出_${primary}_${target}.xlsx`
    downloadBlobFile(blob, filename)
    exportRowsModalOpen.value = false
    message.success('导出完成')
  } catch (err) {
    let detail = err?.message || '导出失败'
    const data = err?.response?.data
    if (data instanceof Blob) {
      try {
        const parsed = JSON.parse(await data.text())
        detail = parsed?.detail || detail
      } catch {
        /* ignore */
      }
    } else if (data?.detail) {
      detail = Array.isArray(data.detail)
        ? data.detail.map((d) => d.msg || d).join('; ')
        : data.detail
    }
    // 全局拦截器可能已提示过；这里保证有可读信息
    if (!String(detail).includes('[object')) message.error(String(detail))
  } finally {
    exportRowsSubmitting.value = false
  }
}

function buildContentMatchJoins(target) {
  return (state.sourceJoins[target] || []).map((j) => ({
    left_table: j.leftTable,
    left_field: j.leftField,
    right_table: j.rightTable,
    right_field: j.rightField,
  }))
}

function joinColumnsForTable(table, target = currentPair().target) {
  const fields = new Set()
  for (const join of state.sourceJoins[target] || []) {
    if (join.leftTable === table && join.leftField) fields.add(join.leftField)
    if (join.rightTable === table && join.rightField) fields.add(join.rightField)
  }
  return [...fields]
}

function sourceColumnOrder(table) {
  if (!table) return []
  const cached = sourceColumnCache[table]
  if (Array.isArray(cached) && cached.length) return cached.map((item) => item.key)
  if (columnItems.source.length && currentPair().source === table) {
    return columnItems.source.map((item) => item.key)
  }
  return []
}

function sourceTableRankMap(target, primary) {
  const tables = []
  const seen = new Set()
  const push = (name) => {
    if (!name || seen.has(name)) return
    seen.add(name)
    tables.push(name)
  }
  push(primary)
  for (const name of sourcesWithColumnsForTarget(target)) push(name)
  const saved = state.displayFields[target] || {}
  for (const key of saved.left || []) {
    const sep = String(key).indexOf('::')
    if (sep > 0) push(String(key).slice(0, sep))
  }
  return new Map(tables.map((name, index) => [name, index]))
}

function fieldLineOrderKey(side, line, primary, target) {
  if (side === 'target') {
    const order = targetColumnOrder(target)
    const field = line.field || line.label
    const idx = order.indexOf(field)
    return idx >= 0 ? idx : Number.MAX_SAFE_INTEGER
  }
  const table = line.table || primary
  const tableRank = sourceTableRankMap(target, primary)
  const tableIdx = tableRank.has(table) ? tableRank.get(table) : Number.MAX_SAFE_INTEGER
  const colOrder = sourceColumnOrder(table)
  const field = line.field || line.label
  const colIdx = colOrder.indexOf(field)
  const within = colIdx >= 0 ? colIdx : Number.MAX_SAFE_INTEGER
  return tableIdx * 100000 + within
}

function sortFieldLinesByTableOrder(side, lines, primary, target) {
  const list = Array.isArray(lines) ? lines : []
  const fields = []
  const joins = []
  list.forEach((line, index) => {
    if (line?.kind === 'join') joins.push({ line, index })
    else fields.push({ line, index })
  })
  fields.sort((a, b) => {
    const ra = fieldLineOrderKey(side, a.line, primary, target)
    const rb = fieldLineOrderKey(side, b.line, primary, target)
    if (ra !== rb) return ra - rb
    return a.index - b.index
  })
  return [...fields.map((entry) => entry.line), ...joins.map((entry) => entry.line)]
}

function insertSoloLinesByTableOrder(side, base, extras, primary, target) {
  if (!extras.length) {
    if (side === 'target') return sortFieldLinesByTableOrder(side, base, primary, target)
    return base
  }
  if (side === 'target') {
    return sortFieldLinesByTableOrder(side, [...base, ...extras], primary, target)
  }

  const joins = []
  const fields = []
  for (const line of base) {
    if (line?.kind === 'join') joins.push(line)
    else fields.push(line)
  }

  for (const extra of extras) {
    const table = extra.table || primary
    const colOrder = sourceColumnOrder(table)
    const extraRank = colOrder.indexOf(extra.field || extra.label)
    let insertAt = fields.length
    let inBlock = false
    for (let i = 0; i < fields.length; i += 1) {
      const lineTable = fields[i].table || primary
      if (lineTable !== table) {
        if (inBlock) {
          insertAt = i
          break
        }
        continue
      }
      inBlock = true
      const lineRank = colOrder.indexOf(fields[i].field || fields[i].label)
      if (extraRank >= 0 && (lineRank < 0 || extraRank < lineRank)) {
        insertAt = i
        break
      }
      insertAt = i + 1
    }
    fields.splice(insertAt, 0, extra)
  }
  return [...fields, ...joins]
}

function appendSoloDisplayLines(side, fieldLines, row, primary, target, rowsByTable = null) {
  const saved = state.displayFields[target] || {}
  const keys = side === 'source' ? saved.left || [] : saved.right || []
  const base = Array.isArray(fieldLines) ? fieldLines.slice() : []
  if (!keys.length) {
    return side === 'target' ? sortFieldLinesByTableOrder(side, base, primary, target) : base
  }

  const existing = new Set(
    base
      .filter((line) => line && line.kind !== 'join')
      .map((line) => {
        if (side === 'source') return `${line.table || primary}::${line.field || line.label}`
        return line.field || line.label
      }),
  )

  const extras = []
  for (const key of keys) {
    if (side === 'source') {
      if (existing.has(key)) continue
      const sep = String(key).indexOf('::')
      if (sep < 0) continue
      const table = String(key).slice(0, sep)
      const field = String(key).slice(sep + 2)
      const tableRows = rowsForTable(rowsByTable, table)
      const fallbackRows = table === primary && row ? [row] : []
      const sourceRows = tableRows.length ? tableRows : fallbackRows
      if (!sourceRows.length) continue
      const value = formatMultiJoinValues(sourceRows.map((item) => item?.[field]))
      extras.push({
        kind: 'field',
        table,
        field,
        label: field,
        value,
        text: `${table}.${field}=${value}`,
        unequal: false,
        compareMark: null,
        displayOnly: true,
      })
    } else {
      if (existing.has(key)) continue
      const value = formatRowCell(row?.[key])
      extras.push({
        kind: 'field',
        field: key,
        label: key,
        value,
        text: `${key}=${value}`,
        unequal: false,
        compareMark: null,
        displayOnly: true,
      })
    }
  }
  return insertSoloLinesByTableOrder(side, base, extras, primary, target)
}

function joinKey(value) {
  return value === null || value === undefined ? '__NULL__' : String(value)
}

function valuesEqualForJoin(a, b) {
  if (a === null || a === undefined) return b === null || b === undefined
  if (b === null || b === undefined) return false
  return String(a) === String(b)
}

function toValueOption(value) {
  if (value === null || value === undefined) return { value: '', label: '(空/NULL)' }
  const text = String(value)
  if (!text) return { value: '', label: '(空)' }
  return { value: text, label: text }
}

function formatAliasValue(value) {
  const text = String(value ?? '')
  return text === '' ? '(空)' : text
}

function serializeValueAliases(list) {
  return (list || []).map((item) => ({
    source_field: item.sourceField,
    source_value: item.sourceValue,
    target_field: item.targetField,
    target_value: item.targetValue,
  }))
}

function serializeExtractMatchRules(list) {
  return (list || []).map((item) => ({
    source_field: item.sourceField,
    source_positions: item.sourcePositions,
    target_field: item.targetField,
    target_positions: item.targetPositions,
  }))
}

const partnerIndexCache = reactive({})

async function openAliasModal() {
  if (!state.currentTablePair) {
    message.warning('请先选择对比表对')
    return
  }
  if (!columnItems.source.length || !columnItems.target.length) await loadColumns()
  if (!currentColumnMappings.value.length) {
    message.warning('请先在上一步为字段连线，再设置值对应关系')
    return
  }
  aliasDraft.sourceField = undefined
  aliasDraft.sourceValue = ''
  aliasDraft.targetField = undefined
  aliasDraft.targetValue = ''
  extractDraft.sourceField = undefined
  extractDraft.sourcePositions = ''
  extractDraft.targetField = undefined
  extractDraft.targetPositions = ''
  sourceValueOptions.value = []
  targetValueOptions.value = []
  aliasModalTab.value = 'value'
  aliasModalOpen.value = true
}

async function loadAliasValueOptions(side, field) {
  const pair = currentPair()
  if (!field || !pair.source || !pair.target) {
    if (side === 'source') sourceValueOptions.value = []
    else targetValueOptions.value = []
    return
  }
  const database = side === 'source' ? state.sourceDb : state.targetDb
  const table = side === 'source' ? pair.source : pair.target
  const schemaName = side === 'source' ? state.sourceSchema : state.targetSchema
  try {
    if (side === 'source' && String(field).includes('+')) {
      const fields = String(field)
        .split('+')
        .map((p) => p.trim())
        .filter(Boolean)
      const rowsResult = await api.rows(
        props.id,
        'source',
        database,
        table,
        schemaName || undefined,
        80,
        0,
      )
      const seen = new Set()
      const options = []
      for (const row of rowsResult.rows || []) {
        const value = fields.every((name) => row?.[name] == null || row?.[name] === '')
          ? ''
          : fields.map((name) => (row?.[name] == null ? '' : String(row[name]))).join('+')
        if (seen.has(value)) continue
        seen.add(value)
        options.push(toValueOption(value))
        if (options.length >= 40) break
      }
      sourceValueOptions.value = options
      return
    }
    const result = await api.values(props.id, side, database, table, field, schemaName || undefined)
    const options = (result.values || []).map(toValueOption)
    if (side === 'source') sourceValueOptions.value = options
    else targetValueOptions.value = options
  } catch {
    if (side === 'source') sourceValueOptions.value = []
    else targetValueOptions.value = []
  }
}

async function onAliasFieldChange(side) {
  if (side === 'source') {
    aliasDraft.sourceValue = ''
    const field = aliasDraft.sourceField
    if (!field) {
      sourceValueOptions.value = []
      return
    }
    const mapping = currentContentMatchColumns().find((m) => m.source === field)
    if (mapping?.target) {
      aliasDraft.targetField = mapping.target
      aliasDraft.targetValue = ''
      await Promise.all([
        loadAliasValueOptions('source', field),
        loadAliasValueOptions('target', mapping.target),
      ])
      return
    }
    await loadAliasValueOptions('source', field)
    return
  }

  aliasDraft.targetValue = ''
  const field = aliasDraft.targetField
  if (!field) {
    targetValueOptions.value = []
    return
  }
  const mapping = currentContentMatchColumns().find((m) => m.target === field)
  if (mapping?.source) {
    aliasDraft.sourceField = mapping.source
    aliasDraft.sourceValue = ''
    await Promise.all([
      loadAliasValueOptions('target', field),
      loadAliasValueOptions('source', mapping.source),
    ])
    return
  }
  await loadAliasValueOptions('target', field)
}

async function addValueAlias() {
  const sourceField = String(aliasDraft.sourceField || '').trim()
  const sourceValue = String(aliasDraft.sourceValue ?? '').trim()
  const targetField = String(aliasDraft.targetField || '').trim()
  const targetValue = String(aliasDraft.targetValue ?? '').trim()
  if (!sourceField || !targetField) {
    message.warning('请选择左右字段')
    return
  }
  const linked = currentContentMatchColumns().some(
    (m) => m.source === sourceField && m.target === targetField,
  )
  if (!linked) {
    message.warning('只能为上一步已连线的字段设置值对应关系')
    return
  }
  const next = [...currentValueAliases.value]
  const exists = next.some(
    (item) =>
      item.sourceField === sourceField &&
      item.sourceValue === sourceValue &&
      item.targetField === targetField &&
      item.targetValue === targetValue,
  )
  if (exists) {
    message.warning('这条对应关系已存在')
    return
  }
  next.push({ sourceField, sourceValue, targetField, targetValue })
  state.valueAliases[state.currentTablePair] = next
  aliasDraft.sourceValue = ''
  aliasDraft.targetValue = ''
  await persist()
  message.success(
    `已添加 ${sourceField}:${formatAliasValue(sourceValue)} = ${targetField}:${formatAliasValue(targetValue)}`,
  )
}

async function removeValueAlias(index) {
  const next = currentValueAliases.value.filter((_, i) => i !== index)
  state.valueAliases[state.currentTablePair] = next
  await persist()
}

function parsePositionSpec(spec) {
  const text = String(spec ?? '').trim()
  if (!text) return []
  if (/[,，\s;；、]/.test(text)) {
    const parts = text.split(/[,，\s;；、]+/).map((p) => p.trim()).filter(Boolean)
    if (!parts.length || parts.some((p) => !/^-?[1-9]\d*$/.test(p))) return []
    return parts.map((p) => Number(p))
  }
  // Compact from-end: "-1245" -> [-1, -2, -4, -5]
  if (/^-[1-9]+$/.test(text)) {
    return [...text.slice(1)].map((ch) => -Number(ch))
  }
  if (!/^[1-9]+$/.test(text)) return []
  return [...text].map((ch) => Number(ch))
}

function formatPositionPreview(spec) {
  const positions = parsePositionSpec(spec)
  if (!positions.length) return ''
  return positions
    .map((pos) => (pos < 0 ? `倒数第${-pos}` : `第${pos}`))
    .join('、')
}

async function onExtractFieldChange(side) {
  if (side === 'source') {
    const field = extractDraft.sourceField
    if (!field) return
    const mapping = currentContentMatchColumns().find((m) => m.source === field)
    if (mapping?.target) extractDraft.targetField = mapping.target
    return
  }
  const field = extractDraft.targetField
  if (!field) return
  const mapping = currentContentMatchColumns().find((m) => m.target === field)
  if (mapping?.source) extractDraft.sourceField = mapping.source
}

async function addExtractRule() {
  const sourceField = String(extractDraft.sourceField || '').trim()
  const targetField = String(extractDraft.targetField || '').trim()
  const sourcePositions = String(extractDraft.sourcePositions || '').trim()
  const targetPositions = String(extractDraft.targetPositions || '').trim()
  if (!sourceField || !targetField) {
    message.warning('请选择左右字段')
    return
  }
  const sourcePos = parsePositionSpec(sourcePositions)
  const targetPos = parsePositionSpec(targetPositions)
  if (!sourcePos.length || !targetPos.length) {
    message.warning('请输入有效取位，例如 1245、-1245 或 -5,-4,-2,-1')
    return
  }
  const linked = currentContentMatchColumns().some(
    (m) => m.source === sourceField && m.target === targetField,
  )
  if (!linked) {
    message.warning('只能为上一步已连线的字段设置提取匹配规则')
    return
  }
  const next = [...currentExtractMatchRules.value]
  const exists = next.some(
    (item) =>
      item.sourceField === sourceField &&
      item.sourcePositions === sourcePositions &&
      item.targetField === targetField &&
      item.targetPositions === targetPositions,
  )
  if (exists) {
    message.warning('这条提取规则已存在')
    return
  }
  next.push({ sourceField, sourcePositions, targetField, targetPositions })
  state.extractMatchRules = {
    ...state.extractMatchRules,
    [state.currentTablePair]: next,
  }
  extractDraft.sourcePositions = ''
  extractDraft.targetPositions = ''
  await persist()
  message.success(
    `已添加 ${sourceField}[${formatPositionPreview(sourcePositions)}] = ${targetField}[${formatPositionPreview(targetPositions)}]`,
  )
}

async function removeExtractRule(index) {
  const next = currentExtractMatchRules.value.filter((_, i) => i !== index)
  state.extractMatchRules = {
    ...state.extractMatchRules,
    [state.currentTablePair]: next,
  }
  await persist()
}

async function loadTables() {
  loading.sourceTables = true
  loading.targetTables = true
  try {
    const [s, t] = await Promise.all([
      api.tables(props.id, 'source', state.sourceDb, state.sourceSchema || undefined),
      api.tables(props.id, 'target', state.targetDb, state.targetSchema || undefined),
    ])
    tableItems.source = (s.tables || []).map(toTableItem)
    tableItems.target = (t.tables || []).map(toTableItem)
  } finally {
    loading.sourceTables = false
    loading.targetTables = false
  }
}

function currentPair() {
  const [source, target] = (state.currentTablePair || '').split('::')
  return { source, target }
}

async function loadSourceTableColumns(table) {
  if (!table || !state.sourceDb) return []
  if (tableItems.source.length && !tableItems.source.some((t) => t.key === table)) {
    message.warning(`源库「${state.sourceDb}」中不存在表「${table}」，请重新映射`)
    return []
  }
  const sampleLimit = 50
  const [cols, rowsResult] = await Promise.all([
    api.columns(props.id, 'source', state.sourceDb, table, state.sourceSchema || undefined),
    api
      .rows(props.id, 'source', state.sourceDb, table, state.sourceSchema || undefined, sampleLimit, 0)
      .catch(() => ({ rows: [] })),
  ])
  const items = (cols.columns || []).map((col) =>
    toColumnItem(col, samplesFromRows(rowsResult.rows, col.name)),
  )
  sourceColumnCache[table] = items
  return items
}

async function loadTargetTableColumns(table) {
  if (!table || !state.targetDb) {
    columnItems.target = []
    return []
  }
  if (tableItems.target.length && !tableItems.target.some((t) => t.key === table)) {
    columnItems.target = []
    message.warning(`目标库「${state.targetDb}」中不存在表「${table}」，请重新映射`)
    return []
  }
  const sampleLimit = 50
  const [cols, rowsResult] = await Promise.all([
    api.columns(props.id, 'target', state.targetDb, table, state.targetSchema || undefined),
    api
      .rows(props.id, 'target', state.targetDb, table, state.targetSchema || undefined, sampleLimit, 0)
      .catch(() => ({ rows: [] })),
  ])
  const items = (cols.columns || []).map((col) =>
    toColumnItem(col, samplesFromRows(rowsResult.rows, col.name)),
  )
  columnItems.target = items
  targetColumnOrderCache[table] = (cols.columns || []).map((col) => col.name)
  return items
}

async function loadColumns() {
  const pair = currentPair()
  if (!pair.source || !pair.target) {
    columnItems.source = []
    columnItems.target = []
    return
  }
  loading.sourceColumns = true
  loading.targetColumns = true
  try {
    const sources = sourceTablesForTarget.value.length
      ? sourceTablesForTarget.value
      : [pair.source]
    await Promise.all([
      ...sources.map((name) => loadSourceTableColumns(name)),
      loadTargetTableColumns(pair.target),
    ])
    columnItems.source = sourceColumnCache[pair.source] || []
  } finally {
    loading.sourceColumns = false
    loading.targetColumns = false
  }
}

async function selectTargetTable(target) {
  if (!target || target === currentTargetTable.value) return
  currentTargetTable.value = target
  await loadColumns()
}

let skipHideReload = false

function rowIndex(key) {
  return Number(String(key).replace(/^row-/, ''))
}

function rowPairPayload() {
  const pair = currentPair()
  return {
    source_database: state.sourceDb,
    target_database: state.targetDb,
    source_table: pair.source,
    target_table: pair.target,
    source_schema: state.sourceSchema || undefined,
    target_schema: state.targetSchema || undefined,
  }
}

async function applyRowOverlay() {
  if (!rowItems.source.length && !rowItems.target.length) {
    state.rowMappings = []
    return
  }
  const overlay = await api.rowMatchOverlay(props.id, {
    ...rowPairPayload(),
    source_indices: rowItems.source.map((item) => rowIndex(item.key)),
    target_indices: rowItems.target.map((item) => rowIndex(item.key)),
  })
  if (!overlay.has_match) {
    // 仅表示服务端对比缓存暂不可用，不因此清掉前端“已对比”状态，避免搜索时触发重跑对比
    rowItems.source.forEach((item) => {
      item.mapped = false
    })
    rowItems.target.forEach((item) => {
      item.mapped = false
    })
    state.rowMappings = []
    return
  }
  hasRowMatch.value = true
  if (typeof overlay.matched === 'number') rowMatchedTotal.value = overlay.matched
  const mappedSource = new Set(overlay.mapped_source || [])
  const mappedTarget = new Set(overlay.mapped_target || [])
  rowItems.source.forEach((item) => {
    item.mapped = mappedSource.has(rowIndex(item.key))
  })
  rowItems.target.forEach((item) => {
    item.mapped = mappedTarget.has(rowIndex(item.key))
  })
  state.rowMappings = overlay.mappings || []
}

function mergeRowSide(base, extraRows, extraIndices, prepend = true) {
  const seen = new Set(base.indices || [])
  const addRows = []
  const addIndices = []
  for (let i = 0; i < (extraIndices || []).length; i++) {
    const idx = Number(extraIndices[i])
    if (!Number.isFinite(idx) || seen.has(idx)) continue
    const row = extraRows[i]
    if (!row) continue
    seen.add(idx)
    addRows.push(row)
    addIndices.push(idx)
  }
  if (!addRows.length) {
    return {
      ...base,
      rows: [...(base.rows || [])],
      indices: [...(base.indices || [])],
    }
  }
  if (prepend) {
    return {
      ...base,
      rows: [...addRows, ...(base.rows || [])],
      indices: [...addIndices, ...(base.indices || [])],
    }
  }
  return {
    ...base,
    rows: [...(base.rows || []), ...addRows],
    indices: [...(base.indices || []), ...addIndices],
  }
}

async function pullMissingMatchPartners(s, t, pair, options = {}) {
  const limit = Math.max(1, Number(options.limit) || 100)
  const sourceSearched = !!options.sourceSearched
  const targetSearched = !!options.targetSearched
  const sourceIndices = [...(s.indices || [])]
  const targetIndices = [...(t.indices || [])]
  if (!sourceIndices.length && !targetIndices.length) return { s, t }

  const overlay = await api.rowMatchOverlay(props.id, {
    ...rowPairPayload(),
    source_database: state.sourceDb,
    target_database: state.targetDb,
    source_table: pair.source,
    target_table: pair.target,
    source_schema: state.sourceSchema || undefined,
    target_schema: state.targetSchema || undefined,
    source_indices: sourceIndices,
    target_indices: targetIndices,
  })
  if (!overlay.has_match) return { s, t }

  const pairBySource = new Map()
  const pairByTarget = new Map()
  for (const item of overlay.pairs || []) {
    const src = Number(item.source)
    const tgt = Number(item.target)
    if (!Number.isFinite(src) || !Number.isFinite(tgt)) continue
    pairBySource.set(src, tgt)
    pairByTarget.set(tgt, src)
  }

  // 两侧都在搜索：不追加额外行，避免撑破分页；只保留当前页结果画线
  if (sourceSearched && targetSearched) return { s, t }

  // 仅一侧搜索：对侧改为“当前页的配对行”，数量不超过分页大小
  if (sourceSearched && !targetSearched) {
    const orderedTargets = []
    const seen = new Set()
    for (const src of sourceIndices) {
      const tgt = pairBySource.get(src)
      if (tgt == null || seen.has(tgt)) continue
      seen.add(tgt)
      orderedTargets.push(tgt)
      if (orderedTargets.length >= limit) break
    }
    if (!orderedTargets.length) return { s, t: { ...t, rows: [], indices: [], total: t.total } }
    const fetched = await api.rowsByIndices(props.id, {
      side: 'target',
      database: state.targetDb,
      table: pair.target,
      schema_name: state.targetSchema || undefined,
      indices: orderedTargets,
    })
    return {
      s,
      t: {
        ...t,
        rows: fetched.rows || [],
        indices: orderedTargets.slice(0, (fetched.rows || []).length),
        total: t.total,
      },
    }
  }

  if (targetSearched && !sourceSearched) {
    const orderedSources = []
    const seen = new Set()
    for (const tgt of targetIndices) {
      const src = pairByTarget.get(tgt)
      if (src == null || seen.has(src)) continue
      seen.add(src)
      orderedSources.push(src)
      if (orderedSources.length >= limit) break
    }
    if (!orderedSources.length) return { s: { ...s, rows: [], indices: [], total: s.total }, t }
    const fetched = await api.rowsByIndices(props.id, {
      side: 'source',
      database: state.sourceDb,
      table: pair.source,
      schema_name: state.sourceSchema || undefined,
      indices: orderedSources,
    })
    return {
      s: {
        ...s,
        rows: fetched.rows || [],
        indices: orderedSources.slice(0, (fetched.rows || []).length),
        total: s.total,
      },
      t,
    }
  }

  // 无搜索（例如隐藏已配对后翻页）：只补齐对侧缺失配对，且总数不超过 limit
  const sourceSet = new Set(sourceIndices)
  const targetSet = new Set(targetIndices)
  const needTarget = []
  const needSource = []
  const seenTarget = new Set()
  const seenSource = new Set()
  for (const item of overlay.pairs || []) {
    const src = Number(item.source)
    const tgt = Number(item.target)
    if (!Number.isFinite(src) || !Number.isFinite(tgt)) continue
    if (sourceSet.has(src) && !targetSet.has(tgt) && !seenTarget.has(tgt)) {
      seenTarget.add(tgt)
      needTarget.push(tgt)
    }
    if (targetSet.has(tgt) && !sourceSet.has(src) && !seenSource.has(src)) {
      seenSource.add(src)
      needSource.push(src)
    }
  }
  const roomSource = Math.max(0, limit - sourceIndices.length)
  const roomTarget = Math.max(0, limit - targetIndices.length)
  const addSource = needSource.slice(0, roomSource)
  const addTarget = needTarget.slice(0, roomTarget)
  if (!addSource.length && !addTarget.length) return { s, t }

  const [targetExtra, sourceExtra] = await Promise.all([
    addTarget.length
      ? api.rowsByIndices(props.id, {
          side: 'target',
          database: state.targetDb,
          table: pair.target,
          schema_name: state.targetSchema || undefined,
          indices: addTarget,
        })
      : Promise.resolve({ rows: [] }),
    addSource.length
      ? api.rowsByIndices(props.id, {
          side: 'source',
          database: state.sourceDb,
          table: pair.source,
          schema_name: state.sourceSchema || undefined,
          indices: addSource,
        })
      : Promise.resolve({ rows: [] }),
  ])

  let nextS = s
  let nextT = t
  if (addSource.length) nextS = mergeRowSide(nextS, sourceExtra.rows || [], addSource, true)
  if (addTarget.length) nextT = mergeRowSide(nextT, targetExtra.rows || [], addTarget, true)
  return { s: nextS, t: nextT }
}

async function onRowEditMatch({ action, source, target }) {
  if (!hasRowMatch.value) return
  const result = await api.rowMatchEdit(props.id, {
    ...rowPairPayload(),
    action,
    source: source == null || source === '' ? undefined : rowIndex(source),
    target: target == null || target === '' ? undefined : rowIndex(target),
  })
  if (result?.has_match) {
    rememberContentStats(state.currentTablePair, result)
    if (typeof result.matched === 'number') rowMatchedTotal.value = result.matched
  }
  if (hideMappedRows.value) await loadRows()
  else await applyRowOverlay()
}

async function onClearRowMatch() {
  clearSingleCompareState()
  if (hasRowMatch.value) {
    await api.rowMatchEdit(props.id, { ...rowPairPayload(), action: 'clear' })
  }
  hasRowMatch.value = false
  rowMatchedTotal.value = null
  if (state.currentTablePair) delete state.contentStats[state.currentTablePair]
  if (hideMappedRows.value) {
    skipHideReload = true
    hideMappedRows.value = false
    await nextTick()
    skipHideReload = false
    await loadRows()
    return
  }
  rowItems.source.forEach((item) => {
    item.mapped = false
  })
  rowItems.target.forEach((item) => {
    item.mapped = false
  })
}

async function selectContentTarget(target) {
  if (!target || target === currentContentTarget.value) return
  rememberRowSearch(state.currentTablePair)
  const primary = pickPrimarySource(target)
  state.currentTablePair = primary && target ? `${primary}::${target}` : ''
  await onContentTargetChange()
}

async function onContentTargetChange() {
  skipHideReload = true
  rowPage.value = 1
  hideMappedRows.value = false
  unmatchedTotals.source = 0
  unmatchedTotals.target = 0
  searchTotals.source = 0
  searchTotals.target = 0
  state.rowMappings = []
  const target = currentContentTarget.value
  const primary = pickPrimarySource(target)
  if (primary && target && state.currentTablePair !== `${primary}::${target}`) {
    state.currentTablePair = `${primary}::${target}`
  }
  restoreRowSearch(state.currentTablePair)
  const cached = state.contentStats[state.currentTablePair]
  hasRowMatch.value = false
  rowMatchedTotal.value = cached?.matched ?? null
  await loadRows({ restoreMatch: false })
  await nextTick()
  skipHideReload = false
}

async function onRowPageSizeChange() {
  rowPage.value = 1
  await loadRows({ restoreMatch: false })
}

async function compareAllFieldContent() {
  const pair = currentPair()
  const target = pair.target
  const primary = pickPrimarySource(target) || pair.source
  const allCols = buildContentMatchColumns(target, primary)
  if (!primary || !target || !allCols.length) {
    message.warning('请先连线要对比的字段')
    return null
  }
  const selection = await promptCompareFields(allCols, target)
  if (!selection?.columns?.length) return null
  const mappedCols = selection.columns
  const fuzzy = !!selection.fuzzy
  clearSingleCompareState()

  if (primary && target && `${primary}::${target}` !== state.currentTablePair) {
    state.currentTablePair = `${primary}::${target}`
  }
  delete state.contentStats[`${primary}::${target}`]
  compareFieldsSubmitting.value = true
  try {
    const result = await api.rowMatch(props.id, {
      source_database: state.sourceDb,
      target_database: state.targetDb,
      source_table: primary,
      target_table: target,
      source_schema: state.sourceSchema || undefined,
      target_schema: state.targetSchema || undefined,
      columns: serializeMatchColumns(mappedCols),
      source_joins: buildContentMatchJoins(target),
      fuzzy_content_match: fuzzy,
      value_aliases: serializeValueAliases(currentValueAliases.value),
      extract_match_rules: serializeExtractMatchRules(currentExtractMatchRules.value),
      ...rowMatchFilterPayload(),
    })
    hasRowMatch.value = true
    rowMatchedTotal.value = result.matched || 0
    rememberContentStats(state.currentTablePair, result)
    if (typeof result.source_total === 'number') rowTotals.source = result.source_total
    if (typeof result.target_total === 'number') rowTotals.target = result.target_total
    rowPage.value = 1
    await loadRows()
    await persist()
    const scoped = result.filtered || hasActiveRowSearchFilters()
    message.success(
      scoped
        ? `已按当前筛选条件完成${fuzzy ? '模糊内容对比' : '精确对比'}（${mappedCols.length} 个字段）`
        : `${fuzzy ? '模糊内容对比' : '精确对比'}完成（使用 ${mappedCols.length} 个字段）`,
    )
    return {
      mappings: state.rowMappings,
      matched: result.matched || 0,
      leftOnly: result.left_only || 0,
      rightOnly: result.right_only || 0,
    }
  } finally {
    compareFieldsSubmitting.value = false
  }
}

async function onRowSearch({ leftConditions, rightConditions, leftLogic, rightLogic }) {
  // 单条对比锁定结果视图，忽略筛选变更，避免被 reload 踢出
  if (singleCompareActive.value) return
  rowSearchConditions.source = cloneSearchConditions(leftConditions, leftLogic)
  rowSearchConditions.target = cloneSearchConditions(rightConditions, rightLogic)
  rowSearchLogic.source = normalizeSearchLogic(leftLogic || deriveSearchLogic(rowSearchConditions.source))
  rowSearchLogic.target = normalizeSearchLogic(rightLogic || deriveSearchLogic(rowSearchConditions.target))
  rememberRowSearch()
  rowPage.value = 1
  await loadRows({ restoreMatch: false })
}

async function fetchRowSide(side, pair, mappedCols, limit, offset) {
  const conditions = Array.isArray(rowSearchConditions[side]) ? rowSearchConditions[side] : []
  const database = side === 'source' ? state.sourceDb : state.targetDb
  const table = side === 'source' ? pair.source : pair.target
  const schemaName = side === 'source' ? state.sourceSchema : state.targetSchema
  // 源侧只取属于当前主表的物理列；跨表字段（如 duty_catalog.code）不能拿去查 resource
  const mappedNames =
    side === 'source'
      ? mappedCols
          .filter((item) => !item.source_table || item.source_table === table)
          .flatMap((item) => mappingSourceFields(item))
      : mappedCols.map((item) => item.target)
  const displayNames = soloDisplayColumnNames(side, pair.source, pair.target)
  // 搜索时也必须带上跨表关联键，否则关联行会因缺字段被误判为不匹配
  const joinNames = side === 'source' ? joinColumnsForTable(table, pair.target) : []
  const allColumns = [...new Set([...mappedNames, ...displayNames, ...joinNames].filter(Boolean))]
  const conditionFields = conditions.flatMap((item) => {
    if (!item.field) return []
    const sep = String(item.field).indexOf('::')
    // 关联表字段 table::field 不能当作主表列去查
    if (sep > 0) return []
    return [item.field]
  })
  const fetchColumns = [...new Set([...allColumns, ...conditionFields])]
  const hideUnmatchedOnly = hideMappedRows.value && hasRowMatch.value
  if (conditions.length) {
    if (!fetchColumns.length && !conditions.some((item) => item.field)) {
      searchTotals[side] = 0
      return { rows: [], indices: [], total: 0 }
    }
    const result = await api.searchRows(props.id, {
      ...rowPairPayload(),
      side,
      database,
      table,
      schema_name: schemaName || undefined,
      columns: fetchColumns,
      conditions: conditions.map((item, idx) => {
        const mode = normalizeSearchMode(item.mode, item.negate)
        return {
          search_columns: item.field ? [item.field] : allColumns,
          keywords: item.keywords,
          mode,
          negate: mode === 'exclude' || mode === 'not_equals',
          logic: idx === 0 ? 'and' : normalizeSearchLogic(item.logic || rowSearchLogic[side]),
        }
      }),
      condition_logic: normalizeSearchLogic(rowSearchLogic[side]),
      offset,
      limit,
      unmatched_only: hideUnmatchedOnly,
      source_joins: side === 'source' ? buildContentMatchJoins(pair.target) : [],
    })
    searchTotals[side] = result.total || 0
    return result
  }
  searchTotals[side] = 0
  if (hideUnmatchedOnly) {
    const result = await api.unmatchedRows(props.id, {
      ...rowPairPayload(),
      side,
      database,
      table,
      schema_name: schemaName || undefined,
      offset,
      limit,
    })
    unmatchedTotals[side] = result.total || 0
    return result
  }
  const result = await api.rows(props.id, side, database, table, schemaName || undefined, limit, offset)
  rowTotals[side] = result.total || 0
  return {
    rows: result.rows || [],
    indices: (result.rows || []).map((_, index) => index + offset),
    total: result.total || 0,
  }
}

function soloDisplayColumnNames(side, primary, target) {
  const saved = state.displayFields[target] || {}
  if (side === 'target') {
    return [...new Set((saved.right || []).filter(Boolean))]
  }
  const names = []
  for (const key of saved.left || []) {
    const sep = String(key).indexOf('::')
    if (sep < 0) {
      if (key) names.push(key)
      continue
    }
    const table = String(key).slice(0, sep)
    const field = String(key).slice(sep + 2)
    if (table === primary && field) names.push(field)
  }
  return [...new Set(names)]
}

async function loadPartnerTableIndex(table, joinField, keys) {
  const uniq = [...new Set((keys || []).filter((k) => k !== null && k !== undefined && k !== '__NULL__').map(String))]
  if (!uniq.length) return new Map()
  // 多对多时一个键可能对应多行，预留下限并避免被「键数量」截断
  const limit = Math.min(20000, Math.max(2000, uniq.length * 40))
  const result = await api
    .rowsByValues(props.id, {
      side: 'source',
      database: state.sourceDb,
      table,
      column: joinField,
      schema_name: state.sourceSchema || undefined,
      values: uniq,
      limit,
    })
    .catch(() => ({ rows: [] }))
  const index = new Map()
  for (const row of result.rows || []) {
    const key = joinKey(row[joinField])
    if (!index.has(key)) index.set(key, [])
    index.get(key).push(row)
  }
  return index
}

function joinEdgeFrom(table, join) {
  if (join.leftTable === table) {
    return { localField: join.leftField, remoteTable: join.rightTable, remoteField: join.rightField }
  }
  if (join.rightTable === table) {
    return { localField: join.rightField, remoteTable: join.leftTable, remoteField: join.leftField }
  }
  return null
}

function partnerRowIdentity(row, remoteField) {
  if (!row || typeof row !== 'object') return joinKey(row)
  if (Object.prototype.hasOwnProperty.call(row, 'id') && row.id != null) return `id:${row.id}`
  if (remoteField && row[remoteField] != null) return `${remoteField}:${row[remoteField]}`
  try {
    return JSON.stringify(row)
  } catch {
    return String(row)
  }
}

function formatMultiJoinValues(values, { unique = true } = {}) {
  const raw = (values || []).map((v) => formatRowCell(v)).filter((v) => v && v !== 'NULL')
  const list = unique ? [...new Set(raw)] : raw
  if (!list.length) return 'NULL'
  return list.join('，')
}

function partnerDisplayValue(partner, remoteField, localVal) {
  if (!partner || typeof partner !== 'object') return localVal
  // 多对多时优先展示对端行唯一 id，避免关联键相同（如同一 sys_id）去重后只剩 1 个
  if (Object.prototype.hasOwnProperty.call(partner, 'id') && partner.id != null && partner.id !== '') {
    return partner.id
  }
  if (remoteField && partner[remoteField] != null && partner[remoteField] !== '') {
    return partner[remoteField]
  }
  return localVal
}

function rowsForTable(rowsByTable, table) {
  const raw = rowsByTable?.get(table)
  if (!raw) return []
  return Array.isArray(raw) ? raw : [raw]
}

/** Walk all join hops so bridge tables (e.g. duty_catalog_sys) can reach duty_catalog. */
async function loadPartnerIndexesMultiHop(primary, primaryRows, joins) {
  Object.keys(partnerIndexCache).forEach((k) => delete partnerIndexCache[k])
  let frontier = [{ table: primary, rows: primaryRows || [] }]
  const loaded = new Set([primary])

  const preferIdJoin = (edge) => {
    const remote = String(edge.remoteField || '').toLowerCase()
    const local = String(edge.localField || '').toLowerCase()
    if (remote === 'id' || local === 'id') return 0
    if (remote.endsWith('_id') || local.endsWith('_id')) return 1
    return 2
  }

  while (frontier.length) {
    const nextFrontier = []
    for (const { table, rows } of frontier) {
      const edges = []
      for (const join of joins) {
        const edge = joinEdgeFrom(table, join)
        if (!edge || loaded.has(edge.remoteTable)) continue
        edges.push(edge)
      }
      edges.sort((a, b) => preferIdJoin(a) - preferIdJoin(b))
      for (const edge of edges) {
        if (loaded.has(edge.remoteTable)) continue
        const keys = (rows || []).map((row) => row?.[edge.localField])
        const index = await loadPartnerTableIndex(edge.remoteTable, edge.remoteField, keys)
        partnerIndexCache[edge.remoteTable] = index
        loaded.add(edge.remoteTable)
        const partnerRows = [...index.values()].flat()
        nextFrontier.push({ table: edge.remoteTable, rows: partnerRows })
      }
    }
    frontier = nextFrontier
  }
}

function undirectedJoinEdgeKey(table, edge) {
  const a = `${table}.${edge.localField}`
  const b = `${edge.remoteTable}.${edge.remoteField}`
  return [a, b].sort().join('\0')
}

/** 同表之间的全部关联边（多字段 = 交集条件） */
function joinEdgesBetween(table, remoteTable, joins) {
  const edges = []
  for (const join of joins || []) {
    const edge = joinEdgeFrom(table, join)
    if (edge && edge.remoteTable === remoteTable) edges.push(edge)
  }
  return edges
}

function partnerMatchesAllJoinEdges(localRow, partner, edges) {
  for (const edge of edges || []) {
    if (!valuesEqualForJoin(localRow?.[edge.localField], partner?.[edge.remoteField])) {
      return false
    }
  }
  return true
}

function enrichSourceLinesWithJoins(primary, primaryRow, target, joins, compareSelected = null) {
  const rowsByTable = new Map([[primary, [primaryRow]]])
  const joinLines = []
  const visitedEdges = new Set()
  const queue = [primary]

  while (queue.length) {
    const table = queue.shift()
    const localRows = rowsForTable(rowsByTable, table)
    for (const join of joins) {
      const edge = joinEdgeFrom(table, join)
      if (!edge) continue
      // 按「表.字段」去重，避免正反边重复；同表多字段关联（如 id 与 archived）都要展示
      const edgeKey = undirectedJoinEdgeKey(table, edge)
      if (visitedEdges.has(edgeKey)) continue
      visitedEdges.add(edgeKey)

      const allEdges = joinEdgesBetween(table, edge.remoteTable, joins)

      // 若对端已由其它关联拉到，优先用已关联行按本字段建索引（如 sys.archived=duty_catalog_sys.archived）
      let partnerIndex = null
      const existingRemote = rowsForTable(rowsByTable, edge.remoteTable)
      if (existingRemote.length) {
        partnerIndex = new Map()
        for (const row of existingRemote) {
          const key = joinKey(row?.[edge.remoteField])
          if (!partnerIndex.has(key)) partnerIndex.set(key, [])
          partnerIndex.get(key).push(row)
        }
      } else {
        partnerIndex = partnerIndexCache[edge.remoteTable]
      }
      const leftRef = `${table}.${edge.localField}`
      const rightRef = `${edge.remoteTable}.${edge.remoteField}`
      const pairExpr = `${leftRef}=${rightRef}`

      const matchedPairs = []
      const seenPartner = new Set()
      let missingLocal = 0
      const unmatchedLocals = []
      for (const row of localRows) {
        const localVal = row?.[edge.localField]
        const hasLocalKey = !(localVal === null || localVal === undefined || formatRowCell(localVal) === 'NULL')
        if (!hasLocalKey) {
          missingLocal += 1
          continue
        }
        // 同表多字段关联取交集：候选行必须同时满足全部关联条件
        const partners = (partnerIndex?.get(joinKey(localVal)) || []).filter((partner) =>
          partnerMatchesAllJoinEdges(row, partner, allEdges),
        )
        if (!partners.length) {
          unmatchedLocals.push(localVal)
          continue
        }
        for (const partner of partners) {
          const id = partnerRowIdentity(partner, edge.remoteField)
          if (seenPartner.has(id)) continue
          seenPartner.add(id)
          matchedPairs.push({ localVal, partner })
        }
      }

      const partnerRows = matchedPairs.map((item) => item.partner)
      let labelPrefix = '匹配'
      let valueText = 'NULL'
      let unequal = false
      if (!matchedPairs.length) {
        if (missingLocal && !unmatchedLocals.length) {
          labelPrefix = '无关联键'
          valueText = 'NULL'
        } else if (existingRemote.length) {
          // 表已关联上，但本字段值不一致
          labelPrefix = '关联字段不匹配'
          valueText = formatMultiJoinValues(localRows.map((row) => row?.[edge.localField]))
          unequal = true
        } else {
          labelPrefix = '未找到关联'
          valueText = formatMultiJoinValues(localRows.map((row) => row?.[edge.localField]))
          unequal = true
        }
      } else {
        const count = matchedPairs.length
        const displayVals = matchedPairs.map((item) =>
          partnerDisplayValue(item.partner, edge.remoteField, item.localVal),
        )
        // 若对端关联键本身就各不相同（如多个 duty_id），直接展示关联键更直观
        const remoteKeys = matchedPairs.map((item) => item.partner?.[edge.remoteField] ?? item.localVal)
        const remoteUnique = new Set(remoteKeys.map((v) => joinKey(v)))
        valueText =
          remoteUnique.size > 1
            ? formatMultiJoinValues(remoteKeys)
            : formatMultiJoinValues(displayVals)
        if (unmatchedLocals.length) {
          labelPrefix = `部分匹配(${count}/${count + unmatchedLocals.length})`
          unequal = true
          valueText = `${valueText}；未找到：${formatMultiJoinValues(unmatchedLocals)}`
        } else {
          labelPrefix = count > 1 ? `匹配(${count})` : '匹配'
        }
      }

      const joinDetails =
        matchedPairs.length > 1 || unmatchedLocals.length
          ? [
              ...matchedPairs.map((item, index) => ({
                index: index + 1,
                local: formatRowCell(item.localVal),
                remote: formatRowCell(item.partner?.[edge.remoteField]),
                text: `${leftRef}=${formatRowCell(item.localVal)} → ${rightRef}=${formatRowCell(
                  partnerDisplayValue(item.partner, edge.remoteField, item.localVal),
                )}`,
              })),
              ...unmatchedLocals.map((localVal, index) => ({
                index: matchedPairs.length + index + 1,
                local: formatRowCell(localVal),
                remote: 'NULL',
                text: `${leftRef}=${formatRowCell(localVal)} → 未找到 ${rightRef}`,
              })),
            ]
          : []

      joinLines.push({
        kind: 'join',
        label: `${labelPrefix} ${pairExpr}`,
        leftRef,
        rightRef,
        value: valueText,
        text: `${labelPrefix} ${pairExpr} = ${valueText}`,
        unequal,
        compareMark: null,
        expandable: joinDetails.length > 0,
        joinDetails,
      })

      if (!partnerRows.length) continue
      // 多字段交集：以本次交集结果覆盖对端行集合（不能并集拼入 archived=1 的脏数据）
      const hadRows = rowsForTable(rowsByTable, edge.remoteTable).length > 0
      if (allEdges.length > 1) {
        rowsByTable.set(edge.remoteTable, partnerRows)
      } else {
        const existed = rowsForTable(rowsByTable, edge.remoteTable)
        const merged = [...existed]
        const mergedSeen = new Set(existed.map((row) => partnerRowIdentity(row, edge.remoteField)))
        for (const row of partnerRows) {
          const id = partnerRowIdentity(row, edge.remoteField)
          if (mergedSeen.has(id)) continue
          mergedSeen.add(id)
          merged.push(row)
        }
        rowsByTable.set(edge.remoteTable, merged)
      }
      if (!hadRows) queue.push(edge.remoteTable)
    }
  }

  const orderedMappings = collectOrderedSourceMappings(target)
  const fieldLines = []
  for (const mapping of orderedMappings) {
    const table = mapping.source_table || primary
    // 关联键若同时又连到目标字段，仍需展示字段值（原先会因是关联键被跳过）
    const tableRows = rowsForTable(rowsByTable, table)
    if (!tableRows.length) continue
    const sourceLabel = mapping.source || mappingSourceFields(mapping).join('+')
    const values = tableRows.map((row) => formatCompositeSourceValue(row, mapping))
    const value = formatMultiJoinValues(values)
    fieldLines.push({
      kind: 'field',
      table,
      field: sourceLabel,
      label: sourceLabel,
      value,
      text: `${table}.${sourceLabel}=${value}`,
      unequal: false,
      compareMark: compareMarkForColumn(mapping, compareSelected),
    })
  }

  return appendSoloDisplayLines(
    'source',
    [...fieldLines, ...joinLines],
    primaryRow,
    primary,
    target,
    rowsByTable,
  )
}

async function loadRows({ restoreMatch = false } = {}) {
  // 单条对比中禁止自动 reload，只有「退出单条对比」会先清状态再加载
  if (singleCompareActive.value) return
  const pair = currentPair()
  const target = pair.target
  const primary = pickPrimarySource(target) || pair.source
  if (primary && target && `${primary}::${target}` !== state.currentTablePair) {
    state.currentTablePair = `${primary}::${target}`
  }
  const mappedColsRaw = buildContentMatchColumns(target, primary)
  if (!primary || !target || !mappedColsRaw.length) {
    rowItems.source = []
    rowItems.target = []
    rowTotals.source = 0
    rowTotals.target = 0
    unmatchedTotals.source = 0
    unmatchedTotals.target = 0
    searchTotals.source = 0
    searchTotals.target = 0
    return
  }

  if (!targetColumnOrderCache[target]?.length) {
    try {
      await loadTargetTableColumns(target)
    } catch {
      /* keep mapping order if metadata unavailable */
    }
  }

  const displayLeft = state.displayFields[target]?.left || []
  const joins = state.sourceJoins[target] || []
  const sourceTablesNeeded = new Set([primary])
  for (const key of displayLeft) {
    const sep = String(key).indexOf('::')
    if (sep > 0) sourceTablesNeeded.add(String(key).slice(0, sep))
  }
  for (const src of sourcesWithColumnsForTarget(target)) {
    sourceTablesNeeded.add(src)
  }
  for (const table of tablesReachableFrom(primary, joins)) {
    sourceTablesNeeded.add(table)
  }
  await Promise.all(
    [...sourceTablesNeeded].map(async (table) => {
      if (!table || sourceColumnCache[table]?.length) return
      try {
        await loadSourceTableColumns(table)
      } catch {
        /* ignore */
      }
    }),
  )

  const mappedCols = mappedColsRaw
  const targetCols = allTargetMappedCols(target, primary)
  const activePair = { source: primary, target }
  const compareSelected = compareSelectedKeySet(target)

  // Enable join enrichment when primary participates in any configured join.
  const enrichSource =
    isCrossTableContent(target) || joins.some((j) => j.leftTable === primary || j.rightTable === primary)

  loading.sourceRows = true
  loading.targetRows = true
  try {
    const limit = Math.min(rowPageSize.value, 1000)
    const offset = (rowPage.value - 1) * limit

    const [s0, t0] = await Promise.all([
      fetchRowSide('source', activePair, mappedCols, limit, offset),
      fetchRowSide('target', activePair, targetCols, limit, offset),
    ])
    if (hasRowMatch.value) {
      await silentRefreshMatchCacheIfNeeded()
    }
    const sourceSearched = hasRowSearchKeywords('source')
    const targetSearched = hasRowSearchKeywords('target')
    const searching = sourceSearched || targetSearched || hideMappedRows.value
    const shouldAlignPartners =
      searching || hasRowMatch.value || !!state.contentStats[state.currentTablePair]
    const aligned = shouldAlignPartners
      ? await pullMissingMatchPartners(s0, t0, activePair, {
          limit,
          sourceSearched,
          targetSearched,
        })
      : { s: s0, t: t0 }
    const s = aligned.s
    const t = aligned.t
    const sourceIdx = s.indices || []
    const targetIdx = t.indices || []

    if (enrichSource) {
      await loadPartnerIndexesMultiHop(primary, s.rows || [], joins)
    }

    if (enrichSource) {
      rowItems.source = (s.rows || []).map((row, i) =>
        toQualifiedSourceRowItem(
          sourceIdx[i],
          enrichSourceLinesWithJoins(primary, row, target, joins, compareSelected),
          rowSignature(row, mappedCols, 'source'),
        ),
      )
    } else {
      rowItems.source = (s.rows || []).map((row, i) => {
        const item = toRowItem(row, sourceIdx[i], mappedCols, 'source', false, compareSelected)
        const fieldLines = appendSoloDisplayLines(
          'source',
          item.fieldLines,
          row,
          primary,
          target,
          new Map([[primary, row]]),
        )
        return {
          ...item,
          fieldLines,
          lineCount: Math.max(fieldLines.length, 1),
          title: fieldLines.map((f) => f.text).join('\n') || item.title,
        }
      })
    }
    rowItems.target = (t.rows || []).map((row, i) => {
      const item = toRowItem(row, targetIdx[i], targetCols, 'target', false, compareSelected)
      const fieldLines = appendSoloDisplayLines('target', item.fieldLines, row, primary, target)
      return {
        ...item,
        fieldLines,
        lineCount: Math.max(fieldLines.length, 1),
        title: fieldLines.map((f) => f.text).join('\n') || item.title,
      }
    })
    await applyRowOverlay()
    if (restoreMatch) await ensureContentMatchRestored()
  } finally {
    loading.sourceRows = false
    loading.targetRows = false
  }
}

async function silentRefreshMatchCacheIfNeeded() {
  // 仅在本会话已点过「内容对比」且服务端缓存丢失时静默重建，不弹对比遮罩、不带搜索条件
  if (!hasRowMatch.value || restoringContentMatch) return false
  const probe = await api.rowMatchOverlay(props.id, {
    ...rowPairPayload(),
    source_indices: [0],
    target_indices: [0],
  })
  if (probe.has_match) return true

  const pairKey = state.currentTablePair
  const target = currentPair().target
  const primary = pickPrimarySource(target) || currentPair().source
  if (!pairKey || !target || !primary) return false
  const columns = filterMatchColumns(buildContentMatchColumns(target, primary), target)
  if (!columns.length) return false

  restoringContentMatch = true
  try {
    const aliases = state.valueAliases[pairKey] || []
    const fuzzy = !!state.contentCompareFields[target]?.fuzzy
    const result = await api.rowMatch(props.id, {
      source_database: state.sourceDb,
      target_database: state.targetDb,
      source_table: primary,
      target_table: target,
      source_schema: state.sourceSchema || undefined,
      target_schema: state.targetSchema || undefined,
      columns: serializeMatchColumns(columns),
      source_joins: buildContentMatchJoins(target),
      fuzzy_content_match: fuzzy,
      value_aliases: serializeValueAliases(aliases),
      extract_match_rules: serializeExtractMatchRules(state.extractMatchRules[pairKey] || []),
    })
    hasRowMatch.value = true
    rememberContentStats(pairKey, result)
    rowMatchedTotal.value = result.matched || 0
    return true
  } catch {
    return false
  } finally {
    restoringContentMatch = false
  }
}

async function ensureContentMatchRestored() {
  if (restoringContentMatch) return
  const pairKey = state.currentTablePair
  const target = currentPair().target
  const primary = pickPrimarySource(target) || currentPair().source
  if (!pairKey || !target || !primary) return
  if (hasRowMatch.value) {
    const cached = state.contentStats[pairKey]
    if (cached && rowMatchedTotal.value == null) rowMatchedTotal.value = cached.matched ?? null
    return
  }
  // 搜索/筛选只刷新列表，绝不自动重跑内容对比
  if (hasActiveRowSearchFilters() || hideMappedRows.value) return

  const hasSavedCompare =
    !!state.contentStats[pairKey] || !!state.contentCompareFields[target]?.selected?.length
  if (!hasSavedCompare) return

  const columns = filterMatchColumns(buildContentMatchColumns(target, primary), target)
  if (!columns.length) return

  restoringContentMatch = true
  try {
    const aliases = state.valueAliases[pairKey] || []
    const fuzzy = !!state.contentCompareFields[target]?.fuzzy
    const result = await api.rowMatch(props.id, {
      source_database: state.sourceDb,
      target_database: state.targetDb,
      source_table: primary,
      target_table: target,
      source_schema: state.sourceSchema || undefined,
      target_schema: state.targetSchema || undefined,
      columns: serializeMatchColumns(columns),
      source_joins: buildContentMatchJoins(target),
      fuzzy_content_match: fuzzy,
      value_aliases: serializeValueAliases(aliases),
      extract_match_rules: serializeExtractMatchRules(state.extractMatchRules[pairKey] || []),
    })
    hasRowMatch.value = true
    rememberContentStats(pairKey, result)
    rowMatchedTotal.value = result.matched || 0
    await applyRowOverlay()
  } catch {
    const cached = state.contentStats[pairKey]
    if (cached) rowMatchedTotal.value = cached.matched ?? null
  } finally {
    restoringContentMatch = false
  }
}

async function next() {
  if (current.value === 0) {
    if (!state.sourceDb || !state.targetDb) {
      message.warning('请先选择源数据库和目标数据库')
      return
    }
    loading.next = true
    try {
      await loadTables()
      const removed = pruneTableMappingsToCatalog()
      if (removed > 0) {
        message.info(`已清除 ${removed} 条在当前库中不存在的表映射，请重新连线`)
      }
      current.value = 1
      await persist()
    } finally {
      loading.next = false
    }
    return
  }
  if (current.value === 1) {
    await loadTables()
    pruneTableMappingsToCatalog()
    if (!state.tableMappings.length) {
      message.warning('请先通过内容对比或手动连线关联数据表')
      return
    }
    const firstTarget = state.tableMappings[0].target
    const firstSource =
      state.tableMappings.find((m) => m.target === firstTarget)?.source || state.tableMappings[0].source
    state.currentTablePair = `${firstSource}::${firstTarget}`
    loading.next = true
    try {
      await loadColumns()
      current.value = 2
      await persist()
    } finally {
      loading.next = false
    }
    return
  }
  if (current.value === 2) {
    // Cross-table joins only need at least one side mapped to the target.
    // The other side may be join-key only (no field mappings).
    for (const [target, joins] of Object.entries(state.sourceJoins || {})) {
      for (const join of joins || []) {
        const leftMapped = (state.columnMappings[`${join.leftTable}::${target}`] || []).length > 0
        const rightMapped = (state.columnMappings[`${join.rightTable}::${target}`] || []).length > 0
        if (!leftMapped && !rightMapped) {
          message.warning(
            `跨表关联「${join.leftTable}.${join.leftField} = ${join.rightTable}.${join.rightField}」的两侧源表均未连线目标字段，请至少完成一侧字段连线`,
          )
          return
        }
      }
    }
    const linkedPairs = contentPairOptions.value
    if (!linkedPairs.length) {
      message.warning('请先连线要对比的字段，未连线的字段不会进入下一步对比')
      return
    }
    const firstTarget = linkedPairs[0].value.split('::')[1]
    const primary = pickPrimarySource(firstTarget) || linkedPairs[0].value.split('::')[0]
    state.currentTablePair = `${primary}::${firstTarget}`
    loading.next = true
    try {
      rowPage.value = 1
      await persist()
      await loadRows({ restoreMatch: false })
      current.value = 3
      await persist()
    } finally {
      loading.next = false
    }
  }
}

async function prev() {
  current.value -= 1
  await persist()
}

async function ensurePairContentStats(mapping) {
  const pairKey = `${mapping.source}::${mapping.target}`
  const target = mapping.target
  const primary = pickPrimarySource(target) || mapping.source
  const columns = filterMatchColumns(buildContentMatchColumns(target, primary), target)
  if (!columns.length) return null
  const cached = state.contentStats[pairKey]
  if (cached) return cached
  const aliases = state.valueAliases[pairKey] || []
  const fuzzy = !!state.contentCompareFields[target]?.fuzzy
  const result = await api.rowMatch(props.id, {
    source_database: state.sourceDb,
    target_database: state.targetDb,
    source_table: primary,
    target_table: target,
    source_schema: state.sourceSchema || undefined,
    target_schema: state.targetSchema || undefined,
    columns: serializeMatchColumns(columns),
    source_joins: buildContentMatchJoins(target),
    fuzzy_content_match: fuzzy,
    value_aliases: serializeValueAliases(aliases),
    extract_match_rules: serializeExtractMatchRules(state.extractMatchRules[pairKey] || []),
    ...(pairKey === state.currentTablePair ? rowMatchFilterPayload() : {}),
  })
  rememberContentStats(pairKey, result)
  return state.contentStats[pairKey]
}

function compareFieldsForReport(target) {
  const saved = state.contentCompareFields[target]
  if (!saved?.selected?.length) {
    return { fields: [], fuzzy: false }
  }
  const fields = saved.selected.map((key) => {
    const match = String(key).match(/^(.*?)::(.*)->(.*)$/)
    if (match) {
      const sourceTable = match[1]
      const source = match[2]
      const targetField = match[3]
      return {
        sourceTable,
        source,
        target: targetField,
        label: sourceTable ? `${sourceTable}.${source} → ${targetField}` : `${source} → ${targetField}`,
      }
    }
    return { label: String(key) }
  })
  return { fields, fuzzy: !!saved.fuzzy }
}

function snapshotSearchFilters(side) {
  return cloneSearchConditions(rowSearchConditions[side] || [], rowSearchLogic[side])
}

function filteredStatsForCurrentTarget(target) {
  const currentTarget = currentContentTarget.value || currentPair().target
  if (!target || target !== currentTarget) return null
  const hasSourceFilter = hasRowSearchKeywords('source')
  const hasTargetFilter = hasRowSearchKeywords('target')
  if (!hasSourceFilter && !hasTargetFilter) return null
  const sourceTotal = hasSourceFilter
    ? Number(searchTotals.source || 0)
    : Number(rowTotals.source || 0)
  const targetTotal = hasTargetFilter
    ? Number(searchTotals.target || 0)
    : Number(rowTotals.target || 0)
  const matched = Math.min(sourceTotal, targetTotal)
  return {
    sourceTotal,
    targetTotal,
    matched,
    leftOnly: Math.max(0, sourceTotal - matched),
    rightOnly: Math.max(0, targetTotal - matched),
    searchFilters: {
      source: snapshotSearchFilters('source'),
      target: snapshotSearchFilters('target'),
      sourceLogic: normalizeSearchLogic(rowSearchLogic.source),
      targetLogic: normalizeSearchLogic(rowSearchLogic.target),
    },
  }
}

async function buildReport() {
  const tables = []
  const seenTargets = new Set()
  const targets = []
  for (const mapping of state.tableMappings) {
    if (!mapping?.target || seenTargets.has(mapping.target)) continue
    seenTargets.add(mapping.target)
    targets.push(mapping.target)
  }

  const activeFilteredStats = filteredStatsForCurrentTarget(
    currentContentTarget.value || currentPair().target,
  )

  for (const target of targets) {
    const sources = sourcesWithColumnsForTarget(target)
    const fallbackSources = state.tableMappings
      .filter((m) => m.target === target)
      .map((m) => m.source)
    const sourceList = sources.length ? sources : [...new Set(fallbackSources)]
    const primary = pickPrimarySource(target) || sourceList[0] || ''
    const pairKey = primary && target ? `${primary}::${target}` : target
    const columns = []
    const seenCol = new Set()
    for (const src of sourceList) {
      for (const col of state.columnMappings[`${src}::${target}`] || []) {
        if (!col?.source || !col?.target) continue
        const id = `${src}.${col.source}->${col.target}`
        if (seenCol.has(id)) continue
        seenCol.add(id)
        columns.push({
          source: col.source,
          target: col.target,
          sourceTable: src,
        })
      }
    }

    const compareMeta = compareFieldsForReport(target)
    const filteredView = filteredStatsForCurrentTarget(target)
    const cachedStats = state.contentStats[pairKey] || null
    let stats = null
    let statsMode = 'none'
    let searchFilters = { source: [], target: [] }
    if (filteredView || cachedStats?.filtered) {
      stats = cachedStats?.filtered ? cachedStats : filteredView || cachedStats
      statsMode = 'filtered'
      searchFilters =
        filteredView?.searchFilters ||
        rowSearchByPair[pairKey] ||
        { source: [], target: [] }
      if (searchFilters.source || searchFilters.target) {
        searchFilters = {
          source: cloneSearchConditions(searchFilters.source || []),
          target: cloneSearchConditions(searchFilters.target || []),
          sourceLogic: normalizeSearchLogic(
            searchFilters.sourceLogic || rowSearchByPair[pairKey]?.sourceLogic,
          ),
          targetLogic: normalizeSearchLogic(
            searchFilters.targetLogic || rowSearchByPair[pairKey]?.targetLogic,
          ),
        }
      }
    } else if (!activeFilteredStats && columns.length && primary) {
      try {
        stats = await ensurePairContentStats({ source: primary, target })
      } catch {
        stats = cachedStats
      }
      if (stats) statsMode = stats.filtered ? 'filtered' : 'full'
    }

    const aliases = []
    const seenAlias = new Set()
    for (const src of sourceList) {
      for (const item of state.valueAliases[`${src}::${target}`] || []) {
        const id = `${item.sourceField}:${item.sourceValue}=${item.targetField}:${item.targetValue}`
        if (seenAlias.has(id)) continue
        seenAlias.add(id)
        aliases.push({
          sourceField: item.sourceField,
          sourceValue: item.sourceValue,
          targetField: item.targetField,
          targetValue: item.targetValue,
        })
      }
    }

    const extractRules = []
    const seenExtract = new Set()
    for (const src of sourceList) {
      for (const item of state.extractMatchRules[`${src}::${target}`] || []) {
        const id = `${item.sourceField}:${item.sourcePositions}=${item.targetField}:${item.targetPositions}`
        if (seenExtract.has(id)) continue
        seenExtract.add(id)
        extractRules.push({
          sourceField: item.sourceField,
          sourcePositions: item.sourcePositions,
          targetField: item.targetField,
          targetPositions: item.targetPositions,
        })
      }
    }

    const joins = state.sourceJoins[target] || []
    tables.push({
      id: pairKey,
      sourceTable: sourceList.join(' + ') || primary,
      sourceTables: sourceList,
      targetTable: target,
      primaryTable: primary,
      columns,
      compareFields: compareMeta.fields,
      compareFuzzy: compareMeta.fuzzy,
      valueAliases: aliases,
      extractMatchRules: extractRules,
      searchFilters,
      sourceJoins: joins.map((item) => ({
        leftTable: item.leftTable,
        leftField: item.leftField,
        rightTable: item.rightTable,
        rightField: item.rightField,
      })),
      compared: !!stats,
      statsMode,
      sourceTotal: stats?.sourceTotal ?? 0,
      targetTotal: stats?.targetTotal ?? 0,
      matched: stats?.matched ?? 0,
      leftOnly: stats?.leftOnly ?? 0,
      rightOnly: stats?.rightOnly ?? 0,
    })
  }

  return {
    taskName: task.value?.name || '',
    generatedAt: new Date().toISOString(),
    sourceLabel: formatDs(task.value?.source),
    targetLabel: formatDs(task.value?.target),
    sourceDb: state.sourceDb,
    targetDb: state.targetDb,
    sourceSchema: state.sourceSchema || '',
    targetSchema: state.targetSchema || '',
    sourceJoins: state.sourceJoins,
    description: task.value?.report?.description || '',
    tables,
  }
}

async function finish() {
  if (!state.tableMappings.length) {
    message.warning('请先完成表关联后再生成报告')
    return
  }
  loading.finish = true
  try {
    const report = await buildReport()
    await api.updateTask(props.id, {
      session_state: sessionPayload(),
      status: 'completed',
      report,
    })
    message.success('对比完成，已生成报告')
    router.push({ name: 'compare-report', params: { id: props.id } })
  } finally {
    loading.finish = false
  }
}

watch(
  () => state.tableMappings,
  () => {
    const nextPairs = new Set((state.tableMappings || []).map((m) => `${m.source}::${m.target}`))

    for (const key of Object.keys(state.columnMappings || {})) {
      if (!nextPairs.has(key)) delete state.columnMappings[key]
    }
    for (const key of Object.keys(state.valueAliases || {})) {
      const target = String(key).includes('::') ? String(key).split('::')[1] : ''
      const stillLinked = (state.tableMappings || []).some(
        (m) => `${m.source}::${m.target}` === key || (!!target && m.target === target),
      )
      if (!stillLinked) delete state.valueAliases[key]
    }
    for (const key of Object.keys(state.extractMatchRules || {})) {
      const target = String(key).includes('::') ? String(key).split('::')[1] : ''
      const stillLinked = (state.tableMappings || []).some(
        (m) => `${m.source}::${m.target}` === key || (!!target && m.target === target),
      )
      if (!stillLinked) delete state.extractMatchRules[key]
    }
    for (const key of Object.keys(state.contentStats || {})) {
      const target = String(key).includes('::') ? String(key).split('::')[1] : ''
      const stillLinked = (state.tableMappings || []).some(
        (m) => `${m.source}::${m.target}` === key || (!!target && m.target === target),
      )
      if (!stillLinked) delete state.contentStats[key]
    }
    for (const key of Object.keys(rowSearchByPair || {})) {
      const target = String(key).includes('::') ? String(key).split('::')[1] : ''
      const stillLinked = (state.tableMappings || []).some(
        (m) => `${m.source}::${m.target}` === key || (!!target && m.target === target),
      )
      if (!stillLinked) delete rowSearchByPair[key]
    }

    for (const target of Object.keys(state.sourceJoins || {})) {
      const sourcesForTarget = new Set(
        (state.tableMappings || []).filter((m) => m.target === target).map((m) => m.source),
      )
      if (!sourcesForTarget.size) {
        delete state.sourceJoins[target]
        continue
      }
      // Drop joins that reference a source table no longer linked to this target.
      state.sourceJoins[target] = (state.sourceJoins[target] || []).filter(
        (j) => sourcesForTarget.has(j.leftTable) && sourcesForTarget.has(j.rightTable),
      )
      if (!state.sourceJoins[target].length) delete state.sourceJoins[target]
    }

    for (const target of Object.keys(state.contentCompareFields || {})) {
      const stillLinked = (state.tableMappings || []).some((m) => m.target === target)
      if (!stillLinked) delete state.contentCompareFields[target]
    }

    for (const target of Object.keys(state.displayFields || {})) {
      const stillLinked = (state.tableMappings || []).some((m) => m.target === target)
      if (!stillLinked) delete state.displayFields[target]
    }

    if (!state.tableMappings.length) {
      state.currentTablePair = ''
      return
    }
    const exists = state.tableMappings.some(
      (m) => `${m.source}::${m.target}` === state.currentTablePair,
    )
    if (!exists) {
      state.currentTablePair = `${state.tableMappings[0].source}::${state.tableMappings[0].target}`
    }
  },
  { deep: true },
)

watch(hideMappedRows, async (hidden) => {
  if (skipHideReload || singleCompareActive.value) return
  if (hidden && !hasRowMatch.value) {
    message.warning('请先进行内容对比，再隐藏已配对内容')
    skipHideReload = true
    hideMappedRows.value = false
    await nextTick()
    skipHideReload = false
    return
  }
  rowPage.value = 1
  await loadRows({ restoreMatch: false })
})

onMounted(async () => {
  await loadTask()
  await loadDatabases()
  if (state.sourceDb) await loadSchemas('source', state.sourceDb)
  if (state.targetDb) await loadSchemas('target', state.targetDb)
  if (current.value >= 1 && state.sourceDb && state.targetDb) {
    await loadTables()
    const removed = pruneTableMappingsToCatalog()
    if (removed > 0) {
      message.info(`当前库中有 ${removed} 条失效表映射已清除，请重新连线`)
      await persist()
    }
  }
  if (current.value >= 2 && state.currentTablePair) await loadColumns()
  if (current.value >= 3 && state.currentTablePair) await loadRows({ restoreMatch: false })
})
</script>

<style scoped>
.wizard-card {
  border-radius: 12px;
}

.wizard-top {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  margin-bottom: 20px;
}

.task-name {
  font-size: 18px;
  font-weight: 700;
}

.task-ds {
  margin-top: 8px;
  display: flex;
  align-items: center;
  gap: 8px;
}

.arrow {
  color: #98a2b3;
}

.steps {
  margin-bottom: 20px;
}

.step-body {
  min-height: 560px;
}

.mb {
  margin-bottom: 12px;
}

.db-list {
  max-height: 420px;
  overflow: auto;
  border: 1px solid #eef2f6;
  border-radius: 10px;
}

.db-item {
  padding: 10px 14px;
  border-bottom: 1px solid #f2f4f7;
  cursor: pointer;
}

.db-item:hover {
  background: #f8fafc;
}

.db-item.active {
  background: #eff6ff;
  color: #1d4ed8;
  font-weight: 650;
}

.schema-row {
  margin-top: 12px;
  color: #667085;
  font-size: 13px;
}

.empty {
  padding: 24px;
  text-align: center;
  color: #98a2b3;
}

.pair-bar {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 12px;
  margin-bottom: 12px;
}

.pair-hint {
  color: #98a2b3;
  font-size: 12px;
}

.target-label {
  font-weight: 650;
  color: #344054;
}

.target-chip {
  cursor: pointer;
  user-select: none;
}

.alias-hint {
  margin-bottom: 12px;
  color: #667085;
  font-size: 13px;
  line-height: 1.6;
}

.alias-hint code {
  padding: 1px 6px;
  background: #f2f4f7;
  border-radius: 4px;
  color: #344054;
}

.alias-form {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 8px;
  margin-bottom: 16px;
}

.compare-field-toolbar {
  display: flex;
  gap: 8px;
  margin-bottom: 12px;
}

.compare-field-list {
  max-height: 420px;
  overflow: auto;
  padding: 4px 2px;
  border: 1px solid #eef2f6;
  border-radius: 8px;
  background: #fafbfc;
}

.compare-field-group {
  display: flex;
  flex-direction: column;
  width: 100%;
  gap: 2px;
}

.compare-field-item {
  display: flex;
  align-items: center;
  gap: 8px;
  margin: 0;
  padding: 8px 12px;
  border-radius: 6px;
  cursor: pointer;
}

.compare-field-item:hover {
  background: #f0f5ff;
}

.compare-field-item.checked {
  background: rgba(82, 196, 26, 0.06);
}

.compare-field-mark {
  flex: 0 0 18px;
  width: 18px;
  height: 18px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  border-radius: 50%;
  font-size: 12px;
  font-weight: 700;
  line-height: 1;
}

.compare-field-mark.yes {
  color: #389e0d;
  background: rgba(82, 196, 26, 0.14);
}

.compare-field-mark.no {
  color: #cf1322;
  background: rgba(255, 77, 79, 0.12);
}

.compare-field-item :deep(.ant-checkbox-wrapper) {
  width: 100%;
}

.compare-field-footer {
  display: flex;
  flex-direction: column;
  gap: 12px;
  margin-top: 16px;
  padding-top: 12px;
  border-top: 1px solid #eef2f6;
}

.compare-fuzzy-hint {
  color: #667085;
  font-size: 12px;
  line-height: 1.5;
}

.compare-field-actions {
  display: flex;
  justify-content: flex-end;
  gap: 8px;
  flex-wrap: wrap;
}

.single-compare-banner {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  margin-bottom: 10px;
  padding: 10px 12px;
  border: 1px solid #b7d4ff;
  border-radius: 8px;
  background: #f0f7ff;
  color: #344054;
  font-size: 13px;
}

.single-compare-banner .ok {
  color: #1677ff;
}

.single-compare-banner .bad {
  color: #dc2626;
}

.single-compare-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 16px;
  margin-top: 12px;
}

.single-compare-pane {
  display: flex;
  flex-direction: column;
  gap: 10px;
  min-height: 360px;
}

.single-compare-pane-title {
  font-weight: 600;
  color: #1f2937;
}

.single-compare-list {
  flex: 1;
  max-height: 420px;
  overflow: auto;
  border: 1px solid #e5eaf1;
  border-radius: 8px;
  background: #fafbfd;
  padding: 8px;
}

.single-compare-card {
  padding: 10px 12px;
  border: 1px solid #e5eaf1;
  border-radius: 8px;
  background: #fff;
  cursor: pointer;
  margin-bottom: 8px;
  transition: border-color 0.15s, box-shadow 0.15s;
}

.single-compare-card:hover {
  border-color: #91caff;
}

.single-compare-card.selected {
  border-color: #1677ff;
  box-shadow: 0 0 0 2px rgba(22, 119, 255, 0.15);
  background: #f5f9ff;
}

.single-compare-card-title {
  color: #1f2937;
  font-size: 13px;
  line-height: 1.45;
  word-break: break-all;
}

.single-compare-card-meta {
  margin-top: 4px;
  color: #98a2b3;
  font-size: 12px;
}

.single-compare-empty {
  padding: 24px 12px;
  text-align: center;
  color: #98a2b3;
  font-size: 13px;
}

.single-compare-footer {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  margin-top: 16px;
  padding-top: 12px;
  border-top: 1px solid #eef2f6;
}

.export-rows-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 16px;
  margin-top: 12px;
}

.export-rows-pane {
  display: flex;
  flex-direction: column;
  gap: 8px;
  min-height: 360px;
}

.export-rows-pane-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  font-weight: 600;
}

.export-rows-count {
  color: #98a2b3;
  font-size: 12px;
  font-weight: 400;
}

.export-rows-tools {
  display: flex;
  gap: 8px;
}

.export-rows-list {
  flex: 1;
  max-height: 420px;
  overflow: auto;
  border: 1px solid #e5eaf1;
  border-radius: 8px;
  background: #fafbfd;
  padding: 8px;
}

.export-rows-group {
  display: flex;
  flex-direction: column;
  gap: 4px;
  width: 100%;
}

.export-rows-item {
  display: block;
  padding: 4px 6px;
  border-radius: 6px;
}

.export-rows-item:hover {
  background: #f0f7ff;
}

.export-rows-empty {
  padding: 24px 8px;
  text-align: center;
  color: #98a2b3;
  font-size: 13px;
}

.export-rows-footer {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  margin-top: 16px;
  padding-top: 12px;
  border-top: 1px solid #eef2f6;
}

.export-rows-hint {
  color: #667085;
  font-size: 12px;
}

.alias-eq {
  color: #344054;
  font-weight: 700;
}

.alias-rule {
  font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
  color: #344054;
}

.wizard-footer {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 12px;
  margin-top: 16px;
  padding-top: 16px;
  border-top: 1px solid #eef2f6;
}

.pager {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 8px;
  min-height: 32px;
}

.footer-actions {
  display: flex;
  gap: 8px;
  margin-left: auto;
}
</style>
