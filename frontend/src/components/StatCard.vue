<script setup lang="ts">
import { RouterLink } from 'vue-router'

defineProps<{ value: string | number; label: string; to?: string }>()
</script>

<template>
  <component
    :is="to ? RouterLink : 'div'"
    :to="to"
    class="rounded-lg border border-outline-gray-1 bg-surface-white p-4"
  >
    <div class="text-2xl font-semibold tracking-tight">{{ value }}</div>
    <div class="mt-1 text-sm text-ink-gray-5">{{ label }}</div>
  </component>
</template>
