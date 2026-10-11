<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { RouterLink, useRouter } from 'vue-router'
import { Button } from 'frappe-ui'
import { call, friendlyError } from '../api'
import { formatDate } from '../format'
import StatusBadge from '../components/StatusBadge.vue'
import StatusTabs from '../components/StatusTabs.vue'
import LoadingBlock from '../components/LoadingBlock.vue'
import EmptyState from '../components/EmptyState.vue'
import ErrorState from '../components/ErrorState.vue'

interface Svc {
  name: string
  hosting_plan: string
  plan_name: string
  product_group: string
  product_type: string
  status: string
  next_due_date: string
}
const list = ref<Svc[]>([])
const loading = ref(true)
const error = ref('')
const router = useRouter()
const groupTab = ref('All')
const statusTab = ref('All')

const STATUS_ORDER = ['Active', 'Pending', 'Suspended', 'Terminated', 'Cancelled']

function withCounts(items: { status?: string; product_group?: string }[], key: 'status' | 'product_group', order: string[]) {
  const counts = new Map<string, number>()
  for (const s of items) {
    const k = (key === 'status' ? s.status : s.product_group) || 'Other'
    counts.set(k, (counts.get(k) || 0) + 1)
  }
  const present = order.filter((s) => counts.has(s))
  for (const s of counts.keys()) if (!present.includes(s)) present.push(s)
  return present.map((s) => ({ label: s, count: counts.get(s) || 0 }))
}

const groupTabs = computed(() => {
  const counts = new Map<string, number>()
  for (const s of list.value) {
    const g = s.product_group || 'Other'
    counts.set(g, (counts.get(g) || 0) + 1)
  }
  const present = [...counts.entries()].sort((a, b) => b[1] - a[1]).map(([g]) => g)
  return [{ label: 'All', count: list.value.length }, ...present.map((g) => ({ label: g, count: counts.get(g) || 0 }))]
})

const inGroup = computed(() => groupTab.value === 'All'
  ? list.value
  : list.value.filter((s) => (s.product_group || 'Other') === groupTab.value))

const statusTabs = computed(() => [
  { label: 'All', count: inGroup.value.length },
  ...withCounts(inGroup.value, 'status', STATUS_ORDER),
])

const filtered = computed(() => statusTab.value === 'All'
  ? inGroup.value
  : inGroup.value.filter((s) => s.status === statusTab.value))

function resetTabs() {
  if (!groupTabs.value.some((t) => t.label === groupTab.value)) groupTab.value = 'All'
  if (!statusTabs.value.some((t) => t.label === statusTab.value)) statusTab.value = 'All'
}

async function load() {
  loading.value = true
  error.value = ''
  try {
    list.value = await call('lube_station.lube_station.portal.apis.my_services', {}, 'GET')
    resetTabs()
  } catch (e) {
    error.value = friendlyError(e)
  } finally {
    loading.value = false
  }
}

function pickGroup(g: string) {
  groupTab.value = g
  statusTab.value = 'All'
}

onMounted(load)
</script>

<template>
  <div class="space-y-4">
    <div class="flex items-start justify-between gap-4">
      <div>
        <h1 class="text-xl font-semibold tracking-tight text-ink-gray-8">Services</h1>
        <p class="mt-1 text-sm text-ink-gray-5">Hosting services on your account, grouped by type.</p>
      </div>
      <RouterLink to="/store"><Button label="Order service" variant="solid" size="sm" /></RouterLink>
    </div>
    <ErrorState v-if="error && !loading" :message="error" @retry="load" />
    <LoadingBlock v-if="loading" :lines="4" />
    <template v-if="!loading && !error">
      <StatusTabs v-if="list.length" :model-value="groupTab" :tabs="groupTabs" @update:model-value="pickGroup" />
      <StatusTabs v-if="list.length && statusTabs.length > 1" v-model="statusTab" :tabs="statusTabs" />
      <div v-if="filtered.length" class="space-y-2">
        <div
          v-for="s in filtered"
          :key="s.name"
          class="flex flex-wrap items-center gap-x-4 gap-y-2 rounded-lg border border-outline-gray-1 bg-surface-white px-4 py-3 sm:flex-nowrap"
        >
          <div class="min-w-0 flex-1">
            <RouterLink :to="`/service/${s.name}`" class="truncate text-sm font-medium text-ink-gray-8 hover:underline">{{ s.name }}</RouterLink>
            <div class="mt-0.5 truncate text-sm text-ink-gray-5">{{ s.plan_name }}{{ s.product_type ? ` · ${s.product_type}` : '' }}</div>
          </div>
          <div class="w-28 shrink-0"><StatusBadge :status="s.status" /></div>
          <div class="w-36 shrink-0 sm:text-right">
            <div class="text-xs text-ink-gray-5">Next due</div>
            <div class="text-sm text-ink-gray-8">{{ formatDate(s.next_due_date) }}</div>
          </div>
          <div class="flex shrink-0 gap-2">
            <RouterLink :to="`/service/${s.name}`"><Button label="View" size="sm" /></RouterLink>
          </div>
        </div>
      </div>
      <EmptyState
        v-else
        title="No services yet"
        hint="Order a hosting plan from the storefront to get started."
        action-label="Browse store"
        @action="router.push('/store')"
      />
    </template>
  </div>
</template>
