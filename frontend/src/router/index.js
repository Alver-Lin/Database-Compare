import { createRouter, createWebHistory } from 'vue-router'
import AppLayout from '../layouts/AppLayout.vue'
import TaskList from '../views/TaskList.vue'
import CompareWizard from '../views/CompareWizard.vue'
import CompareReport from '../views/CompareReport.vue'

const router = createRouter({
  history: createWebHistory(),
  routes: [
    {
      path: '/',
      component: AppLayout,
      children: [
        { path: '', name: 'tasks', component: TaskList },
        { path: 'compare/:id', name: 'compare', component: CompareWizard, props: true },
        { path: 'compare/:id/report', name: 'compare-report', component: CompareReport, props: true },
      ],
    },
  ],
})

export default router
