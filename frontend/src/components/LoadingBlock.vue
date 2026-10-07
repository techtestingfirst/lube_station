<script setup lang="ts">
import { Skeleton } from 'frappe-ui'

defineProps<{ lines?: number }>()
</script>

<template>
  <div class="space-y-2" aria-label="Loading">
    <Skeleton v-for="i in (lines ?? 3)" :key="i" class="h-12 w-full rounded-lg" />
  </div>
</template>
