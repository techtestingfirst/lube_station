<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { RouterLink, useRoute } from 'vue-router'
import { Button } from 'frappe-ui'
import { call } from '../api'

const route = useRoute()
const order = route.params.order as string
const detail = ref<{ order: { name: string; status: string; total: number }; invoices: { name: string; status: string; total_due: number }[] } | null>(null)

onMounted(async () => {
  detail.value = await call('lube_station.lube_station.portal.apis.my_order_detail', { order }, 'GET')
})

function pdfUrl(name: string): string {
  const q = new URLSearchParams({ doctype: 'Hosting Invoice', name, format: 'Hosting Invoice' })
  return `/api/method/frappe.utils.print_format.download_pdf?${q.toString()}`
}
</script>

<template>
  <div class="space-y-4">
    <h1 class="text-xl font-semibold">Order received</h1>
    <div v-if="detail" class="space-y-3 text-sm">
      <div class="rounded border p-3">
        <div class="font-medium">{{ detail.order.name }} · {{ detail.order.status }}</div>
        <div>Total: {{ detail.order.total }}</div>
      </div>
      <div v-for="inv in detail.invoices" :key="inv.name" class="flex items-center justify-between rounded border p-3">
        <div>Invoice {{ inv.name }} · {{ inv.status }} · {{ inv.total_due }}</div>
        <div class="flex gap-2">
          <a :href="pdfUrl(inv.name)" target="_blank" rel="noopener"><Button label="PDF" size="sm" /></a>
          <RouterLink v-if="inv.status !== 'Paid'" :to="`/pay/${inv.name}`"><Button label="Pay now" variant="solid" size="sm" /></RouterLink>
        </div>
      </div>
      <p class="text-xs text-gray-500">Services activate automatically once payment clears. Credentials arrive by email.</p>
      <RouterLink to="/services"><Button label="View my services" /></RouterLink>
    </div>
  </div>
</template>
