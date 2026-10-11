<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { RouterLink } from 'vue-router'
import { call, friendlyError } from '../api'
import EmptyState from '../components/EmptyState.vue'
import LoadingBlock from '../components/LoadingBlock.vue'
import ErrorState from '../components/ErrorState.vue'

interface Txn {
  date: string
  kind: 'credit' | 'debit'
  amount: number
  description: string
  ref: string
  ref_type: string
}

const API = 'lube_station.lube_station.wallet.wallet'
const balance = ref<number | null>(null)
const txns = ref<Txn[]>([])
const loading = ref(true)
const error = ref('')

function fmt(n: number): string {
  const sign = n > 0 ? '+' : n < 0 ? '−' : ''
  return `${sign}${Math.abs(n).toFixed(2)}`
}

function invoiceLink(t: Txn): string | null {
  return t.ref_type === 'Hosting Invoice' ? `/invoice/${t.ref}` : null
}

async function load() {
  loading.value = true
  error.value = ''
  try {
    const [w, rows] = await Promise.all([
      call<{ balance: number }>(`${API}.my_wallet`, {}, 'GET'),
      call<Txn[]>(`${API}.my_wallet_transactions`, {}, 'GET'),
    ])
    balance.value = w.balance
    txns.value = rows
  } catch (e) {
    error.value = friendlyError(e)
  } finally {
    loading.value = false
  }
}

onMounted(load)
</script>

<template>
  <div class="space-y-4">
    <div>
      <h1 class="text-xl font-semibold tracking-tight text-ink-gray-8">Wallet</h1>
      <p class="mt-1 text-sm text-ink-gray-5">Credit balance and every wallet movement.</p>
    </div>

    <ErrorState v-if="error && !loading" :message="error" @retry="load" />
    <LoadingBlock v-if="loading" :lines="4" />
    <template v-if="!loading && !error">
      <div class="rounded-lg border border-outline-gray-1 bg-surface-white p-4">
        <div class="text-sm text-ink-gray-5">Available credit</div>
        <div class="mt-1 text-2xl font-semibold tracking-tight">
          {{ balance !== null ? balance.toFixed(2) : '—' }}
        </div>
        <div class="mt-1 text-xs text-ink-gray-5">
          Auto-applied to your next invoices. Refunds and downgrade credits land here.
        </div>
      </div>

      <div class="rounded-lg border border-outline-gray-1 bg-surface-white p-4">
        <div class="text-sm font-medium text-ink-gray-8">Transactions</div>
        <div v-if="txns.length" class="mt-2 divide-y divide-outline-gray-1">
          <div v-for="t in txns" :key="`${t.ref_type}-${t.ref}`" class="flex items-center justify-between gap-3 px-1 py-2">
            <div class="min-w-0">
              <div class="truncate text-sm font-medium text-ink-gray-8">{{ t.description }}</div>
              <div class="mt-0.5 text-xs text-ink-gray-5">
                {{ new Date(t.date).toLocaleDateString() }} ·
                <RouterLink v-if="invoiceLink(t)" :to="invoiceLink(t)!" class="hover:underline">{{ t.ref }}</RouterLink>
                <span v-else>{{ t.ref }}</span>
              </div>
            </div>
            <div
              class="shrink-0 text-sm font-medium"
              :class="t.kind === 'credit' ? 'text-green-700' : 'text-ink-gray-8'"
            >
              {{ fmt(t.amount) }}
            </div>
          </div>
        </div>
        <EmptyState
          v-else
          title="No wallet activity yet"
          hint="Refunds and credits will appear here."
        />
      </div>
    </template>
  </div>
</template>
