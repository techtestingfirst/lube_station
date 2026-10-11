<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { Button, ErrorMessage, TextInput, Textarea } from 'frappe-ui'
import { call, friendlyError, logout } from '../api'
import { formatMoney } from '../format'
import StatusBadge from '../components/StatusBadge.vue'
import StatCard from '../components/StatCard.vue'
import LoadingBlock from '../components/LoadingBlock.vue'
import ErrorState from '../components/ErrorState.vue'

const account = ref<Record<string, unknown> | null>(null)
const gateway = ref('Stripe')
const token = ref('')
const last4 = ref('')
const loading = ref(true)
const loadError = ref('')
const saving = ref(false)
const savedMsg = ref('')
const saveError = ref('')
const editing = ref(false)
const profileSaving = ref(false)
const profileMsg = ref('')
const profileError = ref('')
const form = ref<Record<string, string>>({})

const PROFILE_FIELDS = ['company', 'phone', 'tax_id', 'billing_address', 'address_line1', 'city', 'state', 'postcode', 'country']

const addressBlock = computed(() => {
  if (!account.value) return ''
  const direct = String(account.value.billing_address ?? '').trim()
  if (direct) return direct
  return ['address_line1', 'city', 'state', 'postcode', 'country']
    .map((k) => String(account.value?.[k] ?? '').trim())
    .filter(Boolean)
    .join(', ')
})

function startEdit() {
  form.value = Object.fromEntries(PROFILE_FIELDS.map((k) => [k, String(account.value?.[k] ?? '')]))
  profileMsg.value = ''
  profileError.value = ''
  editing.value = true
}

async function saveProfile() {
  profileMsg.value = ''
  profileError.value = ''
  profileSaving.value = true
  try {
    await call('lube_station.lube_station.portal.apis.update_account', { ...form.value })
    editing.value = false
    profileMsg.value = 'Profile updated.'
    await refresh()
  } catch (e) {
    profileError.value = friendlyError(e)
  } finally {
    profileSaving.value = false
  }
}

async function refresh() {
  loading.value = true
  loadError.value = ''
  try {
    account.value = await call('lube_station.lube_station.portal.apis.my_account', {}, 'GET')
  } catch (e) {
    loadError.value = friendlyError(e)
  } finally {
    loading.value = false
  }
}

onMounted(refresh)

async function save() {
  saveError.value = ''
  savedMsg.value = ''
  saving.value = true
  try {
    await call('lube_station.lube_station.portal.apis.save_method', { gateway: gateway.value, token: token.value, last_four: last4.value, make_default: true })
    token.value = ''
    savedMsg.value = 'Payment method saved and set as default.'
  } catch (e) {
    saveError.value = friendlyError(e)
  } finally {
    saving.value = false
  }
}
</script>

<template>
  <div class="space-y-4">
    <div class="flex flex-wrap items-start justify-between gap-3">
      <div>
        <h1 class="text-xl font-semibold tracking-tight text-ink-gray-8">Account</h1>
        <p class="mt-1 text-sm text-ink-gray-5">Profile, credit balance and saved payment method.</p>
      </div>
      <Button label="Save + default" variant="solid" size="sm" :loading="saving" @click="save" />
    </div>

    <LoadingBlock v-if="loading" :lines="3" />
    <ErrorState v-else-if="loadError" :message="loadError" @retry="refresh" />
    <template v-else-if="account">
      <div class="grid grid-cols-2 gap-3 sm:grid-cols-3">
        <StatCard :value="formatMoney(account.credit_balance as number | string | null)" label="Credit balance" />
      </div>

      <div class="rounded-lg border border-outline-gray-1 bg-surface-white p-4">
        <div class="flex items-center justify-between gap-3">
          <div class="text-sm font-medium text-ink-gray-8">Profile</div>
          <Button
            v-if="!editing"
            label="Edit"
            variant="subtle"
            size="sm"
            @click="startEdit"
          />
        </div>
        <div v-if="!editing" class="mt-2 flex flex-wrap items-start justify-between gap-3">
          <div class="min-w-0">
            <div class="truncate text-sm font-medium text-ink-gray-8">{{ account.company }}</div>
            <div class="mt-1 flex flex-wrap items-center gap-2 text-sm text-ink-gray-5">
              <StatusBadge :status="String(account.status ?? '')" />
              <span>Credit {{ formatMoney(account.credit_balance as number | string | null) }}</span>
            </div>
            <div v-if="addressBlock" class="mt-2 whitespace-pre-line text-sm text-ink-gray-5">{{ addressBlock }}</div>
            <div v-if="account.phone" class="mt-1 text-sm text-ink-gray-5">{{ account.phone }}</div>
            <div v-if="account.tax_id" class="mt-1 text-sm text-ink-gray-5">Tax / VAT: {{ account.tax_id }}</div>
          </div>
          <Button label="Sign out" variant="outline" size="sm" class="shrink-0" @click="logout" />
        </div>
        <div v-else class="mt-2 space-y-3">
          <div class="grid gap-3 sm:grid-cols-2">
            <TextInput v-model="form.company" label="Company" />
            <TextInput v-model="form.phone" label="Phone" />
            <TextInput v-model="form.tax_id" label="Tax / VAT ID" />
            <TextInput v-model="form.country" label="Country" placeholder="India" />
            <TextInput v-model="form.address_line1" label="Address line" class="sm:col-span-2" />
            <TextInput v-model="form.city" label="City" />
            <TextInput v-model="form.state" label="State" />
            <TextInput v-model="form.postcode" label="Postcode" />
          </div>
          <Textarea v-model="form.billing_address" label="Full billing address (optional override)" :rows="3" />
          <div class="flex gap-2">
            <Button label="Save" variant="solid" size="sm" :loading="profileSaving" @click="saveProfile" />
            <Button label="Cancel" variant="subtle" size="sm" @click="editing = false" />
          </div>
          <ErrorMessage v-if="profileError" :message="profileError" />
        </div>
        <p v-if="profileMsg && !editing" class="mt-2 text-sm text-ink-gray-8">{{ profileMsg }}</p>
      </div>
    </template>

    <div class="rounded-lg border border-outline-gray-1 bg-surface-white p-4">
      <div class="text-sm font-medium text-ink-gray-8">Save payment method (token only)</div>
      <p class="mt-1 text-sm text-ink-gray-5">Only the provider token and last four are stored.</p>
      <div class="mt-2 space-y-3">
        <TextInput v-model="gateway" label="Gateway" />
        <TextInput v-model="token" label="Provider token" type="password" />
        <TextInput v-model="last4" label="Last four" />
        <ErrorMessage v-if="saveError" :message="saveError" />
        <p v-if="savedMsg" class="text-sm text-ink-gray-8">{{ savedMsg }}</p>
      </div>
    </div>
  </div>
</template>
