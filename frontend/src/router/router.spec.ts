import { createPinia, setActivePinia } from 'pinia'
import { createMemoryHistory } from 'vue-router'
import { describe, expect, it } from 'vitest'

import { createApplicationRouter } from './index'
import { useSessionStore } from '../stores/session'

describe('permission-aware router', () => {
  it('redirects a template-only role away from review routes', async () => {
    const pinia = createPinia()
    setActivePinia(pinia)
    useSessionStore().setRole('admin')
    const router = createApplicationRouter(pinia, createMemoryHistory())

    await router.push('/tasks')

    expect(router.currentRoute.value.name).toBe('templates')
  })

  it('redirects a review-only role away from template routes', async () => {
    const pinia = createPinia()
    setActivePinia(pinia)
    useSessionStore().setRole('tester')
    const router = createApplicationRouter(pinia, createMemoryHistory())

    await router.push('/templates')

    expect(router.currentRoute.value.name).toBe('dashboard')
  })
})
