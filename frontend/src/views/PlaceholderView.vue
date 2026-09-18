<script setup lang="ts">
import { useRoute } from 'vue-router'

const route = useRoute()
</script>

<template>
  <section class="panel placeholder vue-placeholder">
    <span>构</span>
    <h1>{{ route.meta.title }}</h1>
    <p>该工作流正在迁移到 Vue 3。</p>
  </section>
</template>
