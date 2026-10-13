<script setup lang="ts">
import { computed, nextTick, onMounted, ref, watch } from 'vue'
import { Button, Checkbox, ErrorMessage, Select, TextInput, Textarea } from 'frappe-ui'
import { call, friendlyError, logout } from '../api'
import { formatMoney } from '../format'
import StatusBadge from '../components/StatusBadge.vue'
import StatCard from '../components/StatCard.vue'
import EmptyState from '../components/EmptyState.vue'
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

interface Addr {
  name: string
  address_title: string
  address_type: string
  address_line1: string
  address_line2?: string | null
  city: string
  state?: string | null
  country: string
  pincode?: string | null
  phone?: string | null
  is_primary_address?: number
  is_shipping_address?: number
}

const addrList = ref<Addr[]>([])
const addrEdit = ref<string | null>(null)
const addrBusy = ref(false)
const addrMsg = ref('')
const addrError = ref('')
const aform = ref({ title: '', type: 'Billing', line1: '', line2: '', city: '', state: '', country: '', pincode: '', phone: '', primary: false, shipping: false })

const ADDR_TYPES = ['Billing', 'Shipping', 'Office', 'Personal', 'Other']

// Postcode/city/state belong to a country: changing it clears all three
// so a stale PIN can't fill (or fail) against the new country.
let suppressCountryWatch = false
watch(() => aform.value.country, (next, prev) => {
  if (suppressCountryWatch || next === prev) return
  aform.value.pincode = ''
  aform.value.city = ''
  aform.value.state = ''
  addrLookupHint.value = ''
})
const addrCountries = ref<{ label: string; value: string }[]>([])
const addrLookingUp = ref(false)
const addrLookupHint = ref('')

async function loadAddrCountries() {
  try {
    const list = await call<{ name: string }[]>('lube_station.lube_station.portal.apis.country_list', {}, 'GET')
    addrCountries.value = list.map((c) => ({ label: c.name, value: c.name }))
  } catch {
    addrCountries.value = []
  }
}

async function lookupAddrPin() {
  if (!aform.value.pincode) return
  addrLookingUp.value = true
  addrLookupHint.value = ''
  try {
    const out = await call<{ city: string; state: string }>(
      'lube_station.lube_station.portal.apis.pincode_lookup',
      { postcode: aform.value.pincode, country: aform.value.country || undefined }, 'GET')
    if (out.city) aform.value.city = out.city
    if (out.state) aform.value.state = out.state
    addrLookupHint.value = `Found: ${out.city}, ${out.state}`
  } catch (e) {
    addrLookupHint.value = friendlyError(e)
  } finally {
    addrLookingUp.value = false
  }
}

async function refresh() {
  loading.value = true
  loadError.value = ''
  try {
    const [acc, addrs] = await Promise.all([
      call('lube_station.lube_station.portal.apis.my_account', {}, 'GET'),
      call<Addr[]>('lube_station.lube_station.customers.addresses.my_addresses', {}, 'GET').catch(() => [] as Addr[]),
    ])
    account.value = acc as Record<string, unknown>
    addrList.value = addrs
  } catch (e) {
    loadError.value = friendlyError(e)
  } finally {
    loading.value = false
  }
}

function addrLines(a: Addr): string {
  return [a.address_line1, a.address_line2, [a.city, a.state].filter(Boolean).join(', '), [a.pincode, a.country].filter(Boolean).join(' ')].filter(Boolean).join(', ')
}

function startAddrAdd() {
  suppressCountryWatch = true
  aform.value = { title: '', type: 'Billing', line1: '', line2: '', city: '', state: '', country: '', pincode: '', phone: '', primary: addrList.value.length === 0, shipping: addrList.value.length === 0 }
  addrMsg.value = ''
  addrError.value = ''
  addrEdit.value = 'new'
  nextTick(() => { suppressCountryWatch = false })
}

function startAddrEdit(a: Addr) {
  suppressCountryWatch = true
  aform.value = {
    title: a.address_title || '', type: a.address_type || 'Billing', line1: a.address_line1 || '',
    line2: a.address_line2 || '', city: a.city || '', state: a.state || '', country: a.country || '',
    pincode: a.pincode || '', phone: a.phone || '', primary: !!a.is_primary_address, shipping: !!a.is_shipping_address,
  }
  addrMsg.value = ''
  addrError.value = ''
  addrEdit.value = a.name
  nextTick(() => { suppressCountryWatch = false })
}

