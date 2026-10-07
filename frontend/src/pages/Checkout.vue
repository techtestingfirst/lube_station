<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { RouterLink, useRoute, useRouter } from 'vue-router'
import { Button, Select, TextInput } from 'frappe-ui'
import { call, friendlyError } from '../api'
import { formatMoney } from '../format'
import EmptyState from '../components/EmptyState.vue'
import ErrorState from '../components/ErrorState.vue'
import LoadingBlock from '../components/LoadingBlock.vue'

interface ReqField { field_key: string; label: string; field_type: string; required: boolean }
interface Info { prices: { billing_cycle: string; recurring_amount: number }[]; requirements: { fields: ReqField[]; flags: Record<string, boolean> } | null }

const route = useRoute()
const router = useRouter()
const plan = route.params.plan as string
const info = ref<Info | null>(null)
const cycle = ref('Monthly')
const quantity = ref(1)
const values = ref<Record<string, string>>({})
const error = ref('')
const fetching = ref(true)
const submitting = ref(false)

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
const total = computed(() => (selected.value ? selected.value.recurring_amount * quantity.value : 0))

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
          :options="info.prices.map((p) => ({ label: `${p.billing_cycle} — ${formatMoney(p.recurring_amount)}`, value: p.billing_cycle }))"
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
          <div v-for="f in info.requirements.fields" :key="f.field_key">
            <TextInput
              v-model="values[f.field_key]"
              :label="`${f.label}${f.required ? ' *' : ''}`"
              :type="f.field_type === 'Password' ? 'password' : 'text'"
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
        <div class="flex justify-between border-t border-outline-gray-1 pt-2 text-sm font-medium text-ink-gray-8">
          <span>Total</span>
          <span>{{ formatMoney(total) }}</span>
        </div>
      </div>
    </div>
  </div>
</template>
