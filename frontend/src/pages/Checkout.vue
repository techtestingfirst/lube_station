<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { RouterLink, useRoute, useRouter } from 'vue-router'
import { Button, Checkbox, Select, TextInput } from 'frappe-ui'
import { call, friendlyError } from '../api'
import { formatMoney } from '../format'
import EmptyState from '../components/EmptyState.vue'
import ErrorState from '../components/ErrorState.vue'
import LoadingBlock from '../components/LoadingBlock.vue'

interface ReqField { field_key: string; label: string; field_type: string; required: boolean; options_json?: any }
interface Price { billing_cycle: string; recurring_amount: number; setup_fee?: number }
interface Info { prices: Price[]; requirements: { fields: ReqField[]; flags: Record<string, boolean> } | null }

const FLAG_DEFS = [
  { key: 'hostname', label: 'Hostname', flag: 'requires_hostname', type: 'text', placeholder: 'vps1.example.com' },
  { key: 'root_password', label: 'Root password', flag: 'requires_root_password', type: 'password', placeholder: '10+ chars, letters + numbers' },
  { key: 'ns1', label: 'Nameserver 1', flag: 'requires_nameservers', type: 'text', placeholder: 'ns1.example.com' },
  { key: 'ns2', label: 'Nameserver 2', flag: 'requires_nameservers', type: 'text', placeholder: 'ns2.example.com' },
  { key: 'os', label: 'Operating system', flag: 'requires_os', type: 'text', placeholder: 'Ubuntu 22.04' },
  { key: 'location', label: 'Location', flag: 'requires_location', type: 'text', placeholder: 'Mumbai' },
] as const

const FLAG_ALIASES: Record<string, string[]> = {
  hostname: ['hostname'],
  root_password: ['root_password', 'root_pass', 'rootpw'],
  ns1: ['ns1', 'nameserver1', 'ns_prefix_1'],
  ns2: ['ns2', 'nameserver2', 'ns_prefix_2'],
  os: ['os', 'os_image', 'image'],
  location: ['location', 'datacenter', 'region'],
}

const route = useRoute()
const router = useRouter()
const plan = route.params.plan as string
const info = ref<Info | null>(null)
const cycle = ref('Monthly')
const quantity = ref(1)
const values = ref<Record<string, any>>({})
const error = ref('')
const fetching = ref(true)
const submitting = ref(false)

const coveredKeys = computed(() => {
  const set = new Set<string>()
  for (const f of info.value?.requirements?.fields ?? []) set.add(f.field_key.toLowerCase())
  return set
})

function flagCovered(key: string): boolean {
  return (FLAG_ALIASES[key] ?? [key]).some((a) => coveredKeys.value.has(a.toLowerCase()))
}

// WHMCS parity: schema flags render canonical inputs when no matching
// field row exists. Server enforces the same keys in validate_config.
const flagFields = computed(() => {
  const flags = info.value?.requirements?.flags ?? {}
  return FLAG_DEFS.filter((d) => flags[d.flag] && !flagCovered(d.key)).map((d) => ({
    ...d,
    required: d.key !== 'ns2' ? true : true,
  }))
})

const needsDomain = computed(() => !!info.value?.requirements?.flags?.requires_domain)

function priceEntries(f: ReqField): { value: string; price: number }[] {
  const o = f.options_json
  if (!o) return []
  if (Array.isArray(o)) {
    return o
      .filter((v: any) => typeof v === 'object' && v.value != null && Number(v.price ?? v.price_delta ?? v.amount ?? 0) > 0)
      .map((v: any) => ({ value: String(v.value), price: Number(v.price ?? v.price_delta ?? v.amount) }))
  }
  if (typeof o === 'object') {
    if (o.price_per_unit != null || (o.price != null && Object.keys(o).length === 1)) return []
    return Object.entries(o)
      .map(([value, spec]: [string, any]) => ({
        value,
        price: Number(typeof spec === 'object' ? (spec.price ?? spec.price_delta ?? spec.amount ?? 0) : spec) || 0,
      }))
      .filter((e) => e.price > 0)
  }
  return []
}

