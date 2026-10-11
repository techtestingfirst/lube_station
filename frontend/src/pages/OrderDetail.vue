<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { RouterLink, useRoute, useRouter } from 'vue-router'
import { Button } from 'frappe-ui'
import { call, friendlyError } from '../api'
import { formatDate, formatMoney } from '../format'
import EmptyState from '../components/EmptyState.vue'
import ErrorState from '../components/ErrorState.vue'
import LoadingBlock from '../components/LoadingBlock.vue'
import StatusBadge from '../components/StatusBadge.vue'

interface OrderItem {
  item_type: string
  reference: string
  billing_cycle: string
  unit_price: number
  quantity: number
  plan_name: string
  domain: string
}
interface Inv { name: string; status: string; total_due: number }
interface Detail {
  order: { name: string; status: string; total: number; creation: string; coupon_code: string; customer_notes: string; items: OrderItem[] }
  invoices: Inv[]
}

const route = useRoute()
const router = useRouter()
const name = route.params.order as string
const detail = ref<Detail | null>(null)
const loading = ref(true)
const error = ref('')

const unpaid = computed(() => (detail.value?.invoices || []).some((i) => i.status !== 'Paid'))

async function load() {
  loading.value = true
  error.value = ''
  try {
    detail.value = await call('lube_station.lube_station.portal.apis.my_order_detail', { order: name }, 'GET')
  } catch (e) {
    error.value = friendlyError(e)
  } finally {
    loading.value = false
  }
}

function itemTitle(item: OrderItem): string {
  if (item.plan_name) return item.plan_name
  if (item.item_type === 'Domain') return item.domain || item.reference
  return `${item.item_type}: ${item.reference}`
}

onMounted(load)

function pdfUrl(invName: string): string {
  const q = new URLSearchParams({ doctype: 'Hosting Invoice', name: invName, format: 'Hosting Invoice' })
  return `/api/method/frappe.utils.print_format.download_pdf?${q.toString()}`
}
</script>

<template>
  <div class="space-y-4">
    <RouterLink to="/orders" class="text-sm text-ink-gray-5 hover:text-ink-gray-8">← All orders</RouterLink>
    <ErrorState v-if="error && !loading" :message="error" @retry="load" />
    <LoadingBlock v-if="loading" :lines="4" />
    <EmptyState
      v-else-if="!detail"
      title="Order not found"
      hint="We could not load this order. It may belong to a different account."
      action-label="All orders"
      @action="router.push('/orders')"
    />
    <template v-else>
      <div class="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h1 class="text-xl font-semibold tracking-tight text-ink-gray-8">{{ detail.order.name }}</h1>
          <p class="mt-1 text-sm text-ink-gray-5">
            Placed {{ formatDate(detail.order.creation) }} · Total {{ formatMoney(detail.order.total) }}
            <span v-if="detail.order.coupon_code"> · Coupon {{ detail.order.coupon_code }}</span>
          </p>
          <p v-if="detail.order.customer_notes" class="mt-1 text-sm text-ink-gray-5">Note: {{ detail.order.customer_notes }}</p>
        </div>
        <StatusBadge :status="detail.order.status" />
      </div>

      <div class="overflow-hidden rounded-lg border border-outline-gray-1 bg-surface-white">
        <div class="border-b border-outline-gray-1 bg-surface-gray-1 px-4 py-2 text-xs font-medium uppercase tracking-wide text-ink-gray-5">
          What you ordered
        </div>
        <div v-for="(item, idx) in detail.order.items" :key="idx" class="flex items-center justify-between gap-4 border-b border-outline-gray-1 px-4 py-3 last:border-0">
          <div class="min-w-0">
            <div class="text-sm font-medium text-ink-gray-8">{{ itemTitle(item) }}</div>
            <div v-if="item.domain && item.plan_name" class="mt-0.5 text-sm text-ink-gray-5">{{ item.domain }}</div>
            <div v-if="item.billing_cycle" class="mt-0.5 text-xs text-ink-gray-5">{{ item.billing_cycle }} · Qty {{ item.quantity || 1 }}</div>
          </div>
          <div class="shrink-0 text-sm font-medium text-ink-gray-8">{{ formatMoney((item.unit_price || 0) * (item.quantity || 1)) }}</div>
        </div>
        <div v-if="!detail.order.items?.length" class="px-4 py-3 text-sm text-ink-gray-5">No items on this order.</div>
      </div>

      <div v-if="detail.invoices.length" class="space-y-2">
        <div
          v-for="inv in detail.invoices"
          :key="inv.name"
          class="flex items-center justify-between gap-3 rounded-lg border border-outline-gray-1 bg-surface-white p-4"
        >
          <div class="min-w-0">
            <div class="flex flex-wrap items-center gap-2 text-sm text-ink-gray-8">
              <RouterLink :to="`/invoice/${inv.name}`" class="font-medium hover:underline">Invoice {{ inv.name }}</RouterLink>
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
      </div>

      <div v-if="unpaid" class="rounded-lg border border-outline-gray-1 bg-surface-gray-1 p-4">
        <h2 class="text-sm font-medium text-ink-gray-8">What happens next</h2>
        <ol class="mt-2 list-decimal space-y-1 pl-5 text-sm text-ink-gray-5">
          <li>Pay any outstanding invoices above.</li>
          <li>Services activate automatically once payment clears.</li>
          <li>Login credentials arrive by email.</li>
        </ol>
      </div>
    </template>
  </div>
</template>
