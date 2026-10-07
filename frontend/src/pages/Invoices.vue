<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { RouterLink, useRouter } from 'vue-router'
import { Button } from 'frappe-ui'
import { call, friendlyError } from '../api'
import { formatDate, formatMoney } from '../format'
import StatusBadge from '../components/StatusBadge.vue'
import LoadingBlock from '../components/LoadingBlock.vue'
import EmptyState from '../components/EmptyState.vue'
import ErrorState from '../components/ErrorState.vue'

interface Inv { name: string; total_due: number; status: string; due_date: string }
const list = ref<Inv[]>([])
const loading = ref(true)
const error = ref('')
const router = useRouter()

async function load() {
  loading.value = true
  error.value = ''
  try {
    list.value = await call('lube_station.lube_station.portal.apis.my_invoices', {}, 'GET')
  } catch (e) {
    error.value = friendlyError(e)
  } finally {
    loading.value = false
  }
}

function pdfUrl(name: string): string {
  const q = new URLSearchParams({ doctype: 'Hosting Invoice', name, format: 'Hosting Invoice' })
  return `/api/method/frappe.utils.print_format.download_pdf?${q.toString()}`
}

onMounted(load)
</script>

<template>
  <div class="space-y-4">
    <div class="flex items-start justify-between gap-4">
      <div>
        <h1 class="text-xl font-semibold tracking-tight text-ink-gray-8">Invoices</h1>
        <p class="mt-1 text-sm text-ink-gray-5">Billing history and outstanding balances.</p>
      </div>
      <RouterLink to="/store"><Button label="Order service" variant="solid" size="sm" /></RouterLink>
    </div>
    <ErrorState v-if="error && !loading" :message="error" @retry="load" />
    <LoadingBlock v-if="loading" :lines="4" />
    <template v-if="!loading && !error">
      <div v-if="list.length" class="space-y-2">
        <div
          v-for="i in list"
          :key="i.name"
          class="flex flex-wrap items-center gap-x-4 gap-y-2 rounded-lg border border-outline-gray-1 bg-surface-white px-4 py-3 sm:flex-nowrap"
        >
          <div class="min-w-0 flex-1">
            <div class="truncate text-sm font-medium text-ink-gray-8">{{ i.name }}</div>
            <div class="mt-0.5 text-sm text-ink-gray-5">Due {{ formatDate(i.due_date) }}</div>
          </div>
          <div class="w-28 shrink-0"><StatusBadge :status="i.status" /></div>
          <div class="w-36 shrink-0 sm:text-right">
            <div class="text-sm font-medium text-ink-gray-8">{{ formatMoney(i.total_due) }}</div>
          </div>
          <div class="flex shrink-0 gap-2">
            <a :href="pdfUrl(i.name)" target="_blank" rel="noopener"><Button label="PDF" size="sm" /></a>
            <RouterLink v-if="i.status !== 'Paid'" :to="`/pay/${i.name}`"><Button label="Pay" variant="solid" size="sm" /></RouterLink>
          </div>
        </div>
      </div>
      <EmptyState
        v-else
        title="No invoices yet"
        hint="Invoices for your services will appear here."
        action-label="Browse store"
        @action="router.push('/store')"
      />
    </template>
  </div>
</template>
