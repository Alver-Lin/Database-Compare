<template>
  <div class="mapping-canvas">
    <div class="mapping-toolbar">
      <div class="toolbar-left">
        <a-button type="primary" :loading="comparing" @click="runContent">内容对比</a-button>
        <a-button @click="clearMappings">清除连线</a-button>
        <a-checkbox v-model:checked="syncScroll">同步滚动</a-checkbox>
        <label v-if="props.hideMappedEnabled" class="hide-mapped">
          <a-switch v-model:checked="hideMappedModel" />
          <span>隐藏已配对内容</span>
        </label>
      </div>
      <div class="toolbar-right">
        <a-button v-if="showExport" @click="emit('export-rows')">导出</a-button>
        <span class="toolbar-hint">
          <template v-if="retargetDrag?.active">
            拖到新的目标项上松开，可将该目标上的全部关联线一起切换过去；松开到空白处取消
          </template>
          <template v-else-if="manualLinkDisabled">内容对比自动关联，不可手动连线；点击可查看详情</template>
          <template v-else-if="dotLinkOnly">仅点击蓝色圆点可连线或取消；点击字段块可查看详情。已关联 {{ displayMappedCount }} 项</template>
          <template v-else-if="allowDisplayOnly && allowLeftJoins">
            连线字段参与对比；源侧跨表可一对多互连（同一字段可连多张表），连得越多卡片蓝色越深。拖拽目标侧圆点可整组切换关联。已关联 {{ displayMappedCount }} 项
          </template>
          <template v-else-if="allowLeftJoins">
            源表字段可跨表一对多互连，或先点左侧再点右侧连目标。再次点击同一字段可取消其全部跨表连线。拖拽目标侧圆点可整组切换关联。已关联 {{ displayMappedCount }} 项
          </template>
          <template v-else>先点左侧再点右侧连线，再次点击可取消；拖拽目标侧圆点可将全部关联线切换到其他目标。已关联 {{ displayMappedCount }} 项</template>
        </span>
      </div>
    </div>

    <div v-if="comparing" class="compare-mask">
      <a-spin size="large" />
      <div class="compare-mask-text">{{ comparingText }}</div>
    </div>

    <div v-if="contentResult" class="banner info">
      自动关联 {{ contentResult.matched }} 项，源未匹配 {{ contentResult.leftOnly }} 项，目标未匹配
      {{ contentResult.rightOnly }} 项。{{
        dotLinkOnly
          ? '可点击蓝色圆点手动连线或取消；点击字段块可查看详情。'
          : '可点击左右项手动连线或取消。'
      }}
    </div>

    <div
      ref="rootRef"
      class="mapping-body"
      :class="{ retargeting: !!retargetDrag?.active }"
      :style="bodyLayoutStyle"
    >
      <div class="panel">
        <div class="panel-head">
          <span class="panel-title">
            {{ leftTitle }}
            <span v-if="allowDisplayOnly" class="panel-hint">勾选=仅展示</span>
          </span>
          <span class="panel-count">{{ visibleLeft.length }}/{{ leftTotalCount }}</span>
        </div>
        <div class="panel-search-stack">
          <div
            v-for="(rule, idx) in leftSearchRules"
            :key="rule.id"
            class="panel-search-row"
          >
            <span v-if="idx === 0" class="panel-search-when">当</span>
            <a-select
              v-else
              v-model:value="rule.logic"
              class="panel-search-join"
              :options="searchLogicOptions"
              :dropdown-match-select-width="false"
            />
            <a-tree-select
              v-if="hasLeftSearchFieldGroups"
              v-model:value="rule.field"
              allow-clear
              show-search
              tree-node-filter-prop="title"
              placeholder="搜索字段"
              class="panel-search-field"
              :tree-data="leftSearchFieldTreeData"
              :tree-default-expanded-keys="leftSearchFieldDefaultExpandedKeys"
              :dropdown-style="{ maxHeight: '360px', overflow: 'auto' }"
              :disabled="!hasLeftSearchFields"
            />
            <a-select
              v-else
              v-model:value="rule.field"
              allow-clear
              show-search
              :filter-option="searchFieldFilterOption"
              placeholder="搜索字段"
              class="panel-search-field"
              :options="leftSearchFieldOptions"
              :disabled="!hasLeftSearchFields"
            />
            <a-select
              v-model:value="rule.mode"
              class="panel-search-mode"
              :options="searchModeOptions"
            />
            <a-select
              v-model:value="rule.keywords"
              mode="tags"
              allow-clear
              :token-separators="[',', '，', ';', '；']"
              :placeholder="searchRulePlaceholder(rule, 'left')"
              class="panel-search"
              :max-tag-count="2"
            />
            <a-button
              v-if="leftSearchRules.length > 1"
              class="panel-search-action"
              title="删除此条件"
              @click="removeSearchRule('left', idx)"
            >
              −
            </a-button>
          </div>
          <a-button type="link" class="panel-search-add-link" @click="addSearchRule('left')">
            + 添加筛选条件
          </a-button>
        </div>
        <div class="panel-list" ref="leftListRef" @scroll="onPanelScroll('left')">
          <div v-if="leftLoading" class="list-mask"><a-spin /></div>
          <template v-if="useLeftGroups">
            <div v-for="group in leftGroups" :key="group.key" class="group-block">
              <div
                class="group-head"
                :class="{ active: isLeftGroupExpanded(group.key) }"
                @click="toggleGroup('left', group.key)"
              >
                <span class="group-title">{{ group.title }}</span>
                <span class="group-meta">{{ group.items?.length || 0 }}</span>
                <DownOutlined class="group-arrow" :class="{ open: isLeftGroupExpanded(group.key) }" />
              </div>
              <template v-if="isLeftGroupExpanded(group.key)">
                <div v-if="!visibleItemsForGroup(group).length" class="empty nested">暂无匹配数据</div>
                <div
                  v-for="item in visibleItemsForGroup(group)"
                  :key="item.key"
                  :ref="(el) => setRef('left', item.key, el)"
                  class="map-item"
                  :class="itemClass(item, 'left')"
                  @click="onLeftClick(item)"
                >
                  <a-checkbox
                    v-if="allowDisplayOnly"
                    class="display-check"
                    title="仅展示，不参与对比"
                    :checked="mappedLeft.has(item.key) || isDisplaySelected('left', item.key)"
                    :disabled="mappedLeft.has(item.key)"
                    @click.stop
                    @change="(e) => setDisplaySelected('left', item.key, !!(e?.target?.checked ?? e))"
                  />
                  <div class="item-main">
                    <div class="item-title">{{ item.title }}</div>
                    <div v-if="item.description" class="item-desc">{{ item.description }}</div>
                    <div v-if="item.sample" class="item-sample">字段样例：{{ item.sample }}</div>
                    <div v-if="item.tags?.length" class="item-tags">
                      <a-tag v-for="tag in item.tags" :key="tag">{{ tag }}</a-tag>
                    </div>
                  </div>
                  <button
                    v-if="showClearLinksBtn(item, 'left')"
                    type="button"
                    class="clear-links-btn"
                    title="清除此字段的所有连线"
                    @click.stop="clearFieldLinks(item, 'left')"
                  >
                    <CloseOutlined />
                  </button>
                  <span class="dot" />
                </div>
              </template>
            </div>
          </template>
          <template v-else>
            <div v-if="!visibleLeft.length" class="empty">暂无匹配数据</div>
            <div v-else-if="virtual" class="virtual-phantom" :style="{ height: `${leftWindow.totalHeight}px` }">
              <div class="virtual-window" :style="{ transform: `translateY(${leftWindow.offset}px)` }">
                <div
                  v-for="item in leftWindow.slice"
                  :key="item.key"
                  :ref="(el) => setRef('left', item.key, el)"
                  class="map-item compact"
                  :class="itemClass(item, 'left')"
                  :style="leftCompactStyle"
                  @click="onLeftItemClick(item)"
                >
                  <div class="item-main">
                    <div class="item-title-wrap">
                      <div class="item-title field-stack">
                        <template v-if="item.fieldLines?.length">
                          <div
                            v-for="(line, idx) in item.fieldLines"
                            :key="idx"
                            class="item-line"
                            :class="lineClass(line)"
                          >
                            <span class="line-key">
                              <span
                                v-if="lineMeta(line).displayOnly"
                                class="line-mark display"
                                title="仅展示"
                              >!</span>
                              <span
                                v-else-if="lineMeta(line).compareMark === true"
                                class="line-mark yes"
                              >√</span>
                              <span
                                v-else-if="lineMeta(line).compareMark === false"
                                class="line-mark no"
                              >×</span>
                              <template v-if="lineMeta(line).kind === 'join'">
                                <span class="line-field join-expr" :title="lineMeta(line).label">
                                  {{ lineMeta(line).label || '关联' }}
                                </span>
                              </template>
                              <template v-else>
                                <span class="line-field">{{ lineMeta(line).label }}</span>
                                <span v-if="lineMeta(line).table" class="line-table">{{ lineMeta(line).table }}</span>
                              </template>
                            </span>
                            <span class="line-val">{{ displayLineValue(line) }}</span>
                          </div>
                        </template>
                        <template v-else>{{ item.title }}</template>
                      </div>
                    </div>
                    <div v-if="item.description" class="item-desc">{{ item.description }}</div>
                  </div>
                  <span
                    class="dot"
                    :class="{ clickable: !manualLinkDisabled }"
                    title="点击连线"
                    @click.stop="onLeftDotClick(item)"
                  />
                </div>
              </div>
            </div>
            <template v-else>
              <div
                v-for="item in visibleLeft"
                :key="item.key"
                :ref="(el) => setRef('left', item.key, el)"
                class="map-item"
                :class="itemClass(item, 'left')"
                @click="onLeftClick(item)"
              >
                <a-checkbox
                  v-if="allowDisplayOnly"
                  class="display-check"
                  title="仅展示，不参与对比"
                  :checked="mappedLeft.has(item.key) || isDisplaySelected('left', item.key)"
                  :disabled="mappedLeft.has(item.key)"
                  @click.stop
                  @change="(e) => setDisplaySelected('left', item.key, !!(e?.target?.checked ?? e))"
                />
                <div class="item-main">
                  <div class="item-title">{{ item.title }}</div>
                  <div v-if="item.description" class="item-desc">{{ item.description }}</div>
                  <div v-if="item.sample" class="item-sample">字段样例：{{ item.sample }}</div>
                  <div v-if="item.tags?.length" class="item-tags">
                    <a-tag v-for="tag in item.tags" :key="tag">{{ tag }}</a-tag>
                  </div>
                </div>
                <button
                  v-if="showClearLinksBtn(item, 'left')"
                  type="button"
                  class="clear-links-btn"
                  title="清除此字段的所有连线"
                  @click.stop="clearFieldLinks(item, 'left')"
                >
                  <CloseOutlined />
                </button>
                <span class="dot" />
              </div>
            </template>
          </template>
        </div>
      </div>

      <svg ref="svgRef" class="svg-layer" :width="svgSize.w" :height="svgSize.h">
        <path
          v-for="line in lines"
          :key="line.id"
          :d="line.d"
          class="link-path"
          :class="{
            'left-join-path': line.kind === 'left-join',
            'field-link-path': line.kind === 'field-link',
            match: line.kind === 'field-link' && line.equal,
            mismatch: line.kind === 'field-link' && !line.equal,
            readonly: manualLinkDisabled || line.kind === 'field-link',
            preview: line.kind === 'retarget-preview',
          }"
          @click.stop="onLineClick(line)"
        />
      </svg>

      <div class="panel">
        <div class="panel-head">
          <span class="panel-title">
            {{ rightTitle }}
            <span v-if="allowDisplayOnly" class="panel-hint">勾选=仅展示</span>
          </span>
          <span class="panel-count">{{ visibleRight.length }}/{{ rightTotalCount }}</span>
        </div>
        <div class="panel-search-stack">
          <div
            v-for="(rule, idx) in rightSearchRules"
            :key="rule.id"
            class="panel-search-row"
          >
            <span v-if="idx === 0" class="panel-search-when">当</span>
            <a-select
              v-else
              v-model:value="rule.logic"
              class="panel-search-join"
              :options="searchLogicOptions"
              :dropdown-match-select-width="false"
            />
            <a-select
              v-model:value="rule.field"
              allow-clear
              show-search
              :filter-option="searchFieldFilterOption"
              placeholder="搜索字段"
              class="panel-search-field"
              :options="rightSearchFieldOptions"
              :disabled="!hasRightSearchFields"
            />
            <a-select
              v-model:value="rule.mode"
              class="panel-search-mode"
              :options="searchModeOptions"
            />
            <a-select
              v-model:value="rule.keywords"
              mode="tags"
              allow-clear
              :token-separators="[',', '，', ';', '；']"
              :placeholder="searchRulePlaceholder(rule, 'right')"
              class="panel-search"
              :max-tag-count="2"
            />
            <a-button
              v-if="rightSearchRules.length > 1"
              class="panel-search-action"
              title="删除此条件"
              @click="removeSearchRule('right', idx)"
            >
              −
            </a-button>
          </div>
          <a-button type="link" class="panel-search-add-link" @click="addSearchRule('right')">
            + 添加筛选条件
          </a-button>
        </div>
        <div class="panel-list" ref="rightListRef" @scroll="onPanelScroll('right')">
          <div v-if="rightLoading" class="list-mask"><a-spin /></div>
          <template v-if="useRightGroups">
            <div v-for="group in rightGroups" :key="group.key" class="group-block">
              <div
                class="group-head"
                :class="{ active: expandedRightKey === group.key }"
                @click="toggleGroup('right', group.key)"
              >
                <span class="group-title">{{ group.title }}</span>
                <span class="group-meta">{{ group.items?.length || 0 }}</span>
                <DownOutlined class="group-arrow" :class="{ open: expandedRightKey === group.key }" />
              </div>
              <template v-if="expandedRightKey === group.key">
                <div v-if="!visibleRight.length" class="empty nested">暂无匹配数据</div>
                <div
                  v-for="item in visibleRight"
                  :key="item.key"
                  :ref="(el) => setRef('right', item.key, el)"
                  class="map-item right"
                  :class="itemClass(item, 'right')"
                  :data-key="item.key"
                  @click="onRightClick(item)"
                >
                  <span
                    class="dot"
                    :class="rightDotClass(item)"
                    :title="rightDotTitle(item)"
                    @mousedown.stop="onRightDotPointerDown(item, $event)"
                    @click.stop="onRightDotClick(item)"
                  />
                  <a-checkbox
                    v-if="allowDisplayOnly"
                    class="display-check"
                    title="仅展示，不参与对比"
                    :checked="mappedRight.has(item.key) || isDisplaySelected('right', item.key)"
                    :disabled="mappedRight.has(item.key)"
                    @click.stop
                    @change="(e) => setDisplaySelected('right', item.key, !!(e?.target?.checked ?? e))"
                  />
                  <div class="item-main">
                    <div class="item-title">{{ item.title }}</div>
                    <div v-if="item.description" class="item-desc">{{ item.description }}</div>
                    <div v-if="item.sample" class="item-sample">字段样例：{{ item.sample }}</div>
                    <div v-if="item.tags?.length" class="item-tags">
                      <a-tag v-for="tag in item.tags" :key="tag">{{ tag }}</a-tag>
                    </div>
                  </div>
                  <button
                    v-if="showClearLinksBtn(item, 'right')"
                    type="button"
                    class="clear-links-btn right"
                    title="清除此字段的所有连线"
                    @click.stop="clearFieldLinks(item, 'right')"
                  >
                    <CloseOutlined />
                  </button>
                </div>
              </template>
            </div>
          </template>
          <template v-else>
            <div v-if="!visibleRight.length" class="empty">暂无匹配数据</div>
            <div v-else-if="virtual" class="virtual-phantom" :style="{ height: `${rightWindow.totalHeight}px` }">
              <div class="virtual-window" :style="{ transform: `translateY(${rightWindow.offset}px)` }">
                <div
                  v-for="item in rightWindow.slice"
                  :key="item.key"
                  :ref="(el) => setRef('right', item.key, el)"
                  class="map-item compact right"
                  :class="itemClass(item, 'right')"
                  :data-key="item.key"
                  :style="rightCompactStyle"
                  @click="onRightItemClick(item)"
                >
                  <span
                    class="dot"
                    :class="rightDotClass(item)"
                    :title="rightDotTitle(item)"
                    @mousedown.stop="onRightDotPointerDown(item, $event)"
                    @click.stop="onRightDotClick(item)"
                  />
                  <div class="item-main">
                    <div class="item-title-wrap">
                      <div class="item-title field-stack">
                        <template v-if="item.fieldLines?.length">
                          <div
                            v-for="(line, idx) in item.fieldLines"
                            :key="idx"
                            class="item-line"
                            :class="lineClass(line)"
                          >
                            <span class="line-key">
                              <span
                                v-if="lineMeta(line).displayOnly"
                                class="line-mark display"
                                title="仅展示"
                              >!</span>
                              <span
                                v-else-if="lineMeta(line).compareMark === true"
                                class="line-mark yes"
                              >√</span>
                              <span
                                v-else-if="lineMeta(line).compareMark === false"
                                class="line-mark no"
                              >×</span>
                              <template v-if="lineMeta(line).kind === 'join'">
                                <span class="line-field join-expr" :title="lineMeta(line).label">
                                  {{ lineMeta(line).label || '关联' }}
                                </span>
                              </template>
                              <template v-else>
                                <span class="line-field">{{ lineMeta(line).label }}</span>
                                <span v-if="lineMeta(line).table" class="line-table">{{ lineMeta(line).table }}</span>
                              </template>
                            </span>
                            <span class="line-val">{{ displayLineValue(line) }}</span>
                          </div>
                        </template>
                        <template v-else>{{ item.title }}</template>
                      </div>
                    </div>
                    <div v-if="item.description" class="item-desc">{{ item.description }}</div>
                  </div>
                </div>
              </div>
            </div>
            <template v-else>
              <div
                v-for="item in visibleRight"
                :key="item.key"
                :ref="(el) => setRef('right', item.key, el)"
                class="map-item right"
                :class="itemClass(item, 'right')"
                :data-key="item.key"
                @click="onRightClick(item)"
              >
                <span
                  class="dot"
                  :class="rightDotClass(item)"
                  :title="rightDotTitle(item)"
                  @mousedown.stop="onRightDotPointerDown(item, $event)"
                  @click.stop="onRightDotClick(item)"
                />
                <a-checkbox
                  v-if="allowDisplayOnly"
                  class="display-check"
                  title="仅展示，不参与对比"
                  :checked="mappedRight.has(item.key) || isDisplaySelected('right', item.key)"
                  :disabled="mappedRight.has(item.key)"
                  @click.stop
                  @change="(e) => setDisplaySelected('right', item.key, !!(e?.target?.checked ?? e))"
                />
                <div class="item-main">
                  <div class="item-title">{{ item.title }}</div>
                  <div v-if="item.description" class="item-desc">{{ item.description }}</div>
                  <div v-if="item.sample" class="item-sample">字段样例：{{ item.sample }}</div>
                  <div v-if="item.tags?.length" class="item-tags">
                    <a-tag v-for="tag in item.tags" :key="tag">{{ tag }}</a-tag>
                  </div>
                </div>
                <button
                  v-if="showClearLinksBtn(item, 'right')"
                  type="button"
                  class="clear-links-btn right"
                  title="清除此字段的所有连线"
                  @click.stop="clearFieldLinks(item, 'right')"
                >
                  <CloseOutlined />
                </button>
              </div>
            </template>
          </template>
        </div>
      </div>
    </div>
  </div>

  <a-modal
    v-model:open="detailOpen"
    :title="detailTitle"
    :width="760"
    :footer="null"
    destroy-on-close
    class="record-detail-modal"
  >
    <div class="record-detail">
      <template v-if="detailLines.length">
        <div
          v-for="(line, idx) in detailLines"
          :key="idx"
          class="record-detail-block"
        >
          <div
            class="record-detail-row"
            :class="[lineClass(line), { open: isJoinExpanded(idx) }]"
            @click="hasJoinDetails(line) && toggleJoinDetail(idx, line)"
          >
            <div class="record-detail-key">
              <span
                v-if="lineMeta(line).displayOnly"
                class="line-mark display"
                title="仅展示"
              >!</span>
              <span
                v-else-if="lineMeta(line).compareMark === true"
                class="line-mark yes"
              >√</span>
              <span
                v-else-if="lineMeta(line).compareMark === false"
                class="line-mark no"
              >×</span>
              <template v-if="lineMeta(line).kind === 'join'">
                <span class="record-detail-field join-expr" :title="lineMeta(line).label">
                  {{ lineMeta(line).label || '关联' }}
                </span>
                <DownOutlined
                  v-if="hasJoinDetails(line)"
                  class="join-expand-arrow"
                  :class="{ open: isJoinExpanded(idx) }"
                />
              </template>
              <template v-else>
                <span class="record-detail-field">{{ lineMeta(line).label }}</span>
                <span v-if="lineMeta(line).table" class="record-detail-table">{{ lineMeta(line).table }}</span>
              </template>
            </div>
            <div class="record-detail-val">
              {{ displayLineValue(line) }}
              <span v-if="hasJoinDetails(line) && !isJoinExpanded(idx)" class="join-expand-hint">点击展开</span>
            </div>
          </div>
          <div v-if="hasJoinDetails(line) && isJoinExpanded(idx)" class="join-detail-panel">
            <div
              v-for="detail in line.joinDetails"
              :key="detail.index"
              class="join-detail-item"
            >
              <span class="join-detail-index">{{ detail.index }}</span>
              <span class="join-detail-text">{{ detail.text }}</span>
            </div>
          </div>
        </div>
      </template>
      <pre v-else class="record-detail-fallback">{{ detailItem?.title || '暂无字段内容' }}</pre>
    </div>
  </a-modal>
