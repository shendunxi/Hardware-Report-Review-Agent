import { computed, ref } from 'vue'
import { defineStore } from 'pinia'

import { apiClient } from '../api/client'
import type { RoleId } from '../domain/types'

export const roleOptions: ReadonlyArray<{ id: RoleId; label: string }> = [
  { id: 'tester', label: '测试报告审核' },
  { id: 'admin', label: '模板规则管理' },
  { id: 'combined', label: '组合角色' },
]

export const useSessionStore = defineStore('session', () => {
  const role = ref<RoleId>('tester')
  const actor = ref('')
  const ready = ref(false)
  const loading = ref(false)
  const error = ref<Error | null>(null)
  const canReview = computed(() => role.value === 'tester' || role.value === 'combined')
  const canManageTemplates = computed(() => role.value === 'admin' || role.value === 'combined')
  let establishing: Promise<void> | null = null

  function setRole(value: RoleId) {
    role.value = value
  }

  async function selectRole(value: RoleId) {
    loading.value = true
    error.value = null
    try {
      const context = await apiClient.selectLocalSession(value)
      role.value = context.role
      actor.value = context.actor
      ready.value = true
    } catch (caught) {
      error.value = caught instanceof Error ? caught : new Error('本地会话建立失败')
      throw caught
    } finally {
      loading.value = false
    }
  }

  function establish(): Promise<void> {
    if (ready.value) return Promise.resolve()
    if (!establishing) {
      establishing = selectRole(role.value).finally(() => { establishing = null })
    }
    return establishing
  }

  return { role, actor, ready, loading, error, canReview, canManageTemplates, setRole, selectRole, establish }
})
