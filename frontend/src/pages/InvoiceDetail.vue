<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { RouterLink, useRoute } from 'vue-router'
import { Button } from 'frappe-ui'
import { call, friendlyError } from '../api'
import { formatDate, formatMoney } from '../format'
import StatusBadge from '../components/StatusBadge.vue'
import LoadingBlock from '../components/LoadingBlock.vue'
import ErrorState from '../components/ErrorState.vue'

interface Item { description: string; service_ref: string; amount: number; plan_name: string; domain: string }
interface Invoice {
  name: string
  status: string
  due_date: string
  order_ref: string
  gateway: string
  invoice_items: Item[]
  subtotal_amount: number
  tax_amount: number
  tax_label: string
  cgst_amount: number
  sgst_amount: number
  ugst_amount: number
  igst_amount: number
  credit_applied: number
  total_due: number
}

interface Customer {
  name: string
  email: string
  company: string
  phone: string
  tax_id: string
  address: string
}

const route = useRoute()
const name = route.params.invoice as string
const inv = ref<Invoice | null>(null)
const customer = ref<Customer | null>(null)
const loading = ref(true)
const error = ref('')

async function load() {
  loading.value = true
  error.value = ''
  try {
    const out = await call<{ invoice: Invoice; customer: Customer }>('lube_station.lube_station.portal.apis.my_invoice_detail', { invoice: name }, 'GET')
    inv.value = out.invoice
    customer.value = out.customer
  } catch (e) {
    error.value = friendlyError(e)
  } finally {
    loading.value = false
  }
}

function pdfUrl(invName: string): string {
  const q = new URLSearchParams({ doctype: 'Hosting Invoice', name: invName, format: 'Hosting Invoice' })
  return `/api/method/frappe.utils.print_format.download_pdf?${q.toString()}`
}

onMounted(load)
</script>

<template>
  <div class="space-y-4">
    <RouterLink to="/invoices" class="text-sm text-ink-gray-5 hover:text-ink-gray-8">← All invoices</RouterLink>
    <ErrorState v-if="error && !loading" :message="error" @retry="load" />
    <LoadingBlock v-if="loading" :lines="5" />
    <template v-if="!loading && !error && inv">
      <div class="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h1 class="text-xl font-semibold tracking-tight text-ink-gray-8">{{ inv.name }}</h1>
          <p class="mt-1 text-sm text-ink-gray-5">
            Due {{ formatDate(inv.due_date) }}
            <span v-if="inv.order_ref"> · Order <RouterLink :to="`/order/${inv.order_ref}`" class="underline">{{ inv.order_ref }}</RouterLink></span>
          </p>
        </div>
        <div class="flex items-center gap-2">
          <StatusBadge :status="inv.status" />
          <a :href="pdfUrl(inv.name)" target="_blank" rel="noopener"><Button label="PDF" size="sm" /></a>
          <RouterLink v-if="inv.status !== 'Paid'" :to="`/pay/${inv.name}`"><Button label="Pay now" variant="solid" size="sm" /></RouterLink>
        </div>
      </div>

      <div v-if="customer" class="rounded-lg border border-outline-gray-1 bg-surface-white px-4 py-3">
        <div class="mb-1 text-xs font-medium uppercase tracking-wide text-ink-gray-5">Billed to — verify before paying</div>
        <div class="text-sm font-medium text-ink-gray-8">{{ customer.name }}</div>
        <div v-if="customer.company" class="text-sm text-ink-gray-5">{{ customer.company }}</div>
        <div v-if="customer.address" class="mt-1 whitespace-pre-line text-sm text-ink-gray-5">{{ customer.address }}</div>
        <div class="mt-1 flex flex-wrap gap-x-4 gap-y-0.5 text-sm text-ink-gray-5">
          <span v-if="customer.email">{{ customer.email }}</span>
          <span v-if="customer.phone">{{ customer.phone }}</span>
          <span v-if="customer.tax_id">Tax / VAT: {{ customer.tax_id }}</span>
        </div>
      </div>

      <div class="overflow-hidden rounded-lg border border-outline-gray-1 bg-surface-white">
        <div class="border-b border-outline-gray-1 bg-surface-gray-1 px-4 py-2 text-xs font-medium uppercase tracking-wide text-ink-gray-5">
          What you are paying for
        </div>
        <div v-for="item in inv.invoice_items" :key="item.description + item.amount" class="flex items-center justify-between gap-4 border-b border-outline-gray-1 px-4 py-3 last:border-0">
          <div class="min-w-0">
            <div class="text-sm font-medium text-ink-gray-8">{{ item.plan_name || item.description }}</div>
            <div v-if="item.domain" class="mt-0.5 text-sm text-ink-gray-5">{{ item.domain }}</div>
            <div v-if="item.plan_name && item.description !== item.plan_name" class="mt-0.5 text-xs text-ink-gray-5">{{ item.description }}</div>
          </div>
          <div class="shrink-0 text-sm font-medium text-ink-gray-8">{{ formatMoney(item.amount) }}</div>
        </div>
        <div v-if="!inv.invoice_items?.length" class="px-4 py-3 text-sm text-ink-gray-5">No line items on this invoice.</div>
      </div>

      <div class="space-y-1.5 rounded-lg border border-outline-gray-1 bg-surface-white px-4 py-3 text-sm">
        <div class="flex justify-between text-ink-gray-5"><span>Subtotal</span><span class="text-ink-gray-8">{{ formatMoney(inv.subtotal_amount) }}</span></div>
        <div v-if="inv.tax_amount" class="flex justify-between text-ink-gray-5">
          <span>Tax{{ inv.tax_label ? ` (${inv.tax_label})` : '' }}</span><span class="text-ink-gray-8">{{ formatMoney(inv.tax_amount) }}</span>
        </div>
        <div v-if="inv.cgst_amount" class="flex justify-between text-ink-gray-5"><span>CGST</span><span class="text-ink-gray-8">{{ formatMoney(inv.cgst_amount) }}</span></div>
        <div v-if="inv.sgst_amount" class="flex justify-between text-ink-gray-5"><span>SGST</span><span class="text-ink-gray-8">{{ formatMoney(inv.sgst_amount) }}</span></div>
        <div v-if="inv.ugst_amount" class="flex justify-between text-ink-gray-5"><span>UGST</span><span class="text-ink-gray-8">{{ formatMoney(inv.ugst_amount) }}</span></div>
        <div v-if="inv.igst_amount" class="flex justify-between text-ink-gray-5"><span>IGST</span><span class="text-ink-gray-8">{{ formatMoney(inv.igst_amount) }}</span></div>
        <div v-if="inv.credit_applied" class="flex justify-between text-ink-gray-5"><span>Credit applied</span><span class="text-ink-gray-8">−{{ formatMoney(inv.credit_applied) }}</span></div>
        <div class="flex justify-between border-t border-outline-gray-1 pt-2 font-medium text-ink-gray-8"><span>Total due</span><span>{{ formatMoney(inv.total_due) }}</span></div>
      </div>
    </template>
  </div>
</template>