</template>

<script setup>
import { computed, nextTick, onBeforeUnmount, onMounted, reactive, ref, watch } from 'vue'
import { CloseOutlined, DownOutlined } from '@ant-design/icons-vue'

const ITEM_H_BASE = 60
const BUFFER = 8

const props = defineProps({
  leftTitle: { type: String, default: '源' },
  rightTitle: { type: String, default: '目标' },
  leftItems: { type: Array, default: () => [] },
  rightItems: { type: Array, default: () => [] },
  leftGroups: { type: Array, default: null },
  rightGroups: { type: Array, default: null },
  expandedLeftKey: { type: String, default: null },
  expandedRightKey: { type: String, default: null },
  mappings: { type: Array, default: () => [] },
  leftLoading: { type: Boolean, default: false },
  rightLoading: { type: Boolean, default: false },
  leftCount: { type: Number, default: null },
  rightCount: { type: Number, default: null },
  unit: { type: String, default: '项' },
  hideMappedEnabled: { type: Boolean, default: false },
  hideMapped: { type: Boolean, default: false },
  fullCompareFn: { type: Function, default: null },
  serverSearch: { type: Boolean, default: false },
  searchResetKey: { type: [String, Number], default: '' },
  leftMatchTotal: { type: Number, default: null },
  rightMatchTotal: { type: Number, default: null },
  mappedCount: { type: Number, default: null },
  virtual: { type: Boolean, default: false },
  dimUnmatched: { type: Boolean, default: true },
  allowSharedTarget: { type: Boolean, default: false },
  allowLeftJoins: { type: Boolean, default: false },
  leftJoins: { type: Array, default: () => [] },
  manualLinkDisabled: { type: Boolean, default: false },
  dotLinkOnly: { type: Boolean, default: false },
  allowDisplayOnly: { type: Boolean, default: false },
  displaySelections: {
    type: Object,
    default: () => ({ left: [], right: [] }),
  },
  leftSearchFields: { type: Array, default: () => [] },
  rightSearchFields: { type: Array, default: () => [] },
  leftSearchSeed: { type: Array, default: () => [] },
  rightSearchSeed: { type: Array, default: () => [] },
  leftSearchLogicSeed: { type: String, default: 'and' },
  rightSearchLogicSeed: { type: String, default: 'and' },
  // 单条字段对比连线：{ source, target, sourceLine, targetLine, equal }
  fieldLinks: { type: Array, default: () => [] },
  showExport: { type: Boolean, default: false },
})

const emit = defineEmits([
  'update:mappings',
  'update:leftJoins',
  'update:hideMapped',
  'update:displaySelections',
  'edit-match',
  'clear-match',
  'search',
  'expand-left-group',
  'expand-right-group',
  'export-rows',
])

const rootRef = ref(null)
const svgRef = ref(null)
const selectedLeft = ref('')
const selectedRight = ref('')
const retargetDrag = ref(null)
let suppressRightDotClick = false
const detailOpen = ref(false)
const detailSide = ref('left')
const detailItem = ref(null)
const expandedJoinKeys = ref(new Set())

const detailTitle = computed(() =>
  detailSide.value === 'left' ? `${props.leftTitle} · 全部字段` : `${props.rightTitle} · 全部字段`,
)
const detailLines = computed(() => detailItem.value?.fieldLines || [])

function showRecordDetail(side, item) {
  if (!props.virtual || !item) return
  detailSide.value = side
  detailItem.value = item
  expandedJoinKeys.value = new Set()
  detailOpen.value = true
}

