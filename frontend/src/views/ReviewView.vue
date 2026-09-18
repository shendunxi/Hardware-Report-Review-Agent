<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useRoute } from 'vue-router'

import { apiClient } from '../api/client'
import ReviewResultCard from '../components/ReviewResultCard.vue'
import { deriveReviewRows, deriveRevisionRows } from '../domain/review'
import type { FinalStatus } from '../domain/types'
import { useTaskStore } from '../stores/tasks'

const route = useRoute()
const store = useTaskStore()
const id = String(route.params.taskId)
const selectedRevisionNo = ref<number | null>(null)

onMounted(() => { void store.loadTask(id).catch(() => undefined) })

const currentRows = computed(() => store.selected ? deriveReviewRows(store.selected) : [])
const selectedRevision = computed(() => store.selected?.revisions.find(item => item.revision_no === selectedRevisionNo.value) ?? null)
const historicalRows = computed(() => selectedRevision.value?.snapshot ? deriveRevisionRows(selectedRevision.value.snapshot) : [])
const visibleRows = computed(() => selectedRevisionNo.value === null ? currentRows.value : historicalRows.value)
const unresolved = computed(() => currentRows.value.filter(row => row.displayStatus === 'NEEDS_REVIEW').length)
const isHistorical = computed(() => selectedRevisionNo.value !== null)

async function save(payload: { ruleId: string; finalStatus: FinalStatus; reason: string }) {
  await store.saveDecision(id, payload.ruleId, payload.finalStatus, payload.reason)
}
async function complete() { await store.complete(id) }
</script>

<template>
  <section v-if="store.selected" class="page-stack">
    <header class="page-header">
      <div><p class="eyebrow">审核结果</p><h1>{{ store.selected.display_name }}</h1><p>{{ currentRows.length }} 个校验项 · {{ unresolved }} 个待人工确认</p></div>
      <div class="button-row">
        <button v-if="store.selected.state === 'READY_FOR_REVIEW'" class="btn btn-primary" :disabled="unresolved > 0 || store.loading" @click="complete">完成审核</button>
        <button v-if="store.selected.state === 'COMPLETED'" class="btn btn-secondary" @click="store.reopen(id)">重新打开</button>
        <a v-if="store.selected.state === 'COMPLETED'" class="btn btn-primary" :href="apiClient.checklistUrl(id)">导出测试检查表</a>
      </div>
    </header>

    <div v-if="unresolved && !isHistorical" class="callout">所有“待人工确认”项完成复核后，才可完成审核。</div>

    <article v-if="store.selected.revisions.length" class="panel revision-navigator">
      <div class="panel-heading"><h2>审核修订历史</h2><span>已完成 {{ store.selected.revisions.length }} 版</span></div>
      <div class="revision-buttons">
        <button class="btn" :class="selectedRevisionNo === null ? 'btn-primary' : 'btn-ghost'" @click="selectedRevisionNo = null">当前审核</button>
        <button
          v-for="revision in store.selected.revisions"
          :key="revision.id"
          class="btn"
          :class="selectedRevisionNo === revision.revision_no ? 'btn-primary' : 'btn-ghost'"
          :disabled="!revision.snapshot"
          @click="selectedRevisionNo = revision.revision_no"
        >第 {{ revision.revision_no }} 版 · {{ new Date(revision.completed_at).toLocaleString('zh-CN') }}</button>
      </div>
    </article>

    <div class="review-mode-heading">
      <div>
        <p class="eyebrow">{{ isHistorical ? '不可变历史快照' : '当前活动结果' }}</p>
        <h2 v-if="selectedRevision">历史修订 · 第 {{ selectedRevision.revision_no }} 版</h2>
        <h2 v-else>当前审核结果</h2>
      </div>
      <span v-if="selectedRevision">完成于 {{ new Date(selectedRevision.completed_at).toLocaleString('zh-CN') }}</span>
    </div>

    <ReviewResultCard
      v-for="row in visibleRows"
      :key="`${isHistorical ? `revision-${selectedRevisionNo}` : 'current'}-${row.ruleId}`"
      :row="row"
      :editable="!isHistorical && store.selected.state !== 'COMPLETED'"
      :busy="store.loading"
      @save="save"
    />
  </section>
  <p v-else class="loading-state">正在读取审核结果…</p>
</template>
