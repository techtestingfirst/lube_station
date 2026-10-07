<script setup lang="ts">
import { Badge } from 'frappe-ui'
import { computed } from 'vue'

const props = defineProps<{ status: string | null | undefined }>()

const theme = computed(() => {
  switch ((props.status || '').toLowerCase()) {
    case 'active':
    case 'paid':
    case 'success':
    case 'available':
    case 'registered':
      return 'green'
    case 'suspended':
    case 'overdue':
    case 'failed':
    case 'terminated':
      return 'red'
    case 'pending':
    case 'unpaid':
    case 'provisioning':
    case 'taken':
      return 'amber'
    case 'cancelled':
    case 'expired':
      return 'gray'
    default:
      return 'blue'
  }
})
</script>

<template>
  <Badge :theme="theme" size="md">{{ status || '—' }}</Badge>
</template>