function closeRecordDetail() {
  detailOpen.value = false
  detailItem.value = null
  expandedJoinKeys.value = new Set()
}

function joinDetailKey(idx) {
  return `${detailSide.value}:${idx}`
}

function hasJoinDetails(line) {
  return !!(line && typeof line === 'object' && Array.isArray(line.joinDetails) && line.joinDetails.length)
}

function isJoinExpanded(idx) {
  return expandedJoinKeys.value.has(joinDetailKey(idx))
}

function toggleJoinDetail(idx, line) {
  if (!hasJoinDetails(line)) return
  const key = joinDetailKey(idx)
  const next = new Set(expandedJoinKeys.value)
  if (next.has(key)) next.delete(key)
  else next.add(key)
  expandedJoinKeys.value = next
}
const highlighted = ref(false)
const comparing = ref(false)
const syncScroll = ref(false)
let searchRuleSeq = 1
function createSearchRule(logic = 'and') {
  return {
    id: `sr-${searchRuleSeq++}`,
    field: undefined,
    mode: 'include',
    keywords: [],
    logic: normalizeSearchLogic(logic),
  }
}

function normalizeSearchLogic(logic) {
  return String(logic || 'and').trim().toLowerCase() === 'or' ? 'or' : 'and'
}

function rulesFromSeed(seed, fallbackLogic = 'and') {
  const fallback = normalizeSearchLogic(fallbackLogic)
  if (!Array.isArray(seed) || !seed.length) return [createSearchRule()]
  return seed.map((item, idx) => ({
    id: `sr-${searchRuleSeq++}`,
    field: item?.field || undefined,
    mode: normalizeSearchMode(item?.mode, item?.negate),
    keywords: normalizeKeywords(item?.keywords),
    logic: idx === 0 ? 'and' : normalizeSearchLogic(item?.logic || fallback),
  }))
}

function applySearchSeed() {
  leftSearchRules.value = rulesFromSeed(props.leftSearchSeed, props.leftSearchLogicSeed)
  rightSearchRules.value = rulesFromSeed(props.rightSearchSeed, props.rightSearchLogicSeed)
}

const leftSearchRules = ref([createSearchRule()])
const rightSearchRules = ref([createSearchRule()])
const contentResult = ref(null)
const expandedLeftKey = ref('')
const expandedLeftKeys = ref([])
const expandedRightKey = ref('')
const svgSize = reactive({ w: 0, h: 0 })
const lines = ref([])
const leftListRef = ref(null)
const rightListRef = ref(null)
const leftScrollTop = ref(0)
const rightScrollTop = ref(0)
const viewportH = ref(500)
const leftRefs = {}
const rightRefs = {}
let syncingScroll = false
let leftSearchTimer = 0
let rightSearchTimer = 0

const useLeftGroups = computed(() => Array.isArray(props.leftGroups) && props.leftGroups.length > 0)
const useRightGroups = computed(() => Array.isArray(props.rightGroups) && props.rightGroups.length > 0)
const multiExpandLeft = computed(() => props.allowLeftJoins && useLeftGroups.value)

const leftSearchFieldOptions = computed(() => normalizeSearchFieldOptions(props.leftSearchFields))

const rightSearchFieldOptions = computed(() => normalizeSearchFieldOptions(props.rightSearchFields))

function normalizeSearchFieldOptions(raw) {
  const list = Array.isArray(raw) ? raw : []
  const groups = []
  const flat = []
  for (const item of list) {
    if (typeof item === 'string') {
      if (!item) continue
      flat.push({ value: item, label: item })
      continue
    }
    if (!item || typeof item !== 'object') continue
    if (Array.isArray(item.options)) {
      const children = item.options
        .map((child) => {
          if (typeof child === 'string') return child ? { value: child, label: child } : null
          if (!child?.value) return null
          return { value: child.value, label: child.label || child.value }
        })
        .filter(Boolean)
      if (!children.length) continue
      groups.push({
        label: item.label || item.value || '字段',
        options: children,
      })
      continue
    }
    if (!item.value) continue
    flat.push({ value: item.value, label: item.label || item.value })
  }
  if (groups.length && flat.length) {
    groups.push({ label: '其他', options: flat })
    return groups
  }
  if (groups.length) return groups
  return flat
}

function flattenSearchFieldOptions(options) {
  const result = []
  for (const item of options || []) {
    if (Array.isArray(item?.options)) {
      for (const child of item.options) {
        if (child?.value) result.push(child)
      }
    } else if (item?.value) {
      result.push(item)
    }
  }
  return result
}

const leftSearchFieldLeaves = computed(() => flattenSearchFieldOptions(leftSearchFieldOptions.value))
const rightSearchFieldLeaves = computed(() => flattenSearchFieldOptions(rightSearchFieldOptions.value))
const hasLeftSearchFields = computed(() => leftSearchFieldLeaves.value.length > 0)
const hasRightSearchFields = computed(() => rightSearchFieldLeaves.value.length > 0)
const hasLeftSearchFieldGroups = computed(() =>
  (leftSearchFieldOptions.value || []).some((item) => Array.isArray(item?.options)),
)

const leftSearchFieldTreeData = computed(() =>
  (leftSearchFieldOptions.value || [])
    .filter((item) => Array.isArray(item?.options) && item.options.length)
    .map((group, index) => ({
      title: group.label,
      value: `__group__${index}__${group.label}`,
      selectable: false,
      children: group.options.map((child) => ({
        title: child.label || child.value,
        value: child.value,
        isLeaf: true,
      })),
    })),
)

const leftSearchFieldDefaultExpandedKeys = computed(() => {
  const first = leftSearchFieldTreeData.value[0]
  return first ? [first.value] : []
})

const searchModeOptions = [
  { value: 'include', label: '包含' },
  { value: 'exclude', label: '不包含' },
  { value: 'equals', label: '等于' },
  { value: 'not_equals', label: '不等于' },
]

const searchLogicOptions = [
  { value: 'and', label: '且' },
  { value: 'or', label: '或' },
]

function normalizeSearchMode(mode, negate = false) {
  const value = String(mode || '').trim()
  if (['include', 'exclude', 'equals', 'not_equals'].includes(value)) return value
  return negate ? 'exclude' : 'include'
}

function leftSearchFieldLabel(value) {
  if (!value) return ''
  const sep = String(value).indexOf('::')
  if (sep > 0) {
    const table = String(value).slice(0, sep)
    const field = String(value).slice(sep + 2)
    return `${table}.${field}`
  }
  return leftSearchFieldLeaves.value.find((item) => item.value === value)?.label || value
}

function rightSearchFieldLabel(value) {
  return rightSearchFieldLeaves.value.find((item) => item.value === value)?.label || value
}

function searchFieldFilterOption(input, option) {
  const keyword = String(input || '').trim().toLowerCase()
  if (!keyword) return true
  const label = String(option?.label ?? '').toLowerCase()
  const value = String(option?.value ?? '').toLowerCase()
  // 支持搜表名（value 形如 sys_org::name）或字段名
  return label.includes(keyword) || value.includes(keyword) || value.replaceAll('::', '.').includes(keyword)
}

function searchRulePlaceholder(rule, side = 'left') {
  const mode = normalizeSearchMode(rule?.mode)
  const actionMap = {
    include: '模糊搜索',
    exclude: '模糊排除',
    equals: '精确匹配',
    not_equals: '精确排除',
  }
  const action = actionMap[mode] || '搜索'
  if (rule?.field) {
    const label =
      side === 'right' ? rightSearchFieldLabel(rule.field) : leftSearchFieldLabel(rule.field)
    return `在「${label}」中${action}，回车添加多个值`
  }
  return `输入值后回车添加，可${action}多个值`
}

function addSearchRule(side) {
  const rules = side === 'left' ? leftSearchRules : rightSearchRules
  const prevLogic = rules.value[rules.value.length - 1]?.logic || 'and'
  rules.value = [...rules.value, createSearchRule(prevLogic)]
  scheduleEmitSearch()
}

function removeSearchRule(side, index) {
  const rules = side === 'left' ? leftSearchRules : rightSearchRules
  if (rules.value.length <= 1) return
  rules.value = rules.value.filter((_, i) => i !== index)
  if (rules.value[0]) rules.value[0].logic = 'and'
  scheduleEmitSearch()
}

function activeSearchConditions(rules) {
  return (rules || [])
    .map((rule) => {
      const mode = normalizeSearchMode(rule.mode)
      return {
        field: rule.field || '',
        keywords: normalizeKeywords(rule.keywords),
        mode,
        negate: mode === 'exclude' || mode === 'not_equals',
        logic: normalizeSearchLogic(rule.logic),
      }
    })
    .filter((rule) => rule.keywords.length)
}

function deriveSearchLogic(conditions) {
  const list = Array.isArray(conditions) ? conditions : []
  if (list.length <= 1) return 'and'
  const logics = list.slice(1).map((item) => normalizeSearchLogic(item.logic))
  if (logics.length && logics.every((item) => item === logics[0])) return logics[0]
  return logics[0] || 'and'
}

const activeLeftItems = computed(() => {
  if (!useLeftGroups.value) return props.leftItems
  if (multiExpandLeft.value) {
    const open = new Set(expandedLeftKeys.value)
    return props.leftGroups.filter((g) => open.has(g.key)).flatMap((g) => g.items || [])
  }
  const group = props.leftGroups.find((g) => g.key === expandedLeftKey.value)
  return group?.items || []
})

const activeRightItems = computed(() => {
  if (!useRightGroups.value) return props.rightItems
  const group = props.rightGroups.find((g) => g.key === expandedRightKey.value)
  return group?.items || []
})

function isLeftGroupExpanded(key) {
  if (multiExpandLeft.value) return expandedLeftKeys.value.includes(key)
  return expandedLeftKey.value === key
}

function visibleItemsForGroup(group) {
  const items = group?.items || []
  return items.filter((item) => {
    if (
      props.hideMappedEnabled &&
      props.hideMapped &&
      !props.serverSearch &&
      mappedLeft.value.has(item.key)
    ) {
      return false
    }
    if (props.serverSearch) return true
    return matchSearchRules(item, leftSearchRules.value, props.leftSearchLogicSeed)
  })
}

function groupKeyOf(itemOrKey) {
  if (itemOrKey && typeof itemOrKey === 'object') {
    if (itemOrKey.groupKey) return itemOrKey.groupKey
    const key = itemOrKey.key
    const sep = String(key).indexOf('::')
    return sep > 0 ? String(key).slice(0, sep) : ''
  }
  const key = String(itemOrKey || '')
  const sep = key.indexOf('::')
  return sep > 0 ? key.slice(0, sep) : ''
}

let leftExpandInitialized = false
let leftExpandGroupsSig = ''

function syncExpandedGroup(side) {
  const groups = side === 'left' ? props.leftGroups : props.rightGroups
  if (side === 'left' && multiExpandLeft.value) {
    if (!groups?.length) {
      expandedLeftKeys.value = []
      leftExpandInitialized = false
      leftExpandGroupsSig = ''
      return
    }
    const sig = groups.map((g) => g.key).join('\0')
    const valid = new Set(groups.map((g) => g.key))
    const kept = expandedLeftKeys.value.filter((k) => valid.has(k))
    if (!leftExpandInitialized || sig !== leftExpandGroupsSig) {
      expandedLeftKeys.value = groups.map((g) => g.key)
      leftExpandInitialized = true
      leftExpandGroupsSig = sig
      return
    }
    expandedLeftKeys.value = kept
    return
  }
  const current = side === 'left' ? expandedLeftKey : expandedRightKey
  const preferred = side === 'left' ? props.expandedLeftKey : props.expandedRightKey
  if (!groups?.length) {
    current.value = ''
    return
  }
  if (preferred && groups.some((g) => g.key === preferred)) {
    current.value = preferred
    return
  }
  if (!groups.some((g) => g.key === current.value)) {
    current.value = groups[0].key
    emit(side === 'left' ? 'expand-left-group' : 'expand-right-group', current.value)
  }
}

function toggleGroup(side, key) {
  if (side === 'left' && multiExpandLeft.value) {
    const set = new Set(expandedLeftKeys.value)
    if (set.has(key)) set.delete(key)
    else set.add(key)
    expandedLeftKeys.value = [...set]
    selectedLeft.value = ''
    nextTick(scheduleDraw)
    return
  }
  if (side === 'left') {
    if (expandedLeftKey.value === key) {
      expandedLeftKey.value = ''
      selectedLeft.value = ''
      nextTick(scheduleDraw)
      return
    }
    expandedLeftKey.value = key
    selectedLeft.value = ''
    leftListRef.value && (leftListRef.value.scrollTop = 0)
    leftScrollTop.value = 0
    emit('expand-left-group', key)
  } else {
    if (expandedRightKey.value === key) {
      expandedRightKey.value = ''
      selectedRight.value = ''
      nextTick(scheduleDraw)
      return
    }
    expandedRightKey.value = key
    selectedRight.value = ''
    rightListRef.value && (rightListRef.value.scrollTop = 0)
    rightScrollTop.value = 0
    emit('expand-right-group', key)
  }
  nextTick(scheduleDraw)
}

