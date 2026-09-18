<script setup lang="ts">
defineProps<{ status: string }>()
const labels: Record<string, string> = {
  CREATED: '已创建', FILES_STAGED: '文件已接收', PARSING: '解析中', PARSED: '已解析', EVALUATING: '审核中',
  READY_FOR_REVIEW: '待人工复核', FAILED: '处理失败', COMPLETED: '已完成', DRAFT: '草稿', PUBLISHED: '已发布', RETIRED: '已停用',
  COMPLIANT: '符合', NON_COMPLIANT: '不符合', NOT_APPLICABLE: '不适用', NEEDS_REVIEW: '待人工确认',
}
</script>
<template><span class="status-badge" :data-status="status">{{ labels[status] ?? status }}</span></template>
