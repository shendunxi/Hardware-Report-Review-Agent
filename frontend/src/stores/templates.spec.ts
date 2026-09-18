import { beforeEach, describe, expect, it, vi } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'

import { useTemplateStore } from './templates'

describe('template store', () => {
  beforeEach(() => setActivePinia(createPinia()))

  it('exposes only published templates for creating tasks', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response(JSON.stringify({ templates: [
      { id: 'a', status: 'DRAFT' }, { id: 'b', status: 'PUBLISHED' }, { id: 'c', status: 'RETIRED' },
    ] }), { status: 200 })))
    const store = useTemplateStore()
    await store.loadTemplates()
    expect(store.publishedTemplates.map((item) => item.id)).toEqual(['b'])
  })
})
