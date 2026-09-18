import { defineStore } from 'pinia'
import { computed, ref } from 'vue'

import { ApiError, apiClient } from '../api/client'
import type { FinalStatus, ReviewTask, SupportingUpload } from '../domain/types'

export const useTaskStore = defineStore('tasks', () => {
  const tasks = ref<ReviewTask[]>([])
  const selected = ref<ReviewTask | null>(null)
  const loading = ref(false)
  const error = ref<ApiError | Error | null>(null)
  const transientStates = new Set(['FILES_STAGED', 'PARSING', 'PARSED', 'EVALUATING'])

  const isSelectedTransient = computed(() => !!selected.value && transientStates.has(selected.value.state))

  async function run<T>(operation: () => Promise<T>): Promise<T> {
    loading.value = true
    error.value = null
    try { return await operation() } catch (caught) {
      error.value = caught instanceof Error ? caught : new Error('请求失败')
      throw caught
    } finally { loading.value = false }
  }

  async function loadTasks() {
    return run(async () => {
      const response = await apiClient.listTasks()
      tasks.value = response.tasks
      return tasks.value
    })
  }

  async function loadTask(taskId: string) {
    return run(async () => {
      selected.value = await apiClient.getTask(taskId)
      return selected.value
    })
  }

  async function createAndExecute(input: { templateId: string; primaryReport: File; supportingFiles: SupportingUpload[] }) {
    return run(async () => {
      const created = await apiClient.createTask(input)
      selected.value = await apiClient.executeTask(created.id)
      return selected.value
    })
  }

  async function saveDecision(taskId: string, ruleId: string, finalStatus: FinalStatus, reason: string) {
    await run(() => apiClient.saveManualDecision(taskId, ruleId, { finalStatus, reason }))
    return loadTask(taskId)
  }

  async function complete(taskId: string) {
    await run(() => apiClient.completeTask(taskId))
    return loadTask(taskId)
  }

  async function reopen(taskId: string) {
    await run(() => apiClient.reopenTask(taskId))
    return loadTask(taskId)
  }

  function clearError() { error.value = null }

  return { tasks, selected, loading, error, isSelectedTransient, loadTasks, loadTask, createAndExecute, saveDecision, complete, reopen, clearError }
})
