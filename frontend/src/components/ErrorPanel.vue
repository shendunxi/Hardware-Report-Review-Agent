<script setup lang="ts">defineProps<{ error: Error | null }>(); defineEmits<{ dismiss: [] }>()</script>
<template><div v-if="error" class="error-panel" role="alert"><div><strong>操作未完成</strong><p>{{ error.message }}</p></div><button class="btn btn-ghost" @click="$emit('dismiss')">关闭</button></div></template>
