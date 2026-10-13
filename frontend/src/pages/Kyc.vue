<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { Button, ErrorMessage, Select } from 'frappe-ui'
import { call, friendlyError } from '../api'
import LoadingBlock from '../components/LoadingBlock.vue'
import ErrorState from '../components/ErrorState.vue'
import StatusBadge from '../components/StatusBadge.vue'

interface KycRequest { name: string; status: string; provider: string; ovd_type?: string | null; verified_on?: string | null; creation: string }
interface Kyc {
  status: string
  verified: boolean
  provider?: string | null
  ovd_type?: string | null
  verified_on?: string | null
  providers: string[]
  ovd_types: string[]
  requests: KycRequest[]
}

const kyc = ref<Kyc | null>(null)
const loading = ref(true)
const listError = ref('')
const provider = ref('Manual')
const ovd = ref('')
const busy = ref(false)
const error = ref('')
const done = ref('')

function providerOptions(list: string[]) {
  return list.map((p) => ({ label: p, value: p }))
}

function ovdOptions(list: string[]) {
  return [{ label: 'Select ID type…', value: '' }, ...list.map((o) => ({ label: o, value: o }))]
}

async function load() {
  loading.value = true
  listError.value = ''
  try {
    kyc.value = await call('lube_station.lube_station.portal.apis.my_kyc_status', {}, 'GET')
    if (kyc.value && !providerOptions(kyc.value.providers).some((o) => o.value === provider.value)) {
      provider.value = kyc.value.providers[0] || 'Manual'
    }
  } catch (e) {
    listError.value = friendlyError(e)
  } finally {
    loading.value = false
  }
}

async function submit() {
  error.value = ''
  done.value = ''
  if (!ovd.value) {
    error.value = 'Select the ID type you will verify with.'
    return
  }
  busy.value = true
  try {
    const out = await call<Kyc & { name?: string }>('lube_station.lube_station.portal.apis.request_my_kyc', { provider: provider.value, ovd_type: ovd.value }, 'POST')
    if (out && typeof out === 'object' && 'kyc' in out) kyc.value = (out as unknown as { kyc: Kyc }).kyc
    else await load()
    done.value = 'Verification request recorded. Services activate automatically once staff verifies it.'
  } catch (e) {
    error.value = friendlyError(e)
  } finally {
    busy.value = false
  }
}

onMounted(load)
</script>

<template>
  <div class="space-y-4">
    <div>
      <h1 class="text-xl font-semibold tracking-tight text-ink-gray-8">Identity verification</h1>
      <p class="mt-1 text-sm text-ink-gray-5">Paid services stay Pending until verification completes, then activate automatically.</p>
    </div>
    <ErrorState v-if="listError && !loading" :message="listError" @retry="load" />
    <LoadingBlock v-if="loading" :lines="3" />
    <template v-if="kyc && !loading">
      <div class="flex flex-wrap items-center gap-2 rounded-lg border border-outline-gray-1 bg-surface-white px-4 py-3">
        <span class="text-sm font-medium text-ink-gray-8">Status</span>
        <StatusBadge :status="kyc.status" />
        <span v-if="kyc.verified" class="text-sm text-ink-gray-5">Verified{{ kyc.verified_on ? ` on ${kyc.verified_on}` : '' }} — no action needed.</span>
        <span v-else class="text-sm text-ink-gray-5">Start or restart verification below. Staff reviews Manual requests; mock providers verify instantly in test flows.</span>
      </div>
      <div v-if="!kyc.verified" class="space-y-3 rounded-lg border border-outline-gray-1 bg-surface-white px-4 py-4">
        <div class="grid gap-3 sm:grid-cols-2">
          <Select v-model="provider" label="Provider" :options="providerOptions(kyc.providers)" />
          <Select v-model="ovd" label="ID type" :options="ovdOptions(kyc.ovd_types)" />
        </div>
        <ErrorMessage v-if="error" :message="error" />
        <p v-if="done" class="text-xs text-ink-gray-6">{{ done }}</p>
        <Button label="Request verification" variant="solid" size="sm" :loading="busy" @click="submit" />
      </div>
      <div v-if="kyc.requests.length" class="space-y-2">
        <h2 class="text-sm font-medium text-ink-gray-8">Requests</h2>
        <div
          v-for="r in kyc.requests"
          :key="r.name"
          class="flex flex-wrap items-center gap-x-4 gap-y-1 rounded-lg border border-outline-gray-1 bg-surface-white px-4 py-3 text-sm"
        >
          <span class="font-medium text-ink-gray-8">{{ r.name }}</span>
          <StatusBadge :status="r.status" />
          <span class="text-xs text-ink-gray-5">{{ r.provider }}<span v-if="r.ovd_type"> · {{ r.ovd_type }}</span></span>
        </div>
      </div>
      <p v-else class="text-sm text-ink-gray-5">No verification requests yet.</p>
    </template>
  </div>
</template>
