import { beforeEach, describe, expect, it, vi } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'

import { useTaskStore } from './tasks'

describe('task store', () => {
  beforeEach(() => setActivePinia(createPinia()))

  it('loads the persisted task list', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response(JSON.stringify({ tasks: [{ id: 't1', state: 'CREATED', display_name: '样例' }] }), { status: 200 })))
    const store = useTaskStore()
    await store.loadTasks()
    expect(store.tasks).toHaveLength(1)
    expect(store.tasks[0]?.display_name).toBe('样例')
  })

  it('creates a task and immediately requests execution', async () => {
    const fetchMock = vi.fn()
      .mockResolvedValueOnce(new Response(JSON.stringify({ id: 't1', state: 'FILES_STAGED' }), { status: 201 }))
      .mockResolvedValueOnce(new Response(JSON.stringify({ id: 't1', state: 'PARSING' }), { status: 202 }))
    vi.stubGlobal('fetch', fetchMock)
    const store = useTaskStore()
    const task = await store.createAndExecute({ templateId: 'tpl', primaryReport: new File(['x'], 'report.xls'), supportingFiles: [] })
    expect(task.state).toBe('PARSING')
    expect(fetchMock).toHaveBeenCalledTimes(2)

    // A run interrupted by a process death is recoverable: re-requesting execution
    // must reuse the same endpoint and then reload the task.
    fetchMock
      .mockResolvedValueOnce(new Response(JSON.stringify({ id: 't1', state: 'FILES_STAGED' }), { status: 202 }))
      .mockResolvedValueOnce(new Response(JSON.stringify({ id: 't1', state: 'READY_FOR_REVIEW', execution: null }), { status: 200 }))
    const recovered = await store.reexecute('t1')
    expect(recovered.state).toBe('READY_FOR_REVIEW')
    expect(recovered.execution).toBeNull()
    expect(fetchMock).toHaveBeenCalledTimes(4)
    expect(String(fetchMock.mock.calls[2]?.[0])).toContain('/api/tasks/t1/execute')
  })
})