const hideMappedModel = computed({
  get: () => props.hideMapped,
  set: (value) => emit('update:hideMapped', value),
})
const LINE_ROW_H = 24
const LINE_GAP = 3
const CARD_PAD_Y = 16

const itemH = computed(() => {
  if (!props.virtual) return ITEM_H_BASE
  const lineCount = Math.max(
    sampleLineCount(props.leftItems),
    sampleLineCount(props.rightItems),
  )
  const contentH =
    CARD_PAD_Y + lineCount * LINE_ROW_H + Math.max(0, lineCount - 1) * LINE_GAP
  return Math.max(ITEM_H_BASE, contentH + 8)
})

function longestFieldLineLen(items) {
  let maxLen = 0
  for (const item of items || []) {
    const lines = item.fieldLines || []
    if (!lines.length) {
      maxLen = Math.max(maxLen, String(item.title || '').length)
      continue
    }
    for (const line of lines) {
      const meta = lineMeta(line)
      maxLen = Math.max(maxLen, String(meta.value || meta.text || '').length)
    }
  }
  return maxLen
}

function sampleLineCount(items) {
  let max = 1
  for (const item of (items || []).slice(0, 80)) {
    max = Math.max(max, item?.lineCount || item?.fieldLines?.length || 1)
  }
  return max
}

const fieldLayoutStats = computed(() => {
  const leftLines = sampleLineCount(props.leftItems)
  const rightLines = sampleLineCount(props.rightItems)
  const lineCount = Math.max(leftLines, rightLines)
  const leftMaxLen = longestFieldLineLen(props.leftItems.slice(0, 30))
  const rightMaxLen = longestFieldLineLen(props.rightItems.slice(0, 30))
  return {
    lineCount,
    leftLines,
    rightLines,
    leftMaxLen,
    rightMaxLen,
    maxLen: Math.max(leftMaxLen, rightMaxLen),
  }
})

const bodyLayoutStyle = computed(() => {
  if (!props.virtual) return undefined
  const leftEmpty = !(props.leftItems && props.leftItems.length)
  const rightEmpty = !(props.rightItems && props.rightItems.length)
  // 一侧无数据时保持等宽，避免筛选项被挤乱
  if (leftEmpty || rightEmpty) {
    return { gridTemplateColumns: 'minmax(0, 1fr) minmax(0, 1fr)' }
  }
  const { leftLines, rightLines, leftMaxLen, rightMaxLen } = fieldLayoutStats.value
  let leftFr = 1
  let rightFr = 1
  if (leftLines >= 4 || leftMaxLen >= 36) leftFr = 1.2
  if (leftLines >= 6 || leftMaxLen >= 52) leftFr = 1.35
  if (leftLines >= 8 || leftMaxLen >= 72) leftFr = 1.5
  if (rightLines >= 4 || rightMaxLen >= 36) rightFr = 1.2
  if (rightLines >= 6 || rightMaxLen >= 52) rightFr = 1.35
  if (rightLines >= 8 || rightMaxLen >= 72) rightFr = 1.5
  return {
    gridTemplateColumns: `minmax(0, ${leftFr}fr) minmax(0, ${rightFr}fr)`,
  }
})

const compactItemStyle = computed(() => {
  if (!props.virtual) return undefined
  const style = {
    height: `${itemH.value - 8}px`,
    minHeight: `${itemH.value - 8}px`,
  }
  return style
})

const leftCompactStyle = computed(() => {
  const style = { ...(compactItemStyle.value || {}) }
  const maxLen = fieldLayoutStats.value.leftMaxLen
  if (maxLen >= 36) {
    style.minWidth = `${Math.min(640, Math.max(220, Math.round(maxLen * 7.2 + 40)))}px`
  }
  return Object.keys(style).length ? style : undefined
})

const rightCompactStyle = computed(() => {
  const style = { ...(compactItemStyle.value || {}) }
  const maxLen = fieldLayoutStats.value.rightMaxLen
  if (maxLen >= 36) {
    style.minWidth = `${Math.min(640, Math.max(220, Math.round(maxLen * 7.2 + 40)))}px`
  }
  return Object.keys(style).length ? style : undefined
})
const displayMappedCount = computed(() => {
  if (props.mappedCount != null) return props.mappedCount
  return props.mappings.length + (props.allowLeftJoins ? props.leftJoins.length : 0)
})
const leftTotalCount = computed(() => {
  if (props.leftMatchTotal != null) return props.leftMatchTotal
  if (props.leftCount != null) return props.leftCount
  return activeLeftItems.value.length
})
const rightTotalCount = computed(() => {
  if (props.rightMatchTotal != null) return props.rightMatchTotal
  if (props.rightCount != null) return props.rightCount
  return activeRightItems.value.length
})
const comparingText = computed(() =>
  props.fullCompareFn ? '正在按当前筛选条件比对...' : '正在对比，请稍候...',
)
const mappedLeft = computed(() => {
  const set = new Set(props.mappings.map((m) => m.source))
  if (props.allowLeftJoins) {
    for (const m of props.leftJoins || []) {
      set.add(m.source)
      set.add(m.target)
    }
  }
  for (const item of activeLeftItems.value) {
    if (item.mapped) set.add(item.key)
  }
  return set
})

/** 源侧跨表关联度数：同一字段连出越多，一对多程度越高 */
const leftJoinDegree = computed(() => {
  const deg = new Map()
  if (!props.allowLeftJoins) return deg
  for (const m of props.leftJoins || []) {
    if (!m?.source || !m?.target) continue
    deg.set(m.source, (deg.get(m.source) || 0) + 1)
    deg.set(m.target, (deg.get(m.target) || 0) + 1)
  }
  return deg
})
const mappedRight = computed(() => {
  const set = new Set(props.mappings.map((m) => m.target))
  for (const item of activeRightItems.value) {
    if (item.mapped) set.add(item.key)
  }
  return set
})
const mappingBySource = computed(() => {
  const map = new Map()
  for (const item of props.mappings) map.set(item.source, item)
  return map
})
const mappingByTarget = computed(() => {
  const map = new Map()
  for (const item of props.mappings) map.set(item.target, item)
  return map
})

const mappingsByTarget = computed(() => {
  const map = new Map()
  for (const item of props.mappings) {
    const list = map.get(item.target) || []
    list.push(item)
    map.set(item.target, list)
  }
  return map
})

function itemClass(item, side) {
  const selected = side === 'left' ? selectedLeft.value === item.key : selectedRight.value === item.key
  const mapped = side === 'left' ? mappedLeft.value.has(item.key) : mappedRight.value.has(item.key)
  const displayOnly = props.allowDisplayOnly && isDisplaySelected(side, item.key) && !mapped
  const joinDeg = side === 'left' && props.allowLeftJoins ? leftJoinDegree.value.get(item.key) || 0 : 0
  const drag = retargetDrag.value
  const retargetFrom = side === 'right' && drag?.active && drag.fromTarget === item.key
  const retargetDrop =
    side === 'right' && drag?.active && drag.hoverTarget === item.key && drag.hoverTarget !== drag.fromTarget
  return {
    selected,
    mapped,
    'display-only': displayOnly,
    unmatched: props.dimUnmatched && highlighted.value && !mapped,
    // 仅一对多（连出≥2）加深卡片，一对一跨表不改变底色
    'left-join-multi': joinDeg > 1,
    [`left-join-deg-${Math.min(joinDeg, 5)}`]: joinDeg > 1,
    'retarget-from': retargetFrom,
    'retarget-drop': retargetDrop,
  }
}

function canRetargetRight(item) {
  if (props.manualLinkDisabled || !item?.key) return false
  // 行内容对比的关联由服务端缓存维护，整组拖拽改目标仅用于表/字段映射
  if (props.virtual && props.dotLinkOnly) return false
  return (mappingsByTarget.value.get(item.key) || []).length > 0
}

function rightDotClass(item) {
  const drag = retargetDrag.value
  return {
    clickable: !props.manualLinkDisabled,
    draggable: canRetargetRight(item),
    dragging: !!(drag?.active && drag.fromTarget === item.key),
  }
}

function rightDotTitle(item) {
  if (props.manualLinkDisabled) return ''
  if (canRetargetRight(item)) {
    return '拖拽可将全部关联线切换到其他目标；点击可连线或取消'
  }
  return '点击连线'
}

function displaySelectionList(side) {
  const raw = props.displaySelections || {}
  const list = side === 'left' ? raw.left : raw.right
  return Array.isArray(list) ? list : []
}

function isDisplaySelected(side, key) {
  return displaySelectionList(side).includes(key)
}

function setDisplaySelected(side, key, checked) {
  if (!props.allowDisplayOnly) return
  const left = new Set(displaySelectionList('left'))
  const right = new Set(displaySelectionList('right'))
  const set = side === 'left' ? left : right
  if (checked) set.add(key)
  else set.delete(key)
  emit('update:displaySelections', {
    left: [...left],
    right: [...right],
  })
}

function itemText(item) {
  const fieldText = (item.fieldLines || []).map((line) => lineMeta(line).text)
  return [
    item.title,
    item.description,
    item.sample,
    item.matchValue,
    ...fieldText,
    ...(item.tags || []),
  ]
    .filter(Boolean)
    .join(' ')
}

function lineMeta(line) {
  if (line && typeof line === 'object') {
    const label = line.label ?? line.field ?? ''
    let value
    if (Object.prototype.hasOwnProperty.call(line, 'value') && line.value != null) {
      value = String(line.value)
    } else {
      value = parseLineValue(line.text)
    }
    const kind = line.kind || (label === '关联' ? 'join' : 'field')
    return {
      kind,
      table: line.table || '',
      label: label || (kind === 'join' ? '关联' : ''),
      value,
      text: line.text ?? `${label}=${value}`,
      unequal: !!line.unequal,
      compareMark: line.compareMark === true || line.compareMark === false ? line.compareMark : null,
      displayOnly: !!line.displayOnly,
      expandable: !!(line.expandable && Array.isArray(line.joinDetails) && line.joinDetails.length),
      joinDetails: Array.isArray(line.joinDetails) ? line.joinDetails : [],
    }
  }
  const text = String(line ?? '')
  const eq = text.indexOf('=')
  if (eq > 0) {
    return {
      kind: 'field',
      table: '',
      label: text.slice(0, eq),
      value: text.slice(eq + 1),
      text,
      unequal: false,
      compareMark: null,
      displayOnly: false,
    }
  }
  return { kind: 'field', table: '', label: '', value: text, text, unequal: false, compareMark: null, displayOnly: false }
}

function parseLineValue(text) {
  const raw = String(text || '')
  const eq = raw.lastIndexOf('=')
  return eq >= 0 ? raw.slice(eq + 1).trim() : raw
}

function lineClass(line) {
  const meta = lineMeta(line)
  return {
    unequal: meta.unequal,
    join: meta.kind === 'join',
    'display-only': !!meta.displayOnly,
    expandable: !!meta.expandable,
  }
}

function displayLineValue(line) {
  const meta = lineMeta(line)
  const value = meta.value
  if (value === null || value === undefined) return 'NULL'
  const text = String(value).trim()
  if (!text || text.toUpperCase() === 'NULL') return 'NULL'
  return String(value)
}

function normalizeKeywords(value) {
  if (Array.isArray(value)) {
    return value.map((item) => String(item ?? '').trim()).filter(Boolean)
  }
  const text = String(value ?? '').trim()
  return text ? [text] : []
}

function isNullSearchKeyword(term) {
  return String(term || '').trim().toUpperCase() === 'NULL'
}

function isEmptySearchValue(value) {
  if (value === null || value === undefined) return true
  const text = String(value).trim()
  return !text || text.toUpperCase() === 'NULL'
}

function fieldSearchText(item, fieldKeys = []) {
  const keys = normalizeKeywords(fieldKeys)
  if (keys.length && item?.fieldLines?.length) {
    const keySet = new Set(keys)
    return item.fieldLines
      .map((line) => lineMeta(line))
      .filter((meta) => meta.kind !== 'join')
      .filter((meta) => {
        const key = meta.field || meta.label
        const qualified = meta.table ? `${meta.table}::${key}` : key
        return keySet.has(key) || keySet.has(qualified) || keySet.has(meta.label)
      })
      .map((meta) => (isEmptySearchValue(meta.value) ? 'NULL' : String(meta.value ?? '')))
      .join(' ')
      .toLowerCase()
  }
  return itemText(item).toLowerCase()
}

