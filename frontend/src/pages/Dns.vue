<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { useRoute } from 'vue-router'
import { Badge, Button, ErrorMessage, Select, TextInput } from 'frappe-ui'
import { call, friendlyError } from '../api'
import LoadingBlock from '../components/LoadingBlock.vue'
import EmptyState from '../components/EmptyState.vue'
import ErrorState from '../components/ErrorState.vue'

const route = useRoute()
const domain = route.params.domain as string
interface R { name: string; record_type: string; hostname: string; record_value: string; ttl: number }
const list = ref<R[]>([])
const rtype = ref('A')
const host = ref('@')
const value = ref('')
const error = ref('')
const loading = ref(true)
const loadError = ref('')
const adding = ref(false)

async function refresh() {
  loading.value = true
  loadError.value = ''
  try {
    list.value = await call('lube_station.lube_station.portal.apis.dns_list', { domain }, 'GET')
  } catch (e) {
    loadError.value = friendlyError(e)
  } finally {
    loading.value = false
  }
}

async function add() {
  error.value = ''
  adding.value = true
  try {
    await call('lube_station.lube_station.portal.apis.dns_add', { domain, record_type: rtype.value, hostname: host.value, value: value.value })
    value.value = ''
    await refresh()
  } catch (e) {
    error.value = friendlyError(e)
  } finally {
    adding.value = false
  }
}

onMounted(refresh)
</script>

<template>
  <div class="space-y-4">
    <div class="flex flex-wrap items-start justify-between gap-3">
      <div>
        <h1 class="text-xl font-semibold tracking-tight text-ink-gray-8">DNS · {{ domain }}</h1>
        <p class="mt-1 text-sm text-ink-gray-5">Add and review DNS records for this domain.</p>
      </div>
      <Button label="Add record" variant="solid" size="sm" :loading="adding" @click="add" />
    </div>

    <div class="rounded-lg border border-outline-gray-1 bg-surface-white p-4">
      <div class="text-sm font-medium text-ink-gray-8">New record</div>
      <div class="mt-2 grid gap-3 sm:grid-cols-3">
        <Select v-model="rtype" label="Type" :options="['A', 'AAAA', 'CNAME', 'MX', 'TXT', 'NS', 'SRV'].map((t) => ({ label: t, value: t }))" />
        <TextInput v-model="host" label="Host" />
        <TextInput v-model="value" label="Value" />
      </div>
      <ErrorMessage v-if="error" :message="error" class="mt-2" />
    </div>

    <LoadingBlock v-if="loading" :lines="4" />
    <ErrorState v-else-if="loadError" :message="loadError" @retry="refresh" />
    <EmptyState
      v-else-if="!list.length"
      title="No DNS records yet"
      hint="Add your first record with the form above."
    />
    <div v-else class="overflow-hidden rounded-lg border border-outline-gray-1 bg-surface-white">
      <div class="hidden grid-cols-[96px_1fr_1fr_80px] items-center gap-2 border-b border-outline-gray-1 bg-surface-gray-1 px-4 py-2 text-xs font-medium uppercase tracking-wide text-ink-gray-5 sm:grid">
        <span>Type</span>
        <span>Host</span>
        <span>Value</span>
        <span class="text-right">TTL</span>
      </div>
      <div
        v-for="r in list"
        :key="r.name"
        class="grid grid-cols-2 items-center gap-2 border-t border-outline-gray-1 px-4 py-3 text-sm first:border-t-0 sm:grid-cols-[96px_1fr_1fr_80px]"
      >
        <Badge theme="blue" size="md" class="w-fit">{{ r.record_type }}</Badge>
        <span class="truncate font-medium text-ink-gray-8">{{ r.hostname }}</span>
        <span class="truncate text-ink-gray-5">{{ r.record_value }}</span>
        <span class="text-ink-gray-5 sm:text-right">{{ r.ttl }}</span>
      </div>
    </div>
  </div>
</template>
