<script setup lang="ts">
import { computed, onMounted } from 'vue'
import { useTaskStore } from '../stores/tasks'
import StatusBadge from '../components/StatusBadge.vue'
const store = useTaskStore()
onMounted(() => { void store.loadTasks().catch(() => undefined) })
const pending = computed(() => store.tasks.filter((t) => t.state === 'READY_FOR_REVIEW').length)
const completed = computed(() => store.tasks.filter((t) => t.state === 'COMPLETED').length)
</script>
<template><section class="page-stack"><header class="page-header"><div><p class="eyebrow">审核工作台</p><h1>硬件测试报告审核</h1><p>客观规则优先匹配，语义项由大模型辅助，证据不足时进入人工复核。</p></div><RouterLink class="btn btn-primary" to="/tasks/new">创建审核任务</RouterLink></header><div class="metric-grid"><article class="metric-card"><span>全部任务</span><strong>{{ store.tasks.length }}</strong></article><article class="metric-card"><span>待人工复核</span><strong>{{ pending }}</strong></article><article class="metric-card"><span>已完成</span><strong>{{ completed }}</strong></article></div><article class="panel"><div class="panel-heading"><h2>最近任务</h2><RouterLink to="/tasks">查看全部</RouterLink></div><div class="table-wrap"><table><thead><tr><th>报告</th><th>模板</th><th>状态</th><th>更新时间</th></tr></thead><tbody><tr v-for="task in store.tasks.slice(0, 8)" :key="task.id"><td><RouterLink :to="`/tasks/${task.id}`">{{ task.display_name }}</RouterLink></td><td>{{ task.template_name }} {{ task.template_version }}</td><td><StatusBadge :status="task.state" /></td><td>{{ new Date(task.updated_at).toLocaleString('zh-CN') }}</td></tr><tr v-if="!store.tasks.length"><td colspan="4" class="empty-cell">暂无任务</td></tr></tbody></table></div></article></section></template>
