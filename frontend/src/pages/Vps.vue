<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { Button, ErrorMessage, Select, TextInput } from 'frappe-ui'
import { call, friendlyError } from '../api'
import StatusBadge from '../components/StatusBadge.vue'
import StatusTabs from '../components/StatusTabs.vue'
import LoadingBlock from '../components/LoadingBlock.vue'
import EmptyState from '../components/EmptyState.vue'
import ErrorState from '../components/ErrorState.vue'

interface VpsInst { name: string; status?: string; ipv4?: string; location?: string }
const instances = ref<VpsInst[]>([])
const target = ref('')
const action = ref('reboot')
const out = ref('')
const error = ref('')
const loading = ref(true)
const listError = ref('')
const router = useRouter()
const tab = ref('All')

const ORDER = ['Active', 'Suspended', 'Provisioning', 'Terminated']

const tabs = computed(() => {
  const counts = new Map<string, number>()
  for (const i of instances.value) counts.set(i.status || 'Unknown', (counts.get(i.status || 'Unknown') || 0) + 1)
  const present = ORDER.filter((s) => counts.has(s))
  for (const s of counts.keys()) if (!present.includes(s)) present.push(s)
  return [{ label: 'All', count: instances.value.length }, ...present.map((s) => ({ label: s, count: counts.get(s) || 0 }))]
})

const filtered = computed(() => tab.value === 'All' ? instances.value : instances.value.filter((i) => (i.status || 'Unknown') === tab.value))

const actionOptions = ['reboot', 'start', 'stop', 'snapshot', 'console', 'usage'].map((a) => ({
  label: a,
  value: a,
}))

async function send() {
  error.value = ''
  try {
    const r = await call<Record<string, unknown>>('lube_station.lube_station.portal.apis.vps_control', { instance: target.value, action: action.value })
    out.value = JSON.stringify(r)
  } catch (e) {
    error.value = friendlyError(e)
  }
}

async function loadInstances() {
  loading.value = true
  listError.value = ''
  try {
    instances.value = await call('frappe.client.get_list', { doctype: 'VPS Instance', fields: ['name', 'status', 'ipv4', 'location'] })
    if (!tabs.value.some((t) => t.label === tab.value)) tab.value = 'All'
  } catch (e) {
    instances.value = []
    listError.value = friendlyError(e)
  } finally {
    loading.value = false
  }
}

onMounted(loadInstances)

function pick(name: string) {
  target.value = name
}
</script>

<template>
  <div class="space-y-4">
    <div class="flex items-start justify-between gap-4">
      <div>
        <h1 class="text-xl font-semibold tracking-tight text-ink-gray-8">VPS controls</h1>
        <p class="mt-1 text-sm text-ink-gray-5">Click an instance below to select it, pick an action, then Run.</p>
      </div>
      <Button label="Run (audited)" variant="solid" size="sm" @click="send" />
    </div>
    <div class="space-y-3 rounded-lg border border-outline-gray-1 bg-surface-white px-4 py-4">
      <div class="grid gap-3 sm:grid-cols-2">
        <TextInput v-model="target" label="Instance" placeholder="VPS-0001" />
        <Select v-model="action" label="Action" :options="actionOptions" />
      </div>
      <ErrorMessage v-if="error" :message="error" />
      <p v-if="out" class="break-all rounded-lg bg-surface-gray-1 px-3 py-2 text-xs text-ink-gray-8">{{ out }}</p>
    </div>
    <ErrorState v-if="listError && !loading" :message="listError" @retry="loadInstances" />
    <LoadingBlock v-if="loading" :lines="3" />
    <template v-if="!loading && !listError">
      <StatusTabs v-if="instances.length" v-model="tab" :tabs="tabs" />
      <div v-if="filtered.length" class="space-y-2">
        <button
          v-for="inst in filtered"
          :key="inst.name"
          class="flex w-full flex-wrap items-center gap-x-4 gap-y-2 rounded-lg border px-4 py-3 text-left sm:flex-nowrap"
          :class="target === inst.name
            ? 'border-ink-gray-8 bg-surface-gray-1'
            : 'border-outline-gray-1 bg-surface-white hover:bg-surface-gray-1'"
          @click="pick(inst.name)"
        >
          <div class="min-w-0 flex-1">
            <div class="truncate text-sm font-medium text-ink-gray-8">{{ inst.name }}</div>
            <div class="mt-0.5 truncate text-sm text-ink-gray-5">
              {{ [inst.ipv4, inst.location].filter(Boolean).join(' · ') || 'VPS instance' }}
            </div>
          </div>
          <div class="w-28 shrink-0"><StatusBadge :status="inst.status || 'Unknown'" /></div>
          <div class="shrink-0 text-xs text-ink-gray-5">{{ target === inst.name ? 'Selected ✓' : 'Click to select' }}</div>
        </button>
      </div>
      <EmptyState
        v-else
        title="No VPS instances"
        hint="Order a VPS from the storefront to manage it here."
        action-label="Browse store"
        @action="router.push('/store')"
      />
    </template>
  </div>
</template>
