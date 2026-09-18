<script setup lang="ts">
import { onMounted } from 'vue'
import { RouterLink, RouterView, useRouter } from 'vue-router'

import type { RoleId } from '../domain/types'
import { roleOptions, useSessionStore } from '../stores/session'

const session = useSessionStore()
const router = useRouter()

onMounted(() => { void session.establish().catch(() => undefined) })

async function changeRole(event: Event) {
  const requested = (event.target as HTMLSelectElement).value as RoleId
  await session.selectRole(requested).catch(() => undefined)
  if (!session.canReview && router.currentRoute.value.meta.permission === 'review') router.push({ name: 'templates' })
  if (!session.canManageTemplates && router.currentRoute.value.meta.permission === 'template') router.push({ name: 'dashboard' })
}
</script>

<template>
  <div class="vue-app-shell">
    <aside class="vue-sidebar">
      <div class="vue-brand"><span class="brand-mark">智</span><strong>硬件测试报告审核智能体</strong></div>
      <nav aria-label="主导航">
        <template v-if="session.canReview">
          <span class="nav-section-label">审核流程</span>
          <RouterLink to="/">审核工作台</RouterLink>
          <RouterLink to="/tasks">审核任务</RouterLink>
          <RouterLink to="/tasks/new">创建任务</RouterLink>
        </template>
        <template v-if="session.canManageTemplates">
          <span class="nav-section-label">模板规则</span>
          <RouterLink to="/templates">模板管理</RouterLink>
        </template>
      </nav>
      <div class="vue-boundary-note">本地真实 API<br><small>本地会话 · 服务端权限校验</small></div>
    </aside>
    <div class="vue-workspace">
      <header class="vue-topbar">
        <div><strong>A11 审核中心</strong><span class="status-badge status-success"><b>●</b>服务已连接</span></div>
        <label>
          <span>当前角色</span>
          <select :value="session.role" aria-label="切换当前角色" :disabled="session.loading" @change="changeRole">
            <option v-for="role in roleOptions" :key="role.id" :value="role.id">{{ role.label }}</option>
          </select>
        </label>
      </header>
      <main class="vue-main" tabindex="-1">
        <RouterView v-if="session.ready" />
        <section v-else-if="session.error" class="panel session-state">
          <h2>本地会话建立失败</h2><p>{{ session.error.message }}</p>
          <button class="btn btn-primary" :disabled="session.loading" @click="session.establish">重试</button>
        </section>
        <p v-else class="loading-state">正在建立本地会话…</p>
      </main>
    </div>
  </div>
</template>
