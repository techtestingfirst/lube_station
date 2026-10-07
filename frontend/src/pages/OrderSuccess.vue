<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { RouterLink, useRoute, useRouter } from 'vue-router'
import { Badge, Button } from 'frappe-ui'
import { call, friendlyError } from '../api'
import { formatMoney } from '../format'
import EmptyState from '../components/EmptyState.vue'
import LoadingBlock from '../components/LoadingBlock.vue'
import StatusBadge from '../components/StatusBadge.vue'

const route = useRoute()
const router = useRouter()
const order = route.params.order as string
const detail = ref<{ order: { name: string; status: string; total: number }; invoices: { name: string; status: string; total_due: number }[] } | null>(null)
const loading = ref(true)

async function load() {
  loading.value = true
  try {
    detail.value = await call('lube_station.lube_station.portal.apis.my_order_detail', { order }, 'GET')
  } finally {
    loading.value = false
  }
}

onMounted(load)

function pdfUrl(name: string): string {
  const q = new URLSearchParams({ doctype: 'Hosting Invoice', name, format: 'Hosting Invoice' })
  return `/api/method/frappe.utils.print_format.download_pdf?${q.toString()}`
}
</script>

<template>
  <div class="space-y-6">
    <div class="flex items-start justify-between gap-3">
      <div>
        <h1 class="text-xl font-semibold tracking-tight text-ink-gray-8">Order received</h1>
        <p class="mt-1 text-sm text-ink-gray-5">Thank you — your order is confirmed and payment is next.</p>
      </div>
      <RouterLink to="/services" class="shrink-0">
        <Button label="View my services" variant="solid" />
      </RouterLink>
    </div>

    <LoadingBlock v-if="loading" :lines="3" />
    <EmptyState
      v-else-if="!detail"
      title="Order not found"
      hint="We could not load this order. It may belong to a different account."
      action-label="View my services"
      @action="router.push('/services')"
    />
    <div v-else class="space-y-4">
      <div class="rounded-lg border border-outline-gray-1 bg-surface-white p-4">
        <div class="flex flex-wrap items-center gap-2">
          <Badge theme="green" label="Confirmed" />
          <span class="text-sm font-medium text-ink-gray-8">{{ detail.order.name }}</span>
          <StatusBadge :status="detail.order.status" />
        </div>
        <div class="mt-2 text-sm text-ink-gray-5">
          Total: <span class="font-medium text-ink-gray-8">{{ formatMoney(detail.order.total) }}</span>
        </div>
      </div>

      <div
        v-for="inv in detail.invoices"
        :key="inv.name"
        class="flex items-center justify-between gap-3 rounded-lg border border-outline-gray-1 bg-surface-white p-4"
      >
        <div class="min-w-0">
          <div class="flex flex-wrap items-center gap-2 text-sm text-ink-gray-8">
            <span class="font-medium">Invoice {{ inv.name }}</span>
            <StatusBadge :status="inv.status" />
          </div>
          <div class="mt-1 text-sm text-ink-gray-5">Due: {{ formatMoney(inv.total_due) }}</div>
        </div>
        <div class="flex shrink-0 gap-2">
          <a :href="pdfUrl(inv.name)" target="_blank" rel="noopener">
            <Button label="PDF" variant="subtle" size="sm" />
          </a>
          <RouterLink v-if="inv.status !== 'Paid'" :to="`/pay/${inv.name}`">
            <Button label="Pay now" variant="solid" size="sm" />
          </RouterLink>
        </div>
      </div>

      <div class="rounded-lg border border-outline-gray-1 bg-surface-gray-1 p-4">
        <h2 class="text-sm font-medium text-ink-gray-8">What happens next</h2>
        <ol class="mt-2 list-decimal space-y-1 pl-5 text-sm text-ink-gray-5">
          <li>Pay any outstanding invoices above.</li>
          <li>Services activate automatically once payment clears.</li>
          <li>Login credentials arrive by email.</li>
        </ol>
      </div>
    </div>
  </div>
</template>
