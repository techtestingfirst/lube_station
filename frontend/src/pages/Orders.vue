<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { RouterLink, useRouter } from 'vue-router'
import { Button, TabList, TabPanel, TabTrigger, Tabs } from 'frappe-ui'
import { call, friendlyError } from '../api'
import { formatDate, formatMoney } from '../format'
import StatusBadge from '../components/StatusBadge.vue'
import LoadingBlock from '../components/LoadingBlock.vue'
import EmptyState from '../components/EmptyState.vue'
import ErrorState from '../components/ErrorState.vue'

interface Ord { name: string; status: string; total: number; creation: string }
const STATUSES = ['Pending Review', 'Accepted', 'Fraud', 'Cancelled']
const list = ref<Ord[]>([])
const loading = ref(true)
const error = ref('')
const router = useRouter()
const active = ref('Pending Review')

const groups = computed(() => {
  const map = new Map<string, Ord[]>(STATUSES.map((s) => [s, []]))
  for (const o of list.value) {
    if (!map.has(o.status)) map.set(o.status, [])
    map.get(o.status)!.push(o)
  }
  return [...map.entries()]
})

watch(list, (orders) => {
  if (!orders.length) return
  if (!groups.value.some(([s, items]) => s === active.value && items.length)) {
    active.value = groups.value.find(([, items]) => items.length)?.[0] || 'Pending Review'
  }
})

async function load() {
  loading.value = true
  error.value = ''
  try {
    list.value = await call('lube_station.lube_station.portal.apis.my_orders', {}, 'GET')
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
    <div class="flex items-start justify-between gap-4">
      <div>
        <h1 class="text-xl font-semibold tracking-tight text-ink-gray-8">Orders</h1>
        <p class="mt-1 text-sm text-ink-gray-5">Order history with status and totals.</p>
      </div>
      <RouterLink to="/store"><Button label="Order service" variant="solid" size="sm" /></RouterLink>
    </div>
    <ErrorState v-if="error && !loading" :message="error" @retry="load" />
    <LoadingBlock v-if="loading" :lines="4" />
    <template v-if="!loading && !error">
      <Tabs v-if="list.length" v-model="active">
        <TabList>
          <TabTrigger v-for="[status, items] in groups" :key="status" :value="status" :label="`${status} (${items.length})`" />
        </TabList>
        <TabPanel v-for="[status, items] in groups" :key="status" :value="status">
          <div v-if="items.length" class="space-y-2 pt-4">
            <div
              v-for="o in items"
              :key="o.name"
              class="flex flex-wrap items-center gap-x-4 gap-y-2 rounded-lg border border-outline-gray-1 bg-surface-white px-4 py-3 sm:flex-nowrap"
            >
              <div class="min-w-0 flex-1">
                <RouterLink :to="`/order/${o.name}`" class="truncate text-sm font-medium text-ink-gray-8 hover:underline">{{ o.name }}</RouterLink>
                <div class="mt-0.5 text-sm text-ink-gray-5">Placed {{ formatDate(o.creation) }}</div>
              </div>
              <div class="w-36 shrink-0"><StatusBadge :status="o.status" /></div>
              <div class="w-36 shrink-0 sm:text-right">
                <div class="text-sm font-medium text-ink-gray-8">{{ formatMoney(o.total) }}</div>
              </div>
              <div class="flex shrink-0 gap-2">
                <RouterLink :to="`/order/${o.name}`"><Button label="View" size="sm" /></RouterLink>
              </div>
            </div>
          </div>
          <EmptyState
            v-else
            :title="`No ${status.toLowerCase()} orders`"
            hint="Orders with this status will appear here."
            action-label="Browse store"
            @action="router.push('/store')"
          />
        </TabPanel>
      </Tabs>
      <EmptyState
        v-else
        title="No orders yet"
        hint="Orders you place will appear here."
        action-label="Browse store"
        @action="router.push('/store')"
      />
    </template>
  </div>
</template>
