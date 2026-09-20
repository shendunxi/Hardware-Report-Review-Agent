import { defineStore } from 'pinia'
import { computed, ref } from 'vue'

import { apiClient } from '../api/client'
import type { TemplateAuditEvent, TemplateDetail, TemplateRule, TemplateSummary } from '../domain/types'

export const useTemplateStore = defineStore('templates', () => {
  const templates = ref<TemplateSummary[]>([])
  const selected = ref<TemplateDetail | null>(null)
  const auditEvents = ref<TemplateAuditEvent[]>([])
  const loading = ref(false)
  const error = ref<Error | null>(null)
  const publishedTemplates = computed(() => templates.value.filter((item) => item.status === 'PUBLISHED'))

  async function run<T>(operation: () => Promise<T>): Promise<T> {
    loading.value = true
    error.value = null
    try { return await operation() } catch (caught) {
      error.value = caught instanceof Error ? caught : new Error('请求失败')
      throw caught
    } finally { loading.value = false }
  }
  async function loadTemplates() { return run(async () => (templates.value = (await apiClient.listTemplates()).templates)) }
  async function loadTemplate(id: string) {
    return run(async () => {
      const [detail, audit] = await Promise.all([
        apiClient.getTemplate(id),
        apiClient.listTemplateAuditEvents(id),
      ])
      selected.value = detail
      auditEvents.value = audit.events
      return detail
    })
  }
  async function upload(input: { source: File; name: string; version: string }) { await run(() => apiClient.uploadTemplate(input)); return loadTemplates() }
  async function updateRule(templateId: string, ruleId: string, changes: Partial<TemplateRule>) { await run(() => apiClient.updateTemplateRule(templateId, ruleId, changes)); return loadTemplate(templateId) }
  async function addRule(templateId: string, rule: Partial<TemplateRule>) { await run(() => apiClient.addTemplateRule(templateId, rule)); return loadTemplate(templateId) }
  async function deleteRule(templateId: string, ruleId: string) { await run(() => apiClient.deleteTemplateRule(templateId, ruleId)); return loadTemplate(templateId) }
  async function publish(templateId: string) { await run(() => apiClient.publishTemplate(templateId)); await loadTemplates(); return loadTemplate(templateId) }
  async function retire(templateId: string) { await run(() => apiClient.retireTemplate(templateId)); await loadTemplates(); return loadTemplate(templateId) }
  return { templates, selected, auditEvents, loading, error, publishedTemplates, loadTemplates, loadTemplate, upload, updateRule, addRule, deleteRule, publish, retire }
})
