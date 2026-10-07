<script setup lang="ts">
import { Button, ErrorMessage } from 'frappe-ui'

defineProps<{ message: string }>()
defineEmits<{ retry: [] }>()
</script>

<template>
  <div class="space-y-3 rounded-lg border border-outline-red-2 bg-surface-red-1 px-4 py-4">
    <ErrorMessage :message="message" />
    <Button variant="outline" size="sm" @click="$emit('retry')">Try again</Button>
  </div>
</template>
