<script setup lang="ts">
import { ref, watch } from 'vue'

import { localizeReviewText } from '../domain/review'
import type { FinalStatus, ReviewRow } from '../domain/types'
import StatusBadge from './StatusBadge.vue'

const props = defineProps<{ row: ReviewRow; editable: boolean; busy?: boolean }>()
const emit = defineEmits<{ save: [payload: { ruleId: string; finalStatus: FinalStatus; reason: string }] }>()
const judgmentLabels = { RULE: '规则匹配', RULE_PLUS_AI: '规则 + 大模型', AI: '大模型语义判断', MANUAL: '人工确认', DISABLED: '已禁用' }
const finalStatus = ref<FinalStatus>('COMPLIANT')
const reason = ref('')

function resetDraft() {
  finalStatus.value = props.row.finalStatus
    ?? (props.row.initialStatus === 'NEEDS_REVIEW' ? 'COMPLIANT' : props.row.initialStatus)
  reason.value = props.row.decision?.reason ?? ''
}
watch(() => props.row, resetDraft, { immediate: true })

function submit() {
  if (!reason.value.trim()) return
  emit('save', { ruleId: props.row.ruleId, finalStatus: finalStatus.value, reason: reason.value.trim() })
}
</script>

<template>
  <article class="panel review-card">
    <div class="review-heading">
      <div><p class="eyebrow">{{ row.ruleId }}</p><h2>{{ row.rule?.summary ?? `校验项 ${row.ruleId}` }}</h2></div>
      <StatusBadge :status="row.displayStatus" />
    </div>
    <div class="decision-status-grid">
      <div><span>系统初判</span><StatusBadge :status="row.initialStatus" /></div>
      <div><span>人工最终状态</span><StatusBadge v-if="row.finalStatus" :status="row.finalStatus" /><strong v-else class="inherited-status">未修改（沿用系统初判）</strong></div>
      <div><span>判定来源</span><strong>{{ row.rule ? judgmentLabels[row.rule.main_judgment] : row.result.engine_version }}</strong></div>
    </div>
    <div v-if="row.rule" class="rule-context">
      <p><strong>规则要求：</strong>{{ row.rule.verifiable_requirement }}</p>
      <p><strong>所需材料：</strong>{{ row.rule.required_materials || '无额外材料要求' }}</p>
      <p v-if="row.rule.confirmed_boundary"><strong>确认边界：</strong>{{ row.rule.confirmed_boundary }}</p>
    </div>
    <p><strong>系统判定依据：</strong>{{ localizeReviewText(row.result.basis_text) }}</p>
    <p v-if="row.result.evidence_locators.length"><strong>证据：</strong>{{ row.result.evidence_locators.map(e => `${e.container} ${e.structural_address}`).join('；') }}</p>
    <p v-if="row.result.missing_materials.length"><strong>缺少材料：</strong>{{ row.result.missing_materials.join('、') }}</p>
    <p v-if="row.result.unresolved_semantics.length"><strong>待确认原因：</strong>{{ row.result.unresolved_semantics.map(localizeReviewText).join('；') }}</p>
    <div v-if="row.decision" class="manual-decision-record">
      <strong>人工复核记录</strong><p>{{ row.decision.reason }}</p><small>{{ row.decision.actor }} · {{ new Date(row.decision.decided_at).toLocaleString('zh-CN') }}</small>
    </div>
    <form v-if="editable" class="decision-form" @submit.prevent="submit">
      <select v-model="finalStatus" aria-label="人工最终状态"><option value="COMPLIANT">符合</option><option value="NON_COMPLIANT">不符合</option><option value="NOT_APPLICABLE">不适用</option></select>
      <input v-model="reason" required aria-label="修改原因" placeholder="填写人工修改原因">
      <button class="btn btn-secondary" :disabled="busy">保存人工判定</button>
    </form>
  </article>
</template>
