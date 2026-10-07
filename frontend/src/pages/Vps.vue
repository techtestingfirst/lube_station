<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { Button, ErrorMessage, Select, TextInput } from 'frappe-ui'
import { call, friendlyError } from '../api'
import LoadingBlock from '../components/LoadingBlock.vue'
import EmptyState from '../components/EmptyState.vue'
import ErrorState from '../components/ErrorState.vue'

const instances = ref<{ name: string }[]>([])
const target = ref('')
const action = ref('reboot')
const out = ref('')
const error = ref('')
const loading = ref(true)
const listError = ref('')
const router = useRouter()

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
    instances.value = await call('frappe.client.get_list', { doctype: 'VPS Instance', fields: ['name'] })
  } catch (e) {
    instances.value = []
    listError.value = friendlyError(e)
  } finally {
    loading.value = false
  }
}

onMounted(loadInstances)
</script>

<template>
  <div class="space-y-4">
    <div class="flex items-start justify-between gap-4">
      <div>
        <h1 class="text-xl font-semibold tracking-tight text-ink-gray-8">VPS controls</h1>
        <p class="mt-1 text-sm text-ink-gray-5">Audited power operations for your instances.</p>
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
      <div v-if="instances.length" class="space-y-2">
        <div
          v-for="inst in instances"
          :key="inst.name"
          class="flex flex-wrap items-center gap-x-4 gap-y-2 rounded-lg border border-outline-gray-1 bg-surface-white px-4 py-3 sm:flex-nowrap"
        >
          <div class="min-w-0 flex-1">
            <div class="truncate text-sm font-medium text-ink-gray-8">{{ inst.name }}</div>
            <div class="mt-0.5 truncate text-sm text-ink-gray-5">VPS instance</div>
          </div>
          <div class="shrink-0">
            <Button label="Use" size="sm" @click="target = inst.name" />
          </div>
        </div>
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