function fuzzyMatchTerm(text, keyword) {
  const kw = String(keyword || '').trim().toLowerCase()
  if (!kw) return true
  const haystack = String(text || '').toLowerCase()
  const compact = haystack.replace(/[\s_\-./]/g, '')
  return kw.split(/\s+/).every((part) => {
    if (!part) return true
    if (haystack.includes(part)) return true
    const compactPart = part.replace(/[\s_\-./]/g, '')
    return !!(compactPart && compact.includes(compactPart))
  })
}

function fieldExactValues(item, fieldKeys = []) {
  const keys = normalizeKeywords(fieldKeys)
  if (keys.length && item?.fieldLines?.length) {
    const keySet = new Set(keys)
    return item.fieldLines
      .map((line) => lineMeta(line))
      .filter((meta) => meta.kind !== 'join')
      .filter((meta) => {
        const key = meta.field || meta.label
        const qualified = meta.table ? `${meta.table}::${key}` : key
        return keySet.has(key) || keySet.has(qualified) || keySet.has(meta.label)
      })
      .map((meta) => String(meta.value ?? '').trim())
  }
  if (item?.fieldLines?.length) {
    return item.fieldLines
      .map((line) => lineMeta(line))
      .filter((meta) => meta.kind !== 'join')
      .map((meta) => String(meta.value ?? '').trim())
  }
  return [String(item?.title ?? '').trim()].filter(Boolean)
}

function fuzzyMatch(item, keywords, fieldKeys = [], negate = false) {
  const terms = normalizeKeywords(keywords)
  if (!terms.length) return true
  const nullTerms = terms.filter(isNullSearchKeyword)
  const otherTerms = terms.filter((term) => !isNullSearchKeyword(term))
  let hit = false
  if (nullTerms.length) {
    const values = fieldExactValues(item, fieldKeys)
    hit = values.some((value) => isEmptySearchValue(value))
  }
  if (!hit && otherTerms.length) {
    const text = fieldSearchText(item, fieldKeys)
    hit = otherTerms.some((term) => fuzzyMatchTerm(text, term))
  }
  return negate ? !hit : hit
}

function exactMatch(item, keywords, fieldKeys = [], negate = false) {
  const terms = normalizeKeywords(keywords)
  if (!terms.length) return true
  const values = fieldExactValues(item, fieldKeys)
  const nullWanted = terms.some(isNullSearchKeyword)
  const plainTerms = terms.filter((term) => !isNullSearchKeyword(term)).map((term) => String(term).trim())
  const hit = values.some((value) => {
    if (isEmptySearchValue(value)) return nullWanted
    return plainTerms.includes(String(value).trim())
  })
  return negate ? !hit : hit
}

function matchSearchRules(item, rules, fallbackLogic = 'and') {
  const conditions = activeSearchConditions(rules)
  if (!conditions.length) return true
  let result = null
  for (let i = 0; i < conditions.length; i += 1) {
    const cond = conditions[i]
    const fields = cond.field ? [cond.field] : []
    let hit = false
    if (cond.mode === 'equals') hit = exactMatch(item, cond.keywords, fields, false)
    else if (cond.mode === 'not_equals') hit = exactMatch(item, cond.keywords, fields, true)
    else hit = fuzzyMatch(item, cond.keywords, fields, cond.mode === 'exclude')
    if (i === 0) {
      result = hit
      continue
    }
    const op = normalizeSearchLogic(cond.logic || fallbackLogic)
    result = op === 'or' ? result || hit : result && hit
  }
  return !!result
}

const visibleLeft = computed(() =>
  activeLeftItems.value.filter((item) => {
    // 服务端已按未配对过滤时，不再用本地 mapped 状态二次隐藏，避免误伤
    if (
      props.hideMappedEnabled &&
      props.hideMapped &&
      !props.serverSearch &&
      mappedLeft.value.has(item.key)
    ) {
      return false
    }
    if (props.serverSearch) return true
    return matchSearchRules(item, leftSearchRules.value, props.leftSearchLogicSeed)
  }),
)

const visibleRight = computed(() =>
  activeRightItems.value.filter((item) => {
    if (
      props.hideMappedEnabled &&
      props.hideMapped &&
      !props.serverSearch &&
      mappedRight.value.has(item.key)
    ) {
      return false
    }
    if (props.serverSearch) return true
    return matchSearchRules(item, rightSearchRules.value, props.rightSearchLogicSeed)
  }),
)

const leftIndexMap = computed(() => {
  const map = new Map()
  visibleLeft.value.forEach((item, index) => map.set(item.key, index))
  return map
})

const rightIndexMap = computed(() => {
  const map = new Map()
  visibleRight.value.forEach((item, index) => map.set(item.key, index))
  return map
})

function makeWindow(items, scrollTop) {
  const h = itemH.value
  const start = Math.max(0, Math.floor(scrollTop / h) - BUFFER)
  const count = Math.ceil(viewportH.value / h) + BUFFER * 2
  const end = Math.min(items.length, start + count)
  return {
    slice: items.slice(start, end),
    offset: start * h,
    totalHeight: items.length * h,
  }
}

const leftWindow = computed(() => makeWindow(visibleLeft.value, leftScrollTop.value))
const rightWindow = computed(() => makeWindow(visibleRight.value, rightScrollTop.value))

function setRef(side, key, el) {
  const bag = side === 'left' ? leftRefs : rightRefs
  if (el) bag[key] = el
  else delete bag[key]
}

function emitMappings(next) {
  emit('update:mappings', next)
}

function emitLeftJoins(next) {
  emit('update:leftJoins', next)
}

function findLeftJoinsForKey(key) {
  return (props.leftJoins || []).filter((m) => m.source === key || m.target === key)
}

function hasLeftJoin(source, target) {
  return (props.leftJoins || []).some(
    (m) =>
      (m.source === source && m.target === target) ||
      (m.source === target && m.target === source),
  )
}

function linkLeftJoin(source, target) {
  if (!source || !target || source === target) return
  // 已存在则取消该条；否则追加，允许同一字段一对多连到多张表
  if (hasLeftJoin(source, target)) {
    removeLeftJoin(source, target)
    return
  }
  emitLeftJoins([...(props.leftJoins || []), { source, target }])
}

function removeLeftJoin(source, target) {
  emitLeftJoins(
    (props.leftJoins || []).filter(
      (m) =>
        !(
          (m.source === source && m.target === target) ||
          (m.source === target && m.target === source)
        ),
    ),
  )
}

function removeLeftJoinsForKey(key) {
  emitLeftJoins((props.leftJoins || []).filter((m) => m.source !== key && m.target !== key))
}

function showClearLinksBtn(item, side) {
  if (props.manualLinkDisabled || !item?.key) return false
  if (side === 'left') {
    if (mappedLeft.value.has(item.key)) return true
    return props.allowLeftJoins && findLeftJoinsForKey(item.key).length > 0
  }
  return (mappingsByTarget.value.get(item.key) || []).length > 0
}

function clearFieldLinks(item, side = 'left') {
  if (props.manualLinkDisabled || !item?.key) return
  if (side === 'left') {
    const hadMapping = mappedLeft.value.has(item.key)
    const hadJoins = props.allowLeftJoins && findLeftJoinsForKey(item.key).length > 0
    if (!hadMapping && !hadJoins) return
    if (hadMapping) {
      emitMappings(props.mappings.filter((m) => m.source !== item.key))
    }
    if (hadJoins) removeLeftJoinsForKey(item.key)
    if (selectedLeft.value === item.key) {
      selectedLeft.value = ''
      selectedRight.value = ''
      closeRecordDetail()
    }
    return
  }
  const linked = mappingsByTarget.value.get(item.key) || []
  if (!linked.length) return
  emitMappings(props.mappings.filter((m) => m.target !== item.key))
  if (selectedRight.value === item.key) {
    selectedRight.value = ''
    selectedLeft.value = ''
    closeRecordDetail()
  }
}

function onLineClick(line) {
  if (line.kind === 'field-link' || line.kind === 'retarget-preview') return
  if (props.manualLinkDisabled) return
  if (line.kind === 'left-join') removeLeftJoin(line.source, line.target)
  else removeMapping(line.source, line.target)
}

function openLeftDetail(item) {
  if (selectedLeft.value === item.key) {
    selectedLeft.value = ''
    selectedRight.value = ''
    closeRecordDetail()
    return
  }
  selectedLeft.value = item.key
  selectedRight.value = ''
  const existing = mappingBySource.value.get(item.key)
  if (existing && syncScroll.value) {
    selectedRight.value = existing.target
    nextTick(() => alignMappedPair(existing.source, existing.target, 'left'))
  }
  showRecordDetail('left', item)
}

function openRightDetail(item) {
  if (selectedRight.value === item.key) {
    selectedRight.value = ''
    selectedLeft.value = ''
    closeRecordDetail()
    return
  }
  selectedRight.value = item.key
  selectedLeft.value = ''
  const existing = mappingByTarget.value.get(item.key)
  if (existing && syncScroll.value) {
    selectedLeft.value = existing.source
    nextTick(() => alignMappedPair(existing.source, existing.target, 'right'))
  }
  showRecordDetail('right', item)
}

function onLeftItemClick(item) {
  if (props.manualLinkDisabled || props.dotLinkOnly) {
    openLeftDetail(item)
    return
  }
  onLeftLinkClick(item)
}

function onRightItemClick(item) {
  if (props.manualLinkDisabled || props.dotLinkOnly) {
    openRightDetail(item)
    return
  }
  onRightLinkClick(item)
}

function onLeftDotClick(item) {
  if (props.manualLinkDisabled) return
  onLeftLinkClick(item)
}

function onRightDotClick(item) {
  if (props.manualLinkDisabled) return
  if (suppressRightDotClick) {
    suppressRightDotClick = false
    return
  }
  onRightLinkClick(item)
}

function cleanupRetargetListeners() {
  window.removeEventListener('pointermove', onRetargetPointerMove)
  window.removeEventListener('pointerup', onRetargetPointerUp, true)
  window.removeEventListener('pointercancel', onRetargetPointerUp, true)
}

function findRightKeyAtPoint(clientX, clientY) {
  const list = rightListRef.value
  if (!list) return ''
  const rect = list.getBoundingClientRect()
  if (clientX < rect.left || clientX > rect.right || clientY < rect.top || clientY > rect.bottom) {
    return ''
  }
  if (props.virtual) {
    const y = clientY - rect.top + list.scrollTop
    const idx = Math.floor(y / itemH.value)
    const item = visibleRight.value[idx]
    return item?.key || ''
  }
  const el = document.elementFromPoint(clientX, clientY)
  const itemEl = el?.closest?.('.map-item.right')
  return itemEl?.dataset?.key || ''
}

function onRightDotPointerDown(item, event) {
  if (!canRetargetRight(item)) return
  if (event.button != null && event.button !== 0) return
  const linked = mappingsByTarget.value.get(item.key) || []
  if (!linked.length) return
  event.preventDefault()
  cleanupRetargetListeners()
  retargetDrag.value = {
    fromTarget: item.key,
    sources: linked.map((m) => m.source),
    active: false,
    startX: event.clientX,
    startY: event.clientY,
    x: event.clientX,
    y: event.clientY,
    hoverTarget: '',
  }
  window.addEventListener('pointermove', onRetargetPointerMove)
  window.addEventListener('pointerup', onRetargetPointerUp, true)
  window.addEventListener('pointercancel', onRetargetPointerUp, true)
}

function onRetargetPointerMove(event) {
  const drag = retargetDrag.value
  if (!drag) return
  const dist = Math.hypot(event.clientX - drag.startX, event.clientY - drag.startY)
  const next = {
    ...drag,
    x: event.clientX,
    y: event.clientY,
  }
  if (!drag.active && dist >= 6) {
    next.active = true
    selectedLeft.value = ''
    selectedRight.value = ''
    closeRecordDetail()
  }
  if (next.active) {
    next.hoverTarget = findRightKeyAtPoint(event.clientX, event.clientY)
  }
  retargetDrag.value = next
  if (next.active) scheduleDraw()
}

function onRetargetPointerUp(event) {
  const drag = retargetDrag.value
  cleanupRetargetListeners()
  retargetDrag.value = null
  if (!drag) return
  // 无论是否形成拖拽，都吞掉随后的 click，避免误取消关联
  suppressRightDotClick = true
  if (!drag.active) {
    onRightLinkClick({ key: drag.fromTarget, mapped: true })
    scheduleDraw()
    return
  }
  const toTarget = findRightKeyAtPoint(event.clientX, event.clientY)
  if (toTarget && toTarget !== drag.fromTarget) {
    retargetMappings(drag.fromTarget, toTarget, drag.sources)
  }
  scheduleDraw()
}

