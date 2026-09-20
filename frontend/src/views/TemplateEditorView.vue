<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'
import { useRoute } from 'vue-router'

import StatusBadge from '../components/StatusBadge.vue'
import type { TemplateAuditEvent, TemplateRule } from '../domain/types'
import { useTemplateStore } from '../stores/templates'

const route = useRoute()
const store = useTemplateStore()
const id = String(route.params.templateId)
const editing = ref<string | null>(null)
const detail = computed(() => store.selected)
const hasBlockingFindings = computed(() =>
  detail.value?.template.validation_findings.some((item) => item.severity === 'ERROR') ?? false,
)

const form = reactive({
  rule_id: '', summary: '', verifiable_requirement: '', required_materials: '',
  main_judgment: 'RULE' as TemplateRule['main_judgment'], confirmed_boundary: '', enabled: true,
})

const actionLabels: Record<TemplateAuditEvent['action'], string> = {
  TEMPLATE_UPLOADED: '上传模板', RULE_CREATED: '新增校验项', RULE_UPDATED: '修改校验项',
  RULE_DELETED: '删除校验项', TEMPLATE_PUBLISHED: '发布模板', TEMPLATE_RETIRED: '停用模板',
}
const fieldLabels: Record<string, string> = {
  status: '状态', summary: '摘要', verifiable_requirement: '可验证要求',
  required_materials: '必需材料', main_judgment: '判定方式', confirmed_boundary: '确认边界',
  enabled: '启用状态', effective_rules: '启用项数',
}

onMounted(() => { void store.loadTemplate(id).catch(() => undefined) })

function edit(rule: TemplateRule) {
  editing.value = rule.rule_id
  Object.assign(form, {
    rule_id: rule.rule_id, summary: rule.summary,
    verifiable_requirement: rule.verifiable_requirement, required_materials: rule.required_materials,
    main_judgment: rule.main_judgment, confirmed_boundary: rule.confirmed_boundary, enabled: rule.enabled,
  })
}

function reset() {
  editing.value = null
  Object.assign(form, {
    rule_id: '', summary: '', verifiable_requirement: '', required_materials: '',
    main_judgment: 'RULE', confirmed_boundary: '', enabled: true,
  })
}

async function save() {
  const payload = {
    summary: form.summary, verifiable_requirement: form.verifiable_requirement,
    required_materials: form.required_materials, main_judgment: form.main_judgment,
    confirmed_boundary: form.confirmed_boundary, enabled: form.enabled,
  }
  if (editing.value) await store.updateRule(id, editing.value, payload)
  else await store.addRule(id, { rule_id: form.rule_id, ...payload })
  reset()
}

function changeSummary(event: TemplateAuditEvent): string {
  if (!event.before && event.after) return event.rule_id ? `新增 ${event.rule_id}` : `创建版本 ${event.template_version}`
  if (event.before && !event.after) return `删除 ${event.rule_id ?? event.template_version}`
  const keys = new Set([...Object.keys(event.before ?? {}), ...Object.keys(event.after ?? {})])
  const changed = [...keys].filter((key) => event.before?.[key] !== event.after?.[key])
  return changed.map((key) => fieldLabels[key] ?? key).join('、') || '记录操作'
}
</script>

<template>
  <section v-if="detail" class="page-stack">
    <header class="page-header">
      <div><p class="eyebrow">模板规则管理</p><h1>{{ detail.template.name }} · {{ detail.template.version }}</h1><p>{{ detail.rules.length }} 个校验项 · 源文件 {{ detail.template.source_filename }}</p></div>
      <div class="button-row"><StatusBadge :status="detail.template.status"/><button v-if="detail.template.status==='DRAFT'" class="btn btn-primary" :disabled="hasBlockingFindings" @click="store.publish(id)">发布模板</button><button v-if="detail.template.status==='PUBLISHED'" class="btn btn-secondary" @click="store.retire(id)">停用模板</button></div>
    </header>
    <article v-if="detail.template.validation_findings.length" class="panel"><h2>模板校验提示</h2><ul><li v-for="item in detail.template.validation_findings" :key="`${item.code}-${item.structural_address}`"><strong>{{ item.severity==='ERROR' ? '阻塞' : '提示' }}：</strong>{{ item.message }} <span>{{ item.structural_address }}</span></li></ul></article>
    <div class="editor-grid">
      <article class="panel"><div class="panel-heading"><h2>校验项</h2><button v-if="detail.template.status==='DRAFT'" class="btn btn-ghost" @click="reset">新增校验项</button></div><div class="rule-list"><button v-for="rule in detail.rules" :key="rule.rule_id" :class="{active:editing===rule.rule_id}" @click="edit(rule)"><span>{{ rule.rule_id }}</span><strong>{{ rule.summary }}</strong><small>{{ rule.enabled ? rule.main_judgment : '已禁用' }}</small></button></div></article>
      <form v-if="detail.template.status==='DRAFT'" class="panel form-stack" @submit.prevent="save"><h2>{{ editing ? `编辑 ${editing}` : '新增校验项' }}</h2><label v-if="!editing"><span>规则编号</span><input v-model="form.rule_id" required placeholder="如 A11-12"></label><label><span>摘要</span><input v-model="form.summary" required></label><label><span>可验证要求</span><textarea v-model="form.verifiable_requirement" required rows="3"/></label><label><span>必需材料</span><textarea v-model="form.required_materials" rows="2"/></label><label><span>主要判定方式</span><select v-model="form.main_judgment"><option value="RULE">规则匹配</option><option value="RULE_PLUS_AI">规则 + 大模型</option><option value="AI">大模型语义判断</option><option value="MANUAL">人工确认</option><option value="DISABLED">禁用</option></select></label><label><span>确认边界</span><textarea v-model="form.confirmed_boundary" rows="2"/></label><label class="check-row"><input v-model="form.enabled" type="checkbox">启用该校验项</label><div class="button-row"><button class="btn btn-primary">保存校验项</button><button v-if="editing" type="button" class="btn btn-danger" @click="store.deleteRule(id,editing); reset()">删除</button></div></form>
      <article v-else class="panel readonly-note"><h2>当前版本只读</h2><p>已发布或已停用模板不能修改校验项；如需调整，请上传新的模板版本。</p></article>
    </div>
    <article class="panel audit-panel">
      <div class="panel-heading"><div><p class="eyebrow">不可覆盖的操作记录</p><h2>模板审计时间线</h2></div><span>{{ store.auditEvents.length }} 条</span></div>
      <ol v-if="store.auditEvents.length" class="audit-timeline">
        <li v-for="event in store.auditEvents" :key="event.id">
          <span class="audit-dot" aria-hidden="true"></span>
          <div><strong>{{ actionLabels[event.action] }}</strong><p>{{ changeSummary(event) }}</p><small>{{ event.actor }} · {{ new Date(event.occurred_at).toLocaleString('zh-CN') }}<template v-if="event.rule_id"> · {{ event.rule_id }}</template></small></div>
        </li>
      </ol>
      <p v-else class="empty-cell">该模板暂无用户操作记录。</p>
    </article>
  </section>
  <p v-else class="loading-state">正在读取模板…</p>
</template>
