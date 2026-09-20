import type {
  FinalStatus,
  ManualDecision,
  ReviewTask,
  RoleId,
  SessionContext,
  SupportingUpload,
  TemplateDetail,
  TemplateAuditEvent,
  TemplateRule,
  TemplateSummary,
} from '../domain/types'

interface ErrorEnvelope {
  error?: { code?: string; message?: string; details?: Record<string, unknown> }
}

export class ApiError extends Error {
  readonly status: number
  readonly code: string
  readonly details: Record<string, unknown>

  constructor(status: number, payload: ErrorEnvelope) {
    const error = payload.error ?? {}
    super(error.message || `请求失败（HTTP ${status}）`)
    this.name = 'ApiError'
    this.status = status
    this.code = error.code || 'HTTP_ERROR'
    this.details = error.details ?? {}
  }
}

export class ApiClient {
  private readonly baseUrl: string
  private readonly fetchImpl: typeof fetch

  constructor(options: { baseUrl?: string; fetchImpl?: typeof fetch } = {}) {
    this.baseUrl = (options.baseUrl ?? '').replace(/\/$/, '')
    this.fetchImpl = options.fetchImpl ?? ((input, init) => window.fetch(input, init))
  }

  private async request<T>(path: string, init: RequestInit = {}): Promise<T> {
    const response = await this.fetchImpl(`${this.baseUrl}${path}`, { ...init, credentials: 'same-origin' })
    const payload = response.status === 204 ? null : await response.json()
    if (!response.ok) throw new ApiError(response.status, (payload ?? {}) as ErrorEnvelope)
    return payload as T
  }

  selectLocalSession(role: RoleId): Promise<SessionContext> {
    return this.request('/api/session/local', {
      method: 'POST',
      headers: { 'content-type': 'application/json' },
      body: JSON.stringify({ role }),
    })
  }

  listTasks(): Promise<{ tasks: ReviewTask[] }> {
    return this.request('/api/tasks')
  }

  getTask(taskId: string): Promise<ReviewTask> {
    return this.request(`/api/tasks/${encodeURIComponent(taskId)}`)
  }

  createTask(input: { templateId: string; primaryReport: File; supportingFiles: SupportingUpload[] }): Promise<ReviewTask> {
    if (!input.templateId) throw new TypeError('templateId is required')
    if (!input.primaryReport) throw new TypeError('primaryReport is required')
    const form = new FormData()
    form.append('template_id', input.templateId)
    form.append('primary_report', input.primaryReport)
    for (const support of input.supportingFiles) form.append('supporting_files', support.file)
    form.append('supporting_manifest', JSON.stringify(input.supportingFiles.map((support) => ({
      evidence_kinds: [...support.evidenceKinds],
    }))))
    return this.request('/api/tasks', { method: 'POST', body: form })
  }

  executeTask(taskId: string): Promise<ReviewTask> {
    return this.request(`/api/tasks/${encodeURIComponent(taskId)}/execute`, { method: 'POST' })
  }

  saveManualDecision(taskId: string, ruleId: string, input: { finalStatus: FinalStatus; reason: string }): Promise<ManualDecision> {
    return this.request(`/api/tasks/${encodeURIComponent(taskId)}/rules/${encodeURIComponent(ruleId)}/manual-decision`, {
      method: 'PUT',
      headers: { 'content-type': 'application/json' },
      body: JSON.stringify({ final_status: input.finalStatus, reason: input.reason, supplemental_evidence: [] }),
    })
  }

  completeTask(taskId: string): Promise<ReviewTask & { revision: unknown }> {
    return this.request(`/api/tasks/${encodeURIComponent(taskId)}/complete`, { method: 'POST' })
  }

  reopenTask(taskId: string): Promise<ReviewTask> {
    return this.request(`/api/tasks/${encodeURIComponent(taskId)}/reopen`, { method: 'POST' })
  }

  checklistUrl(taskId: string): string {
    return `${this.baseUrl}/api/tasks/${encodeURIComponent(taskId)}/export`
  }

  listTemplates(): Promise<{ templates: TemplateSummary[] }> {
    return this.request('/api/templates')
  }

  getTemplate(templateId: string): Promise<TemplateDetail> {
    return this.request(`/api/templates/${encodeURIComponent(templateId)}`)
  }

  listTemplateAuditEvents(templateId: string): Promise<{ events: TemplateAuditEvent[] }> {
    return this.request(`/api/templates/${encodeURIComponent(templateId)}/audit-events`)
  }

  uploadTemplate(input: { source: File; name: string; version: string }): Promise<TemplateSummary> {
    const form = new FormData()
    form.append('source', input.source)
    form.append('name', input.name)
    form.append('version', input.version)
    return this.request('/api/templates', { method: 'POST', body: form })
  }

  updateTemplateRule(templateId: string, ruleId: string, changes: Partial<TemplateRule>): Promise<TemplateRule> {
    return this.request(`/api/templates/${encodeURIComponent(templateId)}/rules/${encodeURIComponent(ruleId)}`, {
      method: 'PUT', headers: { 'content-type': 'application/json' }, body: JSON.stringify(changes),
    })
  }

  addTemplateRule(templateId: string, rule: Partial<TemplateRule>): Promise<TemplateRule> {
    return this.request(`/api/templates/${encodeURIComponent(templateId)}/rules`, {
      method: 'POST', headers: { 'content-type': 'application/json' }, body: JSON.stringify(rule),
    })
  }

  deleteTemplateRule(templateId: string, ruleId: string): Promise<null> {
    return this.request(`/api/templates/${encodeURIComponent(templateId)}/rules/${encodeURIComponent(ruleId)}`, { method: 'DELETE' })
  }

  publishTemplate(templateId: string): Promise<TemplateSummary> {
    return this.request(`/api/templates/${encodeURIComponent(templateId)}/publish`, { method: 'POST' })
  }

  retireTemplate(templateId: string): Promise<TemplateSummary> {
    return this.request(`/api/templates/${encodeURIComponent(templateId)}/retire`, { method: 'POST' })
  }
}

export const apiClient = new ApiClient()