function retargetMappings(fromTarget, toTarget, sources) {
  if (props.manualLinkDisabled) return
  if (!fromTarget || !toTarget || fromTarget === toTarget) return
  const sourceList = Array.isArray(sources) ? sources.filter(Boolean) : []
  if (!sourceList.length) return
  const sourceSet = new Set(sourceList)
  let next = props.mappings.filter((m) => !sourceSet.has(m.source))
  if (!props.allowSharedTarget) {
    next = next.filter((m) => m.target !== toTarget)
  }
  for (const source of sourceList) {
    next.push({ source, target: toTarget })
  }
  emitMappings(next)
}

function onLeftLinkClick(item) {
  const existing = mappingBySource.value.get(item.key)
  const existingJoins = props.allowLeftJoins ? findLeftJoinsForKey(item.key) : []

  if (selectedLeft.value === item.key) {
    if (existing) {
      emitMappings(props.mappings.filter((m) => m.source !== item.key))
      emit('edit-match', { action: 'unlink', source: item.key, target: existing.target })
    }
    if (existingJoins.length) {
      removeLeftJoinsForKey(item.key)
    }
    selectedLeft.value = ''
    selectedRight.value = ''
    closeRecordDetail()
    return
  }

  if (selectedLeft.value && props.allowLeftJoins) {
    const prevGroup = groupKeyOf(selectedLeft.value)
    const nextGroup = groupKeyOf(item)
    if (prevGroup && nextGroup && prevGroup !== nextGroup) {
      linkLeftJoin(selectedLeft.value, item.key)
      // 一对多时保持源字段选中，可继续连到其他表字段
      selectedRight.value = ''
      closeRecordDetail()
      return
    }
  }

  if (selectedRight.value) {
    link(item.key, selectedRight.value)
    selectedLeft.value = ''
    selectedRight.value = ''
    closeRecordDetail()
    return
  }

  selectedLeft.value = item.key
  if (existing && syncScroll.value) {
    selectedRight.value = existing.target
    nextTick(() => alignMappedPair(existing.source, existing.target, 'left'))
  }
  if (!props.dotLinkOnly) showRecordDetail('left', item)
}

function onRightLinkClick(item) {
  const existingList = mappingsByTarget.value.get(item.key) || []
  const existing = selectedLeft.value
    ? existingList.find((m) => m.source === selectedLeft.value) || mappingByTarget.value.get(item.key)
    : mappingByTarget.value.get(item.key)
  if ((existingList.length || item.mapped) && selectedRight.value === item.key) {
    if (props.allowSharedTarget && existingList.length > 1) {
      const preferred =
        (selectedLeft.value && existingList.find((m) => m.source === selectedLeft.value)) ||
        existingList[0]
      emitMappings(props.mappings.filter((m) => !(m.source === preferred.source && m.target === preferred.target)))
      emit('edit-match', { action: 'unlink', source: preferred.source, target: preferred.target })
    } else {
      emitMappings(props.mappings.filter((m) => m.target !== item.key))
      emit('edit-match', { action: 'unlink', source: existing?.source, target: item.key })
    }
    selectedRight.value = ''
    selectedLeft.value = ''
    closeRecordDetail()
    return
  }
  if (selectedLeft.value) {
    link(selectedLeft.value, item.key)
    selectedLeft.value = ''
    selectedRight.value = ''
    closeRecordDetail()
    return
  }
  selectedRight.value = item.key
  if (existing && syncScroll.value) {
    selectedLeft.value = existing.source
    nextTick(() => alignMappedPair(existing.source, existing.target, 'right'))
  }
  if (!props.dotLinkOnly) showRecordDetail('right', item)
}

function onLeftClick(item) {
  onLeftItemClick(item)
}

function onRightClick(item) {
  onRightItemClick(item)
}

function currentAnchor() {
  if (selectedLeft.value) {
    const mapped = mappingBySource.value.get(selectedLeft.value)
    if (mapped) return mapped
  }
  if (selectedRight.value) {
    const mapped = mappingByTarget.value.get(selectedRight.value)
    if (mapped) return mapped
  }
  return null
}

function maxScroll(el) {
  return Math.max(0, el.scrollHeight - el.clientHeight)
}

function syncByRatio(fromEl, toEl) {
  const fromMax = maxScroll(fromEl)
  const toMax = maxScroll(toEl)
  toEl.scrollTop = fromMax <= 0 ? 0 : (fromEl.scrollTop / fromMax) * toMax
}

function alignMappedPair(sourceKey, targetKey, fromSide) {
  const leftList = leftListRef.value
  const rightList = rightListRef.value
  if (!leftList || !rightList) return
  syncingScroll = true
  if (props.virtual) {
    const leftIdx = leftIndexMap.value.get(sourceKey)
    const rightIdx = rightIndexMap.value.get(targetKey)
    if (leftIdx == null || rightIdx == null) {
      syncingScroll = false
      return
    }
    const srcList = fromSide === 'left' ? leftList : rightList
    const dstList = fromSide === 'left' ? rightList : leftList
    const srcIdx = fromSide === 'left' ? leftIdx : rightIdx
    const dstIdx = fromSide === 'left' ? rightIdx : leftIdx
    const srcOffset = srcIdx * itemH.value + itemH.value / 2 - srcList.scrollTop
    dstList.scrollTop = dstIdx * itemH.value + itemH.value / 2 - srcOffset
  } else {
    const leftEl = leftRefs[sourceKey]
    const rightEl = rightRefs[targetKey]
    if (!leftEl || !rightEl) {
      syncingScroll = false
      return
    }
    const srcEl = fromSide === 'left' ? leftEl : rightEl
    const dstEl = fromSide === 'left' ? rightEl : leftEl
    const srcList = fromSide === 'left' ? leftList : rightList
    const dstList = fromSide === 'left' ? rightList : leftList
    const srcOffset = srcEl.getBoundingClientRect().top - srcList.getBoundingClientRect().top
    const dstOffset = dstEl.getBoundingClientRect().top - dstList.getBoundingClientRect().top
    dstList.scrollTop += dstOffset - srcOffset
  }
  leftScrollTop.value = leftList.scrollTop
  rightScrollTop.value = rightList.scrollTop
  requestAnimationFrame(() => {
    syncingScroll = false
    scheduleDraw()
  })
}

function onPanelScroll(side) {
  const leftList = leftListRef.value
  const rightList = rightListRef.value
  if (leftList) leftScrollTop.value = leftList.scrollTop
  if (rightList) rightScrollTop.value = rightList.scrollTop
  scheduleDraw()
  if (!syncScroll.value || syncingScroll) return
  const fromEl = side === 'left' ? leftList : rightList
  const toEl = side === 'left' ? rightList : leftList
  if (!fromEl || !toEl) return
  syncingScroll = true
  const anchor = currentAnchor()
  if (anchor) {
    alignMappedPair(anchor.source, anchor.target, side)
  } else {
    syncByRatio(fromEl, toEl)
    if (leftList) leftScrollTop.value = leftList.scrollTop
    if (rightList) rightScrollTop.value = rightList.scrollTop
  }
  requestAnimationFrame(() => {
    syncingScroll = false
    scheduleDraw()
  })
}

function link(source, target) {
  if (props.manualLinkDisabled) return
  const next = props.allowSharedTarget
    ? props.mappings.filter((m) => m.source !== source)
    : props.mappings.filter((m) => m.source !== source && m.target !== target)
  next.push({ source, target })
  emitMappings(next)
  emit('edit-match', { action: 'link', source, target })
}

function removeMapping(source, target) {
  if (props.manualLinkDisabled) return
  emitMappings(props.mappings.filter((m) => !(m.source === source && m.target === target)))
  emit('edit-match', { action: 'unlink', source, target })
}

function clearMappings() {
  emitMappings([])
  if (props.allowLeftJoins) emitLeftJoins([])
  highlighted.value = false
  contentResult.value = null
  emit('clear-match')
}

function normalize(item) {
  return String(item.matchValue ?? item.title ?? item.key)
    .trim()
    .toLowerCase()
}

async function runContent() {
  comparing.value = true
  contentResult.value = null
  try {
    if (props.fullCompareFn) {
      const result = await props.fullCompareFn()
      if (!result) return
      emitMappings(result.mappings || [])
      highlighted.value = true
      contentResult.value = {
        matched: result.matched ?? (result.mappings || []).length,
        leftOnly: result.leftOnly ?? 0,
        rightOnly: result.rightOnly ?? 0,
      }
      return
    }
    const buckets = new Map()
    for (const right of activeRightItems.value) {
      const token = normalize(right)
      let list = buckets.get(token)
      if (!list) {
        list = []
        buckets.set(token, list)
      }
      list.push(right)
    }
    const used = new Set()
    const next = []
    for (const left of activeLeftItems.value) {
      const list = buckets.get(normalize(left))
      if (!list) continue
      const match = props.allowSharedTarget
        ? list[0]
        : list.find((right) => !used.has(right.key))
      if (match) {
        if (!props.allowSharedTarget) used.add(match.key)
        next.push({ source: left.key, target: match.key })
      }
    }
    if (props.allowLeftJoins && useLeftGroups.value) {
      const activeKeys = new Set(activeLeftItems.value.map((item) => item.key))
      const kept = props.mappings.filter((m) => !activeKeys.has(m.source))
      emitMappings([...kept, ...next])
    } else {
      emitMappings(next)
    }
    highlighted.value = true
    const linkedTargets = new Set(next.map((m) => m.target))
    contentResult.value = {
      matched: next.length,
      leftOnly: activeLeftItems.value.length - next.length,
      rightOnly: activeRightItems.value.length - linkedTargets.size,
    }
  } catch (err) {
    console.error(err)
  } finally {
    comparing.value = false
    nextTick(scheduleDraw)
  }
}

function svgOrigin() {
  const el = svgRef.value || rootRef.value
  if (!el) return null
  return el.getBoundingClientRect()
}

function pointFromIndex(side, index) {
  const list = side === 'left' ? leftListRef.value : rightListRef.value
  const origin = svgOrigin()
  if (!origin || !list) return null
  const h = itemH.value
  const yInList = index * h + h / 2 - list.scrollTop
  if (yInList < -h || yInList > list.clientHeight + h) return null
  const rect = list.getBoundingClientRect()
  return {
    x: side === 'left' ? rect.right - origin.left - 5 : rect.left - origin.left + 5,
    y: rect.top - origin.top + yInList,
  }
}

function pointFromEl(el) {
  const origin = svgOrigin()
  if (!origin || !el) return null
  const node = el.$el || el
  const dot = typeof node.querySelector === 'function' ? node.querySelector('.dot') : null
  const rect = (dot || node).getBoundingClientRect()
  return {
    x: rect.left + rect.width / 2 - origin.left,
    y: rect.top + rect.height / 2 - origin.top,
  }
}

function pointFromFieldLine(side, itemKey, lineIndex) {
  const origin = svgOrigin()
  const wrap = side === 'left' ? leftRefs[itemKey] : rightRefs[itemKey]
  const list = side === 'left' ? leftListRef.value : rightListRef.value
  if (!origin || !wrap || !list) return null
  const node = wrap.$el || wrap
  if (typeof node.querySelectorAll !== 'function') return null
  const rows = node.querySelectorAll('.item-line')
  const el = rows[lineIndex]
  if (!el) return null
  const rect = el.getBoundingClientRect()
  const listRect = list.getBoundingClientRect()
  if (rect.bottom < listRect.top - 4 || rect.top > listRect.bottom + 4) return null
  return {
    x: side === 'left' ? rect.right - origin.left - 2 : rect.left - origin.left + 2,
    y: rect.top + rect.height / 2 - origin.top,
  }
}

function appendFieldLinks(next) {
  const links = Array.isArray(props.fieldLinks) ? props.fieldLinks : []
  if (!links.length) return
  for (const link of links) {
    if (!link?.source || !link?.target) continue
    const a = pointFromFieldLine('left', link.source, Number(link.sourceLine) || 0)
    const b = pointFromFieldLine('right', link.target, Number(link.targetLine) || 0)
    if (!a || !b) continue
    const dx = Math.max(48, (b.x - a.x) / 2)
    next.push({
      id: `fl:${link.source}:${link.sourceLine}::${link.target}:${link.targetLine}`,
      kind: 'field-link',
      source: link.source,
      target: link.target,
      equal: link.equal !== false,
      d: `M ${a.x} ${a.y} C ${a.x + dx} ${a.y}, ${b.x - dx} ${b.y}, ${b.x} ${b.y}`,
    })
  }
}

function gapBounds() {
  const leftList = leftListRef.value
  const rightList = rightListRef.value
  const origin = svgOrigin()
  if (!origin || !leftList || !rightList) return null
  const gapLeft = leftList.getBoundingClientRect().right - origin.left
  const gapRight = rightList.getBoundingClientRect().left - origin.left
  return { gapLeft, gapRight, gapWidth: Math.max(0, gapRight - gapLeft) }
}