async function saveAddr() {
  addrMsg.value = ''
  addrError.value = ''
  addrBusy.value = true
  try {
    const API = 'lube_station.lube_station.customers.addresses'
    if (addrEdit.value === 'new') {
      await call(`${API}.add_address`, {
        address_title: aform.value.title, address_type: aform.value.type, address_line1: aform.value.line1,
        address_line2: aform.value.line2 || undefined, city: aform.value.city, state: aform.value.state || undefined,
        country: aform.value.country, pincode: aform.value.pincode || undefined, phone: aform.value.phone || undefined,
        is_primary: aform.value.primary, is_shipping: aform.value.shipping,
      })
      addrMsg.value = 'Address added.'
    } else {
      await call(`${API}.update_address`, {
        name: addrEdit.value, address_title: aform.value.title, address_type: aform.value.type,
        address_line1: aform.value.line1, address_line2: aform.value.line2, city: aform.value.city,
        state: aform.value.state, country: aform.value.country, pincode: aform.value.pincode,
        phone: aform.value.phone, is_primary: aform.value.primary, is_shipping: aform.value.shipping,
      })
      addrMsg.value = 'Address updated.'
    }
    addrEdit.value = null
    await refresh()
  } catch (e) {
    addrError.value = friendlyError(e)
  } finally {
    addrBusy.value = false
  }
}

async function addrDefault(name: string, kind: string) {
  addrBusy.value = true
  try {
    await call('lube_station.lube_station.customers.addresses.set_default_address', { name, kind })
    await refresh()
  } catch (e) {
    addrError.value = friendlyError(e)
  } finally {
    addrBusy.value = false
  }
}

async function addrRemove(name: string) {
  addrBusy.value = true
  try {
    await call('lube_station.lube_station.customers.addresses.delete_address', { name })
    addrMsg.value = 'Address removed.'
    await refresh()
  } catch (e) {
    addrError.value = friendlyError(e)
  } finally {
    addrBusy.value = false
  }
}

