<template>
  <a-layout class="app-layout">
    <a-layout-sider breakpoint="lg" collapsed-width="0" :width="232" class="app-sider">
      <div class="brand">
        <div class="brand-mark">DB</div>
        <div>
          <div class="brand-title">库表对比</div>
          <div class="brand-sub">Database Compare</div>
        </div>
      </div>
      <a-menu
        theme="dark"
        mode="inline"
        :selected-keys="selectedKeys"
        class="app-menu"
        @click="onMenu"
      >
        <a-menu-item key="tasks">
          <template #icon><DiffOutlined /></template>
          数据对比任务
        </a-menu-item>
      </a-menu>
    </a-layout-sider>
    <a-layout>
      <a-layout-header class="app-header">
        <div class="header-title">{{ headerTitle }}</div>
        <div class="header-meta">{{ headerMeta }}</div>
      </a-layout-header>
      <a-layout-content class="app-content">
        <router-view />
      </a-layout-content>
    </a-layout>
  </a-layout>
</template>

<script setup>
import { computed } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { DiffOutlined } from '@ant-design/icons-vue'

const route = useRoute()
const router = useRouter()

const selectedKeys = computed(() => ['tasks'])
const headerTitle = computed(() => {
  if (route.name === 'compare') return '开始对比'
  if (route.name === 'compare-report') return '对比报告'
  return '数据对比任务'
})
const headerMeta = computed(() => {
  if (route.name === 'tasks') return '创建源库与目标库的对比任务，支持 MySQL、MariaDB、PostgreSQL、SQLite'
  return 'MySQL / PostgreSQL 结构与数据对比'
})

function onMenu({ key }) {
  if (key === 'tasks') router.push({ name: 'tasks' })
}
</script>

<style scoped>
.app-layout {
  min-height: 100vh;
}

.app-sider {
  background: var(--sider-bg) !important;
}

.app-sider :deep(.ant-layout-sider-children) {
  display: flex;
  flex-direction: column;
}

.brand {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 20px 18px 16px;
}

.brand-mark {
  width: 38px;
  height: 38px;
  border-radius: 10px;
  background: linear-gradient(180deg, #3b82f6, #1677ff);
  color: #fff;
  font-weight: 800;
  display: flex;
  align-items: center;
  justify-content: center;
  letter-spacing: 0.5px;
}

.brand-title {
  color: #fff;
  font-weight: 700;
  font-size: 15px;
}

.brand-sub {
  color: #7d8da3;
  font-size: 11px;
  margin-top: 2px;
}

.app-menu {
  background: transparent !important;
  flex: 1;
}

.app-header {
  background: #fff !important;
  height: 64px;
  line-height: 1.2;
  display: flex;
  flex-direction: column;
  justify-content: center;
  padding: 0 24px;
  border-bottom: 1px solid #edf1f6;
}

.header-title {
  font-size: 16px;
  font-weight: 650;
}

.header-meta {
  font-size: 12px;
  color: #8a94a6;
  margin-top: 3px;
}

.app-content {
  margin: 20px;
  min-height: calc(100vh - 104px);
}
</style>
