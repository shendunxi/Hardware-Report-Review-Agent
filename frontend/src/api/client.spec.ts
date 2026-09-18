import { describe, expect, it, vi } from 'vitest'

import { ApiClient, ApiError } from './client'

describe('ApiClient', () => {
  it('creates a task with the selected template and aligned supporting metadata', async () => {
    const fetchImpl = vi.fn(async (_url: string, init?: RequestInit) =>
      new Response(JSON.stringify({ id: 'task-1', state: 'CREATED' }), {
        status: 201,
        headers: { 'content-type': 'application/json' },
      }),
    )
    const client = new ApiClient({ fetchImpl: fetchImpl as typeof fetch })
    const primary = new File(['primary'], 'report.xls', { type: 'application/vnd.ms-excel' })
    const support = new File(['evidence'], 'jira.pdf', { type: 'application/pdf' })

    await client.createTask({
      templateId: 'template-a11',
      primaryReport: primary,
      supportingFiles: [{ file: support, evidenceKinds: ['JIRA_RECORD', 'OTHER'] }],
    })

    const [url, init] = fetchImpl.mock.calls[0] as unknown as [string, RequestInit]
    expect(url).toBe('/api/tasks')
    expect(init.method).toBe('POST')
    const body = init.body as FormData
    expect(body.get('template_id')).toBe('template-a11')
    expect(body.get('primary_report')).toBe(primary)
    expect(body.getAll('supporting_files')).toEqual([support])
    expect(JSON.parse(String(body.get('supporting_manifest')))).toEqual([
      { evidence_kinds: ['JIRA_RECORD', 'OTHER'] },
    ])
  })

  it('raises the stable server error instead of an HTTP-only message', async () => {
    const client = new ApiClient({
      fetchImpl: vi.fn(async () =>
        new Response(
          JSON.stringify({ error: { code: 'TEMPLATE_STATE_INVALID', message: '创建任务只能选择已发布模板。', details: {} } }),
          { status: 409, headers: { 'content-type': 'application/json' } },
        ),
      ) as typeof fetch,
    })

    await expect(client.listTasks()).rejects.toMatchObject<ApiError>({
      status: 409,
      code: 'TEMPLATE_STATE_INVALID',
      message: '创建任务只能选择已发布模板。',
    })
  })
})