onMounted(() => {
  refresh()
  loadAddrCountries()
})

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
    </div>

    <LoadingBlock v-if="loading" :lines="3" />
    <ErrorState v-else-if="loadError" :message="loadError" @retry="refresh" />
    <template v-else-if="account">
      <div class="grid grid-cols-2 gap-3 sm:grid-cols-3">
        <StatCard :value="formatMoney(account.credit_balance as number | string | null)" label="Credit balance" />
      </div>

      <div class="rounded-lg border border-outline-gray-1 bg-surface-white p-4">
        <div class="flex items-center gap-2">
          <div class="text-sm font-medium text-ink-gray-8">Profile</div>
          <StatusBadge :status="String(account.status ?? '')" />
          <div class="ml-auto">
            <Button
              v-if="!editing"
              label="Edit"
              variant="subtle"
              size="sm"
              @click="startEdit"
            />
          </div>
        </div>
        <div v-if="!editing" class="mt-2 flex flex-wrap items-start justify-between gap-3">
          <div class="min-w-0">
            <div class="truncate text-sm font-medium text-ink-gray-8">{{ account.company }}</div>
            <div v-if="addressBlock" class="mt-2 whitespace-pre-line text-sm text-ink-gray-5">{{ addressBlock }}</div>
            <div v-if="account.phone" class="mt-1 text-sm text-ink-gray-5">{{ account.phone }}</div>
            <div v-if="account.tax_id" class="mt-1 text-sm text-ink-gray-5">Tax / VAT: {{ account.tax_id }}</div>
          </div>
          <Button label="Sign out" theme="red" variant="outline" size="sm" iconLeft="lucide-log-out" class="shrink-0" @click="logout" />
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

      <div class="rounded-lg border border-outline-gray-1 bg-surface-white p-4">
        <div class="flex items-center justify-between gap-3">
          <div class="text-sm font-medium text-ink-gray-8">Addresses ({{ addrList.length }})</div>
          <Button v-if="!addrEdit" label="Add" variant="subtle" size="sm" @click="startAddrAdd" />
        </div>
        <div v-if="addrList.length" class="mt-2 divide-y divide-outline-gray-1">
          <div v-for="a in addrList" :key="a.name" class="py-2">
            <div class="flex flex-wrap items-center gap-2 text-sm">
              <span class="font-medium text-ink-gray-8">{{ a.address_title }}</span>
              <StatusBadge :status="a.address_type" />
              <StatusBadge v-if="a.is_primary_address" status="Default billing" />
              <StatusBadge v-if="a.is_shipping_address" status="Default shipping" />
            </div>
            <div class="mt-0.5 text-sm text-ink-gray-5">{{ addrLines(a) }}</div>
            <div class="mt-1 flex flex-wrap gap-2">
              <Button v-if="!a.is_primary_address" label="Default billing" variant="ghost" size="sm" :loading="addrBusy" @click="addrDefault(a.name, 'billing')" />
              <Button v-if="!a.is_shipping_address" label="Default shipping" variant="ghost" size="sm" :loading="addrBusy" @click="addrDefault(a.name, 'shipping')" />
              <Button label="Edit" variant="ghost" size="sm" @click="startAddrEdit(a)" />
              <Button label="Remove" variant="ghost" size="sm" @click="addrRemove(a.name)" />
            </div>
          </div>
        </div>
        <EmptyState v-else-if="!addrEdit" title="No saved addresses" hint="Add your billing and shipping addresses." />
        <div v-if="addrEdit" class="mt-3 space-y-3 border-t border-outline-gray-1 pt-3">
          <div class="grid gap-3 sm:grid-cols-2">
            <TextInput v-model="aform.title" label="Label *" placeholder="Home" />
            <Select v-model="aform.type" label="Type" :options="ADDR_TYPES.map((t) => ({ label: t, value: t }))" />
            <TextInput v-model="aform.line1" label="Address line 1 *" class="sm:col-span-2" />
            <TextInput v-model="aform.line2" label="Address line 2" class="sm:col-span-2" />
            <TextInput v-model="aform.city" label="City *" />
            <TextInput v-model="aform.state" label="State" />
            <Select
              v-if="addrCountries.length"
              v-model="aform.country"
              label="Country *"
              :options="addrCountries"
            />
            <TextInput v-else v-model="aform.country" label="Country *" placeholder="India" />
            <div>
              <TextInput v-model="aform.pincode" label="Pincode" @blur="lookupAddrPin" @keyup.enter="lookupAddrPin" />
              <Button class="mt-2" label="Find city" size="sm" :loading="addrLookingUp" @click="lookupAddrPin" />
            </div>
            <p v-if="addrLookupHint" class="text-xs text-ink-gray-5 sm:col-span-2">{{ addrLookupHint }}</p>
            <TextInput v-model="aform.phone" label="Phone" class="sm:col-span-2" />
          </div>
          <div class="flex flex-wrap gap-4">
            <Checkbox v-model="aform.primary" label="Default billing" />
            <Checkbox v-model="aform.shipping" label="Default shipping" />
          </div>
          <div class="flex gap-2">
            <Button label="Save" variant="solid" size="sm" :loading="addrBusy" @click="saveAddr" />
            <Button label="Cancel" variant="subtle" size="sm" @click="addrEdit = null" />
          </div>
          <ErrorMessage v-if="addrError" :message="addrError" />
        </div>
        <p v-if="addrMsg && !addrEdit" class="mt-2 text-sm text-ink-gray-8">{{ addrMsg }}</p>
      </div>
    </template>

    <div class="rounded-lg border border-outline-gray-1 bg-surface-white p-4">
      <div class="text-sm font-medium text-ink-gray-8">Save payment method (token only)</div>
      <p class="mt-1 text-sm text-ink-gray-5">Only the provider token and last four are stored.</p>
      <div class="mt-2 space-y-3">
        <TextInput v-model="gateway" label="Gateway" />
        <TextInput v-model="token" label="Provider token" type="password" />
        <TextInput v-model="last4" label="Last four" />
        <div>
          <Button label="Save + default" variant="solid" size="sm" :loading="saving" @click="save" />
        </div>
        <ErrorMessage v-if="saveError" :message="saveError" />
        <p v-if="savedMsg" class="text-sm text-ink-gray-8">{{ savedMsg }}</p>
      </div>
    </div>
  </div>
</template>