function selectOptions(f: ReqField): { label: string; value: string }[] {
  const o = f.options_json
  const prices = new Map(priceEntries(f).map((e) => [e.value, e.price]))
  if (!o) return []
  if (Array.isArray(o)) {
    return o.map((v: any) => {
      if (typeof v === 'string') return { label: v, value: v }
      const price = Number(v.price ?? v.price_delta ?? v.amount ?? 0) || 0
      const label = String(v.label ?? v.value)
      return { label: price > 0 ? `${label} (+${formatMoney(price)})` : label, value: String(v.value ?? v.label) }
    })
  }
  return Object.entries(o).map(([value, spec]: [string, any]) => {
    if (value === 'price' || value === 'price_per_unit' || value === 'price_delta' || value === 'amount' || value === 'label') {
      return { label: value, value }
    }
    const label = typeof spec === 'object' ? String(spec.label ?? value) : value
    const price = prices.get(value) ?? 0
    return { label: price > 0 ? `${label} (+${formatMoney(price)})` : label, value }
  })
}

// Client estimate only; server recomputes authoritatively in cart recalc.
function deltaFor(f: ReqField, raw: any): number {
  if (raw == null || raw === '') return 0
  if (f.field_type === 'Select') {
    return priceEntries(f).find((e) => e.value === String(raw))?.price ?? 0
  }
  if (f.field_type === 'Multi Select') {
    const list = Array.isArray(raw) ? raw.map(String) : String(raw).split(',').map((s) => s.trim()).filter(Boolean)
    return list.reduce((sum, v) => sum + (priceEntries(f).find((e) => e.value === v)?.price ?? 0), 0)
  }
  if (f.field_type === 'Checkbox') {
    const on = raw === true || raw === 1 || raw === '1' || raw === 'true' || raw === 'yes' || raw === 'on'
    if (!on) return 0
    const o = f.options_json
    if (o && typeof o === 'object' && !Array.isArray(o) && o.price != null && Object.keys(o).length === 1) {
      return Number(o.price) || 0
    }
    return 0
  }
  if (f.field_type === 'Integer' || f.field_type === 'Decimal') {
    const o: any = f.options_json
    const per = o && typeof o === 'object' && !Array.isArray(o) ? Number(o.price_per_unit) || 0 : 0
    return per > 0 ? (Number(raw) || 0) * per : 0
  }
  return 0
}

async function load() {
  fetching.value = true
  error.value = ''
  try {
    info.value = await call('lube_station.lube_station.portal.apis.checkout_info', { plan })
  } catch (e) {
    error.value = friendlyError(e)
  } finally {
    fetching.value = false
  }
}

onMounted(load)

const selected = computed(
  () => info.value?.prices.find((p) => p.billing_cycle === cycle.value) ?? info.value?.prices[0] ?? null,
)
const optionsDelta = computed(() => {
  const fields = info.value?.requirements?.fields ?? []
  return fields.reduce((sum, f) => sum + deltaFor(f, values.value[f.field_key]), 0)
})
const setupFee = computed(() => (selected.value?.setup_fee ?? 0) * quantity.value)
const total = computed(() =>
  selected.value ? (selected.value.recurring_amount + optionsDelta.value) * quantity.value : 0,
)
const dueNow = computed(() => total.value + setupFee.value)

async function cont() {
  error.value = ''
  submitting.value = true
  try {
    const cart = await call<{ items: { row: string }[] }>('lube_station.lube_station.portal.apis.cart_add', {
      hosting_plan: plan, billing_cycle: cycle.value, quantity: quantity.value, configuration: values.value,
    })
    const row = cart.items[cart.items.length - 1].row
    router.push(`/domain/${row}`)
  } catch (e) {
    error.value = friendlyError(e)
  } finally {
    submitting.value = false
  }
}
</script>

