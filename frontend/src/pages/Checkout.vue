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
const values = ref<Record<string, string>>({})
const error = ref('')

onMounted(async () => {
  info.value = await call('lube_station.lube_station.portal.apis.checkout_info', { plan })
})

async function addToCart() {
  error.value = ''
  try {
    let cart: string | null = localStorage.getItem('ls_cart')
    if (!cart) {
      const doc = await call<{ name: string }>('frappe.client.insert', { doc: { doctype: 'Cart', session_id: `web-${Date.now()}` } })
      cart = doc.name
      localStorage.setItem('ls_cart', cart)
    }
    await call('lube_station.lube_station.doctype.cart.cart.add_item', {
      cart, item_type: 'Hosting Plan', hosting_plan: plan, billing_cycle: cycle.value, configuration: values.value,
    })
    router.push('/cart')
  } catch (e) {
    error.value = String(e)
  }
}
</script>

<template>
  <div class="space-y-4">
    <h1 class="text-xl font-semibold">Configure plan</h1>
    <ErrorMessage v-if="error" :message="error" />
    <div v-if="info">
      <Select v-model="cycle" label="Billing cycle" :options="info.prices.map((p) => ({ label: `${p.billing_cycle} — ${p.recurring_amount}`, value: p.billing_cycle }))" />
      <div v-if="info.requirements" class="mt-3 space-y-2">
        <div v-for="f in info.requirements.fields" :key="f.field_key">
          <TextInput v-model="values[f.field_key]" :label="`${f.label}${f.required ? ' *' : ''}`" :type="f.field_type === 'Password' ? 'password' : 'text'" />
        </div>
      </div>
      <Button class="mt-4" label="Add to cart" variant="solid" @click="addToCart" />
    </div>
  </div>
</template>