function previewEndpoint(drag) {
  const origin = svgOrigin()
  if (!origin || !drag) return null
  if (drag.hoverTarget && drag.hoverTarget !== drag.fromTarget) {
    if (props.virtual) {
      const idx = rightIndexMap.value.get(drag.hoverTarget)
      if (idx != null) {
        const point = pointFromIndex('right', idx)
        if (point) return point
      }
    } else {
      const point = pointFromEl(rightRefs[drag.hoverTarget])
      if (point) return point
    }
  }
  return {
    x: drag.x - origin.left,
    y: drag.y - origin.top,
  }
}

function appendRetargetPreviews(next, drag) {
  if (!drag?.active || !drag.sources?.length) return
  const end = previewEndpoint(drag)
  if (!end) return
  for (const source of drag.sources) {
    let a = null
    if (props.virtual) {
      const leftIdx = leftIndexMap.value.get(source)
      if (leftIdx == null) continue
      a = pointFromIndex('left', leftIdx)
    } else {
      a = pointFromEl(leftRefs[source])
    }
    if (!a) continue
    const dx = Math.max(60, (end.x - a.x) / 2)
    next.push({
      id: `retarget:${source}`,
      kind: 'retarget-preview',
      source,
      target: drag.hoverTarget || '',
      d: `M ${a.x} ${a.y} C ${a.x + dx} ${a.y}, ${end.x - dx} ${end.y}, ${end.x} ${end.y}`,
    })
  }
}

function draw() {
  if (!rootRef.value) return
  svgSize.w = rootRef.value.clientWidth
  svgSize.h = rootRef.value.clientHeight
  const next = []
  const draggingFrom = retargetDrag.value?.active ? retargetDrag.value.fromTarget : ''
  const hasFieldLinks = Array.isArray(props.fieldLinks) && props.fieldLinks.length > 0
  if (props.virtual) {
    if (!hasFieldLinks) {
      const leftMap = leftIndexMap.value
      const rightMap = rightIndexMap.value
      const leftVisible = new Set(leftWindow.value.slice.map((item) => item.key))
      const rightVisible = new Set(rightWindow.value.slice.map((item) => item.key))
      for (const mapping of props.mappings) {
        if (draggingFrom && mapping.target === draggingFrom) continue
        if (!leftVisible.has(mapping.source) || !rightVisible.has(mapping.target)) continue
        const leftIdx = leftMap.get(mapping.source)
        const rightIdx = rightMap.get(mapping.target)
        if (leftIdx == null || rightIdx == null) continue
        const a = pointFromIndex('left', leftIdx)
        const b = pointFromIndex('right', rightIdx)
        if (!a || !b) continue
        const dx = Math.max(60, (b.x - a.x) / 2)
        next.push({
          id: `${mapping.source}::${mapping.target}`,
          source: mapping.source,
          target: mapping.target,
          d: `M ${a.x} ${a.y} C ${a.x + dx} ${a.y}, ${b.x - dx} ${b.y}, ${b.x} ${b.y}`,
        })
      }
    }
  } else {
    for (const mapping of props.mappings) {
      if (draggingFrom && mapping.target === draggingFrom) continue
      const a = pointFromEl(leftRefs[mapping.source])
      const b = pointFromEl(rightRefs[mapping.target])
      if (!a || !b) continue
      const dx = Math.max(60, (b.x - a.x) / 2)
      next.push({
        id: `${mapping.source}::${mapping.target}`,
        source: mapping.source,
        target: mapping.target,
        d: `M ${a.x} ${a.y} C ${a.x + dx} ${a.y}, ${b.x - dx} ${b.y}, ${b.x} ${b.y}`,
      })
    }
    if (props.allowLeftJoins) {
      const gap = gapBounds()
      for (const mapping of props.leftJoins || []) {
        const a = pointFromEl(leftRefs[mapping.source])
        const b = pointFromEl(leftRefs[mapping.target])
        if (!a || !b || !gap || gap.gapWidth < 16) continue
        const maxBulge = Math.max(gap.gapLeft + 8, gap.gapRight - 10)
        const bulgeX = Math.min(a.x + Math.max(gap.gapWidth * 0.5, 28), maxBulge)
        next.push({
          id: `lj:${mapping.source}::${mapping.target}`,
          kind: 'left-join',
          source: mapping.source,
          target: mapping.target,
          d: `M ${a.x} ${a.y} C ${bulgeX} ${a.y}, ${bulgeX} ${b.y}, ${b.x} ${b.y}`,
        })
      }
    }
  }
  appendRetargetPreviews(next, retargetDrag.value)
  appendFieldLinks(next)
  lines.value = next
}

let frame = 0
function scheduleDraw() {
  cancelAnimationFrame(frame)
  frame = requestAnimationFrame(draw)
}

function measureViewport() {
  const h = leftListRef.value?.clientHeight || rightListRef.value?.clientHeight
  if (h) viewportH.value = h
}

let observer
onMounted(() => {
  applySearchSeed()
  observer = new ResizeObserver(() => {
    measureViewport()
    scheduleDraw()
  })
  if (rootRef.value) observer.observe(rootRef.value)
  if (leftListRef.value) observer.observe(leftListRef.value)
  window.addEventListener('resize', scheduleDraw)
  nextTick(() => {
    measureViewport()
    scheduleDraw()
  })
})

onBeforeUnmount(() => {
  cleanupRetargetListeners()
  retargetDrag.value = null
  observer?.disconnect()
  window.removeEventListener('resize', scheduleDraw)
  cancelAnimationFrame(frame)
  clearTimeout(leftSearchTimer)
  clearTimeout(rightSearchTimer)
})

function emitSearch() {
  const leftConditions = activeSearchConditions(leftSearchRules.value)
  const rightConditions = activeSearchConditions(rightSearchRules.value)
  emit('search', {
    leftConditions,
    rightConditions,
    leftLogic: deriveSearchLogic(leftConditions),
    rightLogic: deriveSearchLogic(rightConditions),
  })
}

function scheduleEmitSearch() {
  const delay = props.serverSearch ? 320 : 160
  clearTimeout(leftSearchTimer)
  leftSearchTimer = window.setTimeout(() => {
    if (props.serverSearch) emitSearch()
  }, delay)
}

watch(leftSearchRules, () => scheduleEmitSearch(), { deep: true })
watch(rightSearchRules, () => scheduleEmitSearch(), { deep: true })

watch(
  leftSearchFieldLeaves,
  (leaves) => {
    const valid = new Set(leaves.map((item) => item.value))
    leftSearchRules.value = leftSearchRules.value.map((rule) => ({
      ...rule,
      field: rule.field && valid.has(rule.field) ? rule.field : undefined,
    }))
  },
  { deep: true },
)

watch(
  rightSearchFieldLeaves,
  (leaves) => {
    const valid = new Set(leaves.map((item) => item.value))
    rightSearchRules.value = rightSearchRules.value.map((rule) => ({
      ...rule,
      field: rule.field && valid.has(rule.field) ? rule.field : undefined,
    }))
  },
  { deep: true },
)

watch(
  () => props.searchResetKey,
  () => {
    applySearchSeed()
  },
)

watch(
  () => [
    props.mappings,
    props.leftJoins,
    props.leftItems,
    props.rightItems,
    props.leftGroups,
    props.rightGroups,
    props.hideMapped,
    props.fieldLinks,
  ],
  () => nextTick(scheduleDraw),
  { deep: true },
)

watch(
  () => props.expandedLeftKey,
  (key) => {
    if (!useLeftGroups.value || !key || key === expandedLeftKey.value) return
    if (props.leftGroups.some((g) => g.key === key)) expandedLeftKey.value = key
  },
)

watch(
  () => props.expandedRightKey,
  (key) => {
    if (!useRightGroups.value || !key || key === expandedRightKey.value) return
    if (props.rightGroups.some((g) => g.key === key)) expandedRightKey.value = key
  },
)

watch(
  () => props.leftGroups,
  () => syncExpandedGroup('left'),
  { immediate: true, deep: true },
)

watch(
  () => props.rightGroups,
  () => syncExpandedGroup('right'),
  { immediate: true, deep: true },
)
</script>

<style scoped>
.mapping-canvas {
  position: relative;
  display: flex;
  flex-direction: column;
  min-height: 520px;
  background: #fff;
  border: 1px solid var(--card-border);
  border-radius: 12px;
  overflow: hidden;
}

.compare-mask {
  position: absolute;
  inset: 0;
  z-index: 20;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 12px;
  background: rgba(255, 255, 255, 0.78);
}

.compare-mask-text {
  color: #1677ff;
  font-size: 14px;
}

.mapping-toolbar {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 12px 16px;
  border-bottom: 1px solid #eef2f6;
  background: #fafbfd;
}

.toolbar-left {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 8px;
}

.hide-mapped {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  margin-left: 8px;
  color: #344054;
  font-size: 13px;
  cursor: pointer;
}

.toolbar-right {
  display: flex;
  align-items: center;
  gap: 12px;
  color: #667085;
  font-size: 13px;
}

.toolbar-hint {
  max-width: 520px;
  text-align: right;
  line-height: 1.4;
}

.banner {
  margin: 12px 16px 0;
  padding: 8px 12px;
  border-radius: 8px;
  font-size: 13px;
}

.banner.info {
  background: #eff6ff;
  color: #1d4ed8;
}

.mapping-body {
  position: relative;
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 88px;
  padding: 16px;
  min-height: 460px;
}

.panel {
  min-width: 0;
  display: flex;
  flex-direction: column;
  padding-right: 4px;
}

.panel-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  font-weight: 650;
  margin-bottom: 8px;
  color: #344054;
  flex: 0 0 auto;
  gap: 8px;
}

.panel-title {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  min-width: 0;
}

.panel-search-add-link {
  align-self: flex-start;
  height: auto;
  padding: 0 4px;
  font-size: 13px;
}

.panel-search-when,
.panel-search-join {
  width: 56px;
  min-width: 56px;
}

.panel-search-when {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  height: 32px;
  color: #667085;
  font-size: 13px;
  font-weight: 600;
}

.panel-count {
  font-weight: 400;
  font-size: 12px;
  color: #98a2b3;
  flex: 0 0 auto;
}

.panel-hint {
  margin-left: 8px;
  font-weight: 400;
  font-size: 12px;
  color: #d48806;
}

.panel-search-stack {
  display: flex;
  flex-direction: column;
  gap: 8px;
  margin-bottom: 10px;
  flex: 0 0 auto;
  min-width: 0;
  max-height: 220px;
  overflow-x: hidden;
  overflow-y: auto;
}

.panel-search-row {
  display: grid;
  grid-template-columns: 56px minmax(88px, 140px) minmax(84px, 104px) minmax(0, 1fr) auto;
  align-items: center;
  gap: 8px;
  min-width: 0;
}

.panel-search-field,
.panel-search-mode,
.panel-search {
  width: 100% !important;
  min-width: 0;
  margin-bottom: 0;
}

.panel-search-action {
  width: 32px;
  min-width: 32px;
  padding: 0;
  font-size: 16px;
  font-weight: 600;
  line-height: 1;
}

.panel-search-stack :deep(.ant-select-selector) {
  max-width: 100%;
}

.panel-list {
  position: relative;
  overflow: auto;
  height: 500px;
  min-height: 240px;
  padding-right: 4px;
  flex: 1 1 auto;
  min-width: 0;
}

.virtual-phantom {
  min-width: 100%;
  width: max-content;
}

.group-block {
  margin-bottom: 6px;
}

.group-head {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 10px 12px;
  margin-bottom: 6px;
  background: #f8fafc;
  border: 1px solid #e5eaf1;
  border-radius: 8px;
  cursor: pointer;
  user-select: none;
}

.group-head:hover {
  border-color: #91caff;
}

.group-head.active {
  border-color: #1677ff;
  background: #f0f7ff;
}