<template>
  <div class="space-y-6">
    <div class="flex items-start justify-between gap-3">
      <div>
        <h1 class="text-xl font-semibold tracking-tight text-ink-gray-8">Configure plan</h1>
        <p class="mt-1 text-sm text-ink-gray-5">Step 1 of 3: options → domain → review &amp; pay</p>
      </div>
      <div class="flex shrink-0 items-center gap-2">
        <RouterLink to="/store">
          <Button label="Back to store" variant="subtle" />
        </RouterLink>
        <Button
          label="Continue to domain"
          variant="solid"
          :disabled="!info"
          :loading="submitting"
          @click="cont"
        />
      </div>
    </div>

    <LoadingBlock v-if="fetching" :lines="4" />
    <ErrorState v-else-if="error" :message="error" @retry="load" />
    <EmptyState
      v-else-if="!info"
      title="Plan not found"
      hint="This plan is no longer available. Browse the store for alternatives."
      action-label="Browse store"
      @action="router.push('/store')"
    />
    <div v-else class="grid gap-4 sm:grid-cols-5">
      <div class="space-y-4 rounded-lg border border-outline-gray-1 bg-surface-white p-4 sm:col-span-3">
        <Select
          v-model="cycle"
          label="Billing cycle"
          :options="info.prices.map((p) => ({ label: `${p.billing_cycle} — ${formatMoney(p.recurring_amount)}${(p.setup_fee ?? 0) > 0 ? ` + ${formatMoney(p.setup_fee ?? 0)} setup` : ''}`, value: p.billing_cycle }))"
        />
        <div>
          <label class="text-xs text-ink-gray-5">Quantity</label>
          <div class="mt-1 flex items-center gap-2">
            <Button label="-" size="sm" @click="quantity = Math.max(1, quantity - 1)" />
            <span class="text-sm text-ink-gray-8">{{ quantity }}</span>
            <Button label="+" size="sm" @click="quantity = quantity + 1" />
          </div>
        </div>
        <div v-if="info.requirements" class="space-y-2">
          <div v-if="needsDomain" class="rounded-md bg-surface-gray-1 p-2 text-xs text-ink-gray-5">
            Domain picked in next step (register / transfer / own domain).
          </div>
          <div v-for="f in flagFields" :key="f.key">
            <TextInput
              v-model="values[f.key]"
              :label="`${f.label} *`"
              :type="f.type === 'password' ? 'password' : 'text'"
              :placeholder="f.placeholder"
            />
          </div>
          <div v-for="f in info.requirements.fields" :key="f.field_key">
            <Select
              v-if="f.field_type === 'Select'"
              v-model="values[f.field_key]"
              :label="`${f.label}${f.required ? ' *' : ''}`"
              :options="selectOptions(f)"
            />
            <Checkbox
              v-else-if="f.field_type === 'Checkbox'"
              v-model="values[f.field_key]"
              :label="`${f.label}${f.required ? ' *' : ''}`"
            />
            <TextInput
              v-else
              v-model="values[f.field_key]"
              :label="`${f.label}${f.required ? ' *' : ''}`"
              :type="f.field_type === 'Password' ? 'password' : f.field_type === 'Integer' || f.field_type === 'Decimal' ? 'number' : 'text'"
            />
          </div>
        </div>
      </div>
      <div class="h-fit space-y-2 rounded-lg border border-outline-gray-1 bg-surface-white p-4 sm:col-span-2">
        <h2 class="text-sm font-medium text-ink-gray-8">Order summary</h2>
        <div class="flex justify-between text-sm text-ink-gray-5">
          <span>Plan</span>
          <span class="truncate text-ink-gray-8">{{ plan }}</span>
        </div>
        <div class="flex justify-between text-sm text-ink-gray-5">
          <span>Cycle</span>
          <span class="text-ink-gray-8">{{ selected?.billing_cycle ?? '—' }}</span>
        </div>
        <div class="flex justify-between text-sm text-ink-gray-5">
          <span>Quantity</span>
          <span class="text-ink-gray-8">{{ quantity }}</span>
        </div>
        <div v-if="optionsDelta > 0" class="flex justify-between text-sm text-ink-gray-5">
          <span>Options</span>
          <span class="text-ink-gray-8">+{{ formatMoney(optionsDelta * quantity) }}</span>
        </div>
        <div v-if="setupFee > 0" class="flex justify-between text-sm text-ink-gray-5">
          <span>Setup (first invoice)</span>
          <span class="text-ink-gray-8">{{ formatMoney(setupFee) }}</span>
        </div>
        <div class="flex justify-between border-t border-outline-gray-1 pt-2 text-sm font-medium text-ink-gray-8">
          <span>Due now</span>
          <span>{{ formatMoney(dueNow) }}</span>
        </div>
        <div class="flex justify-between text-xs text-ink-gray-5">
          <span>Recurs</span>
          <span>{{ formatMoney(total) }} / {{ selected?.billing_cycle ?? '—' }}</span>
        </div>
      </div>
    </div>
  </div>
</template>
