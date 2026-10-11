<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { RouterLink, useRouter } from 'vue-router'
import { Button } from 'frappe-ui'
import { call, friendlyError } from '../api'
import StatusBadge from '../components/StatusBadge.vue'
import StatusTabs from '../components/StatusTabs.vue'
import LoadingBlock from '../components/LoadingBlock.vue'
import EmptyState from '../components/EmptyState.vue'
import ErrorState from '../components/ErrorState.vue'

interface D { name: string; asset_id: string; location: string; status: string; assigned_service: string }
const list = ref<D[]>([])
const loading = ref(true)
const error = ref('')
const router = useRouter()
const tab = ref('All')

const ORDER = ['Assigned', 'Reserved', 'Wipe Pending', 'Available', 'Terminated']

const tabs = computed(() => {
  const counts = new Map<string, number>()
  for (const d of list.value) counts.set(d.status, (counts.get(d.status) || 0) + 1)
  const present = ORDER.filter((s) => counts.has(s))
  for (const s of counts.keys()) if (!present.includes(s)) present.push(s)
  return [{ label: 'All', count: list.value.length }, ...present.map((s) => ({ label: s, count: counts.get(s) || 0 }))]
})

const filtered = computed(() => tab.value === 'All' ? list.value : list.value.filter((d) => d.status === tab.value))

async function load() {
  loading.value = true
  error.value = ''
  try {
    list.value = await call('lube_station.lube_station.portal.apis.my_dedicated', {}, 'GET')
    if (!tabs.value.some((t) => t.label === tab.value)) tab.value = 'All'
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
        <h1 class="text-xl font-semibold tracking-tight text-ink-gray-8">Dedicated servers</h1>
        <p class="mt-1 text-sm text-ink-gray-5">Bare-metal machines assigned to you.</p>
      </div>
      <RouterLink to="/store"><Button label="Order server" variant="solid" size="sm" /></RouterLink>
    </div>
    <p class="rounded-lg border border-outline-gray-1 bg-surface-gray-1 px-4 py-2 text-xs text-ink-gray-5">
      Credentials via portal vault. Wipe verified before release.
    </p>
    <ErrorState v-if="error && !loading" :message="error" @retry="load" />
    <LoadingBlock v-if="loading" :lines="3" />
    <template v-if="!loading && !error">
      <StatusTabs v-if="list.length" v-model="tab" :tabs="tabs" />
      <div v-if="filtered.length" class="space-y-2">
        <div
          v-for="d in filtered"
          :key="d.name"
          class="flex flex-wrap items-center gap-x-4 gap-y-2 rounded-lg border border-outline-gray-1 bg-surface-white px-4 py-3 sm:flex-nowrap"
        >
          <div class="min-w-0 flex-1">
            <div class="truncate text-sm font-medium text-ink-gray-8">{{ d.asset_id || d.name }}</div>
            <div class="mt-0.5 truncate text-sm text-ink-gray-5">{{ d.location }}</div>
          </div>
          <div class="w-28 shrink-0"><StatusBadge :status="d.status" /></div>
          <div class="w-40 shrink-0 sm:text-right">
            <div class="text-xs text-ink-gray-5">Service</div>
            <div class="truncate text-sm text-ink-gray-8">{{ d.assigned_service }}</div>
          </div>
        </div>
      </div>
      <EmptyState
        v-else
        title="No dedicated servers assigned"
        hint="Order a dedicated server from the storefront to see it here."
        action-label="Browse store"
        @action="router.push('/store')"
      />
    </template>
  </div>
</template>
