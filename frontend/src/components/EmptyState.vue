<script setup lang="ts">
import { Button } from 'frappe-ui'

defineProps<{ title: string; hint?: string; actionLabel?: string }>()
defineEmits<{ action: [] }>()
</script>

<template>
  <div class="rounded-lg border border-dashed border-outline-gray-2 px-4 py-10 text-center">
    <div class="text-sm font-medium">{{ title }}</div>
    <p v-if="hint" class="mx-auto mt-1 max-w-sm text-sm text-ink-gray-5">{{ hint }}</p>
    <Button v-if="actionLabel" class="mt-4" variant="solid" size="sm" @click="$emit('action')">
      {{ actionLabel }}
    </Button>
  </div>
</template>
