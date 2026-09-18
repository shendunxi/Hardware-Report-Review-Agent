import { mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { createMemoryHistory } from 'vue-router'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import AppShell from './AppShell.vue'
import { createApplicationRouter } from '../router'
import { useSessionStore } from '../stores/session'

async function renderShell(role: 'tester' | 'admin' | 'combined') {
  const pinia = createPinia()
  setActivePinia(pinia)
  useSessionStore().setRole(role)
  const router = createApplicationRouter(pinia, createMemoryHistory())
  await router.push(role === 'admin' ? '/templates' : '/')
  await router.isReady()
  return mount(AppShell, { global: { plugins: [pinia, router] } })
}

describe('AppShell navigation', () => {
  beforeEach(() => {
    vi.stubGlobal('fetch', vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      if (String(input).endsWith('/api/session/local')) {
        const selected = JSON.parse(String(init?.body)).role as 'tester' | 'admin' | 'combined'
        const roles = selected === 'combined' ? ['review', 'template'] : selected === 'admin' ? ['template'] : ['review']
        const actor = selected === 'combined' ? '组合角色' : selected === 'admin' ? '模板规则管理' : '测试报告审核'
        return new Response(JSON.stringify({ actor, roles, role: selected }), { status: 200 })
      }
      return new Response(JSON.stringify({ tasks: [], templates: [] }), { status: 200 })
    }))
  })
  it('shows review navigation without template administration to the tester role', async () => {
    const wrapper = await renderShell('tester')
    expect(wrapper.text()).toContain('审核工作台')
    expect(wrapper.text()).toContain('创建任务')
    expect(wrapper.text()).not.toContain('模板管理')
  })

  it('shows both navigation groups to the combined role', async () => {
    const wrapper = await renderShell('combined')
    expect(wrapper.text()).toContain('审核任务')
    expect(wrapper.text()).toContain('模板管理')
  })
})
