import type { Pinia } from 'pinia'
import {
  createRouter,
  createWebHistory,
  type RouterHistory,
  type RouteRecordRaw,
} from 'vue-router'

import { useSessionStore } from '../stores/session'

const DashboardView = () => import('../views/DashboardView.vue')
const TaskListView = () => import('../views/TaskListView.vue')
const CreateTaskView = () => import('../views/CreateTaskView.vue')
const TaskDetailView = () => import('../views/TaskDetailView.vue')
const ReviewView = () => import('../views/ReviewView.vue')
const TemplateListView = () => import('../views/TemplateListView.vue')
const TemplateEditorView = () => import('../views/TemplateEditorView.vue')

const routes: RouteRecordRaw[] = [
  { path: '/', name: 'dashboard', component: DashboardView, meta: { permission: 'review', title: '审核工作台' } },
  { path: '/tasks', name: 'tasks', component: TaskListView, meta: { permission: 'review', title: '审核任务' } },
  { path: '/tasks/new', name: 'create-task', component: CreateTaskView, meta: { permission: 'review', title: '创建审核任务' } },
  { path: '/tasks/:taskId', name: 'task-detail', component: TaskDetailView, meta: { permission: 'review', title: '任务详情' } },
  { path: '/tasks/:taskId/review', name: 'review', component: ReviewView, meta: { permission: 'review', title: '审核结果' } },
  { path: '/templates', name: 'templates', component: TemplateListView, meta: { permission: 'template', title: '模板管理' } },
  { path: '/templates/:templateId', name: 'template-editor', component: TemplateEditorView, meta: { permission: 'template', title: '模板规则编辑' } },
  { path: '/:pathMatch(.*)*', redirect: '/' },
]

export function createApplicationRouter(pinia: Pinia, history: RouterHistory = createWebHistory()) {
  const router = createRouter({ history, routes })
  router.beforeEach((to) => {
    const session = useSessionStore(pinia)
    if (to.meta.permission === 'review' && !session.canReview) return { name: 'templates' }
    if (to.meta.permission === 'template' && !session.canManageTemplates) return { name: 'dashboard' }
    return true
  })
  return router
}
