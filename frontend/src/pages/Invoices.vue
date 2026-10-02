<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { RouterLink } from 'vue-router'
import { Button } from 'frappe-ui'
import { call } from '../api'

interface Inv { name: string; total_due: number; status: string; due_date: string }
const list = ref<Inv[]>([])
onMounted(async () => {
  list.value = await call('lube_station.lube_station.portal.apis.my_invoices', {}, 'GET')
})
</script>

<template>
  <div class="space-y-3">
    <h1 class="text-xl font-semibold">Invoices</h1>
    <div v-for="i in list" :key="i.name" class="flex items-center justify-between rounded border p-3 text-sm">
      <div><div class="font-medium">{{ i.name }}</div><div>{{ i.status }} · due {{ i.due_date }} · {{ i.total_due }}</div></div>
      <RouterLink v-if="i.status !== 'Paid'" :to="`/pay/${i.name}`"><Button label="Pay" variant="solid" size="sm" /></RouterLink>
    </div>
  </div>
</template>
