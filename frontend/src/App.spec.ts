import { render, screen } from '@testing-library/vue'
import { createPinia } from 'pinia'
import { createMemoryHistory, createRouter } from 'vue-router'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import App from './App.vue'

describe('application shell', () => {
  beforeEach(() => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response(JSON.stringify({
      actor: '测试报告审核', roles: ['review'], role: 'tester',
    }), { status: 200, headers: { 'content-type': 'application/json' } })))
  })

  it('keeps the approved product and role names visible', async () => {
    const router = createRouter({
      history: createMemoryHistory(),
      routes: [
        { path: '/', component: { template: '<div>首页</div>' } },
        { path: '/tasks', component: { template: '<div>任务</div>' } },
        { path: '/tasks/new', component: { template: '<div>创建</div>' } },
      ],
    })
    router.push('/')
    await router.isReady()

    render(App, { global: { plugins: [createPinia(), router] } })

    expect(screen.getByText('硬件测试报告审核智能体')).toBeTruthy()
    expect(screen.getByRole('option', { name: '测试报告审核' })).toBeTruthy()
    expect(screen.getByRole('option', { name: '模板规则管理' })).toBeTruthy()
  })
})