.group-title {
  flex: 1;
  min-width: 0;
  font-weight: 650;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.group-meta {
  color: #98a2b3;
  font-size: 12px;
}

.group-arrow {
  color: #667085;
  font-size: 11px;
  transition: transform 0.2s ease;
}

.group-arrow.open {
  transform: rotate(180deg);
}

.empty.nested {
  padding: 24px 12px;
  min-height: 80px;
}

.list-mask {
  position: sticky;
  top: 0;
  z-index: 3;
  display: flex;
  justify-content: center;
  padding: 24px 0;
}

.virtual-phantom {
  position: relative;
  width: 100%;
}

.virtual-window {
  position: absolute;
  inset: 0 auto auto 0;
  width: 100%;
  will-change: transform;
}

.empty {
  color: #98a2b3;
  padding: 48px 16px;
  text-align: center;
  min-height: 160px;
  display: flex;
  align-items: center;
  justify-content: center;
  box-sizing: border-box;
}

.map-item {
  position: relative;
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 10px 12px;
  margin-bottom: 8px;
  background: #fff;
  border: 1px solid #e5eaf1;
  border-radius: 10px;
  cursor: pointer;
  box-sizing: border-box;
}

.clear-links-btn {
  position: absolute;
  top: 6px;
  right: 22px;
  z-index: 3;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 20px;
  height: 20px;
  padding: 0;
  border: none;
  border-radius: 999px;
  background: rgba(255, 255, 255, 0.92);
  color: #98a2b3;
  font-size: 11px;
  line-height: 1;
  cursor: pointer;
  box-shadow: 0 0 0 1px rgba(152, 162, 179, 0.35);
  opacity: 0.72;
  transition: color 0.15s ease, background 0.15s ease, opacity 0.15s ease, box-shadow 0.15s ease;
}

.clear-links-btn.right {
  right: 8px;
}

.map-item:hover .clear-links-btn,
.map-item.selected .clear-links-btn,
.map-item.mapped .clear-links-btn,
.map-item.left-join-multi .clear-links-btn {
  opacity: 1;
}

.clear-links-btn:hover {
  color: #fff;
  background: #f04438;
  box-shadow: none;
  opacity: 1;
}

.map-item.compact {
  height: auto;
  min-height: 52px;
  padding: 8px 10px;
  align-items: flex-start;
  background: linear-gradient(180deg, #ffffff 0%, #fafbfc 100%);
}

.map-item:hover {
  border-color: #91caff;
}

.map-item.selected {
  border-color: #1677ff;
  box-shadow: 0 0 0 3px rgba(22, 119, 255, 0.12);
}

.map-item.mapped {
  border-color: #1677ff;
  background: #f5f9ff;
}

/* 源侧跨表一对多：仅连出≥2 时加深卡片底色 */
.map-item.left-join-deg-2 {
  border-color: #69b1ff;
  background: #bae0ff;
}

.map-item.left-join-deg-3 {
  border-color: #4096ff;
  background: #91caff;
}

.map-item.left-join-deg-4 {
  border-color: #1677ff;
  background: #69b1ff;
}

.map-item.left-join-deg-5 {
  border-color: #0958d9;
  background: #4096ff;
  color: #002c8c;
}

.map-item.left-join-deg-4 .item-title,
.map-item.left-join-deg-5 .item-title,
.map-item.left-join-deg-4 .item-desc,
.map-item.left-join-deg-5 .item-desc {
  color: #002c8c;
  font-weight: 600;
}

.map-item.left-join-multi.selected {
  box-shadow: 0 0 0 3px rgba(9, 88, 217, 0.22);
}

.map-item.display-only {
  border-color: #faad14;
  background: #fffbe6;
}

.map-item.unmatched {
  opacity: 0.62;
}

.display-check {
  flex: 0 0 auto;
}

.display-check :deep(.ant-checkbox) {
  top: 0;
}

.item-main {
  flex: 1;
  min-width: 0;
}

.item-title-wrap {
  display: block;
  width: 100%;
}

.item-title {
  display: flex;
  flex-direction: column;
  gap: 2px;
  font-weight: 600;
  word-break: break-all;
}

.item-title.field-stack {
  gap: 3px;
}

.item-line {
  display: grid;
  grid-template-columns: minmax(110px, 1.05fr) minmax(0, 1.35fr);
  column-gap: 8px;
  align-items: center;
  min-height: 24px;
  height: 24px;
  padding: 0 8px;
  border-radius: 6px;
  box-sizing: border-box;
}

.item-line:nth-child(odd) {
  background: rgba(152, 162, 179, 0.08);
}

.line-key {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  min-width: 0;
  overflow: hidden;
  color: #475467;
  font-size: 12px;
  font-weight: 500;
  line-height: 18px;
  justify-content: flex-start;
  text-align: left;
}

.line-mark {
  flex: 0 0 14px;
  width: 14px;
  height: 14px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  border-radius: 50%;
  font-size: 10px;
  font-weight: 700;
  line-height: 1;
}

.line-mark.yes {
  color: #389e0d;
  background: rgba(82, 196, 26, 0.16);
}

.line-mark.no {
  color: #cf1322;
  background: rgba(255, 77, 79, 0.14);
}

.line-mark.display {
  color: #d48806;
  background: rgba(250, 173, 20, 0.22);
  font-weight: 800;
}

.line-field {
  flex: 0 1 auto;
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  color: #344054;
  font-weight: 600;
}

.line-table {
  flex: 0 0 auto;
  max-width: 42%;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  color: #98a2b3;
  font-size: 10px;
  font-weight: 500;
  line-height: 16px;
  padding: 0 5px;
  border-radius: 999px;
  background: rgba(152, 162, 179, 0.14);
}

.line-val {
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  color: #1d2939;
  font-size: 12px;
  font-weight: 600;
  line-height: 18px;
  font-variant-numeric: tabular-nums;
}

.item-line.join {
  background: rgba(22, 119, 255, 0.06);
  grid-template-columns: minmax(160px, 1.45fr) minmax(0, 1fr);
}

.item-line.join .line-key {
  color: #1677ff;
  font-weight: 600;
  justify-content: flex-start;
}

.item-line.join .join-expr {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
  font-size: 11px;
  font-weight: 600;
}

.item-line.join .line-val {
  color: #175cd3;
  font-weight: 600;
}

.item-line.unequal {
  background: rgba(220, 38, 38, 0.08);
}

.item-line.unequal .line-key,
.item-line.unequal .line-val {
  color: #dc2626;
}

.map-item.right .line-key,
.map-item.right .item-line.join .line-key {
  justify-content: flex-start;
  text-align: left;
}

.map-item.compact.mapped {
  background: #f5f9ff;
}

.compact .item-title.field-stack {
  overflow: visible;
}

.item-desc {
  margin-top: 4px;
  color: #667085;
  font-size: 12px;
  line-height: 1.45;
  word-break: break-all;
}

.item-sample {
  margin-top: 4px;
  color: #475467;
  font-size: 12px;
  line-height: 1.45;
  word-break: break-all;
}

.compact .item-title,
.compact .item-desc {
  overflow: hidden;
  width: 100%;
  word-break: normal;
}

.compact .item-title:not(:has(.item-line)) {
  text-overflow: ellipsis;
  white-space: nowrap;
  display: block;
}

.compact .item-desc {
  margin-top: 2px;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.compact .dot {
  margin-top: 5px;
}

.item-tags {
  margin-top: 6px;
}

.dot {
  width: 10px;
  height: 10px;
  border-radius: 50%;
  background: #1677ff;
  box-shadow: 0 0 0 4px rgba(22, 119, 255, 0.12);
  flex-shrink: 0;
  position: relative;
  z-index: 2;
}

.dot.clickable {
  cursor: pointer;
}

.dot.clickable::before {
  content: '';
  position: absolute;
  top: 50%;
  left: 50%;
  width: 28px;
  height: 28px;
  transform: translate(-50%, -50%);
  border-radius: 50%;
}

.dot.clickable:hover {
  box-shadow: 0 0 0 6px rgba(22, 119, 255, 0.22);
}

.dot.draggable {
  cursor: grab;
}

.dot.draggable:active,
.dot.dragging {
  cursor: grabbing;
}

.dot.dragging {
  box-shadow: 0 0 0 7px rgba(22, 119, 255, 0.28);
  transform: scale(1.15);
}

.map-item:not(.right) .dot {
  margin-right: -1px;
}

.map-item.right .dot {
  margin-left: -1px;
}

.map-item.retarget-from {
  opacity: 0.72;
  border-style: dashed;
}

.map-item.retarget-drop {
  border-color: #1677ff !important;
  box-shadow: 0 0 0 2px rgba(22, 119, 255, 0.28);
  background: rgba(22, 119, 255, 0.08);
}

.mapping-body.retargeting {
  cursor: grabbing;
  user-select: none;
}

.mapping-body.retargeting .link-path:not(.preview) {
  pointer-events: none;
}

.svg-layer {
  position: absolute;
  inset: 0;
  pointer-events: none;
  overflow: visible;
}

.link-path {
  fill: none;
  stroke: #1677ff;
  stroke-width: 2.2;
  stroke-linecap: round;
  stroke-linejoin: round;
  pointer-events: stroke;
  cursor: pointer;
}

.link-path.left-join-path {
  stroke: #1677ff;
  stroke-dasharray: 6 4;
}

.link-path.field-link-path.match {
  stroke: #1677ff;
  stroke-width: 2;
  stroke-dasharray: none;
  opacity: 0.92;
}

.link-path.field-link-path.mismatch {
  stroke: #dc2626;
  stroke-width: 2.4;
  stroke-dasharray: none;
  opacity: 0.95;
}

.link-path.field-link-path:hover {
  stroke-width: 3;
}

.link-path:hover {
  stroke: #dc2626;
  stroke-width: 3;
  stroke-dasharray: none;
}

.link-path.field-link-path.match:hover {
  stroke: #0958d9;
}

.link-path.field-link-path.mismatch:hover {
  stroke: #b91c1c;
}

.link-path.preview {
  stroke: #1677ff;
  stroke-width: 2.4;
  stroke-dasharray: 7 5;
  opacity: 0.9;
  pointer-events: none;
  cursor: default;
}

.link-path.preview:hover {
  stroke: #1677ff;
  stroke-width: 2.4;
  stroke-dasharray: 7 5;
}

.link-path.readonly {
  cursor: default;
  pointer-events: none;
}

.link-path.readonly:hover {
  stroke: #1677ff;
  stroke-width: 2.2;
  stroke-dasharray: inherit;
}

.record-detail {
  max-height: min(70vh, 640px);
  overflow: auto;
  padding: 4px 2px;
}

.record-detail-row {
  display: grid;
  grid-template-columns: minmax(120px, 34%) minmax(0, 1fr);
  gap: 12px;
  padding: 10px 12px;
  border-radius: 8px;
}

.record-detail-row:nth-child(odd) {
  background: #f8fafc;
}

.record-detail-row.join {
  background: rgba(22, 119, 255, 0.06);
}

.record-detail-row.expandable {
  cursor: pointer;
}

.record-detail-row.expandable:hover {
  background: rgba(22, 119, 255, 0.1);
}

.record-detail-row.unequal {
  background: rgba(220, 38, 38, 0.06);
}

.record-detail-key {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 6px;
  color: #475467;
  font-size: 12px;
  font-weight: 600;
  line-height: 1.5;
  word-break: break-all;
}

.record-detail-field {
  color: #344054;
}

.record-detail-table {
  color: #98a2b3;
  font-size: 11px;
  font-weight: 500;
  padding: 0 6px;
  border-radius: 999px;
  background: rgba(152, 162, 179, 0.14);
}

.record-detail-val {
  color: #1d2939;
  font-size: 13px;
  font-weight: 500;
  line-height: 1.55;
  white-space: pre-wrap;
  word-break: break-word;
}

.join-expand-arrow {
  color: #1677ff;
  font-size: 10px;
  transition: transform 0.16s ease;
}

.join-expand-arrow.open {
  transform: rotate(180deg);
}

.join-expand-hint {
  margin-left: 8px;
  color: #1677ff;
  font-size: 12px;
  font-weight: 500;
}

.join-detail-panel {
  margin: 0 10px 8px;
  padding: 8px 10px;
  border-radius: 8px;
  background: #f8fbff;
  border: 1px solid rgba(22, 119, 255, 0.14);
}

.join-detail-item {
  display: grid;
  grid-template-columns: 28px minmax(0, 1fr);
  gap: 8px;
  padding: 4px 0;
  color: #344054;
  font-size: 12px;
  line-height: 1.45;
}

.join-detail-item + .join-detail-item {
  border-top: 1px dashed rgba(152, 162, 179, 0.35);
}

.join-detail-index {
  color: #98a2b3;
  font-variant-numeric: tabular-nums;
}

.join-detail-text {
  word-break: break-all;
}

.record-detail-row.join .record-detail-key,
.record-detail-row.join .record-detail-val {
  color: #175cd3;
}

.record-detail-row.join .join-expr {
  font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
  font-size: 12px;
  font-weight: 600;
}

.record-detail-row.unequal .record-detail-key,
.record-detail-row.unequal .record-detail-val {
  color: #dc2626;
}

.record-detail-fallback {
  margin: 0;
  padding: 12px;
  white-space: pre-wrap;
  word-break: break-word;
  font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
  font-size: 12px;
  line-height: 1.55;
  color: #344054;
  background: #f8fafc;
  border-radius: 8px;
}
</style>
