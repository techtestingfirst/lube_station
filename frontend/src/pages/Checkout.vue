<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { Button, ErrorMessage, Select, TextInput } from 'frappe-ui'
import { call } from '../api'

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

onMounted(async () => {
  info.value = await call('lube_station.lube_station.portal.apis.checkout_info', { plan })
})

async function cont() {
  error.value = ''
  try {
    const cart = await call<{ items: { row: string }[] }>('lube_station.lube_station.portal.apis.cart_add', {
      hosting_plan: plan, billing_cycle: cycle.value, quantity: quantity.value, configuration: values.value,
    })
    const row = cart.items[cart.items.length - 1].row
    router.push(`/domain/${row}`)
  } catch (e) {
    error.value = String(e)
  }
}
</script>

<template>
  <div class="space-y-4">
    <h1 class="text-xl font-semibold">Configure plan</h1>
    <p class="text-xs text-gray-500">Step 1 of 3: options → domain → review &amp; pay</p>
    <ErrorMessage v-if="error" :message="error" />
    <div v-if="info">
      <Select v-model="cycle" label="Billing cycle" :options="info.prices.map((p) => ({ label: `${p.billing_cycle} — ${p.recurring_amount}`, value: p.billing_cycle }))" />
      <div class="mt-3">
        <label class="text-xs">Quantity</label>
        <div class="flex items-center gap-2">
          <Button label="-" size="sm" @click="quantity = Math.max(1, quantity - 1)" />
          <span>{{ quantity }}</span>
          <Button label="+" size="sm" @click="quantity = quantity + 1" />
        </div>
      </div>
      <div v-if="info.requirements" class="mt-3 space-y-2">
        <div v-for="f in info.requirements.fields" :key="f.field_key">
          <TextInput v-model="values[f.field_key]" :label="`${f.label}${f.required ? ' *' : ''}`" :type="f.field_type === 'Password' ? 'password' : 'text'" />
        </div>
      </div>
      <Button class="mt-4" label="Continue to domain" variant="solid" @click="cont" />
    </div>
  </div>
</template>
