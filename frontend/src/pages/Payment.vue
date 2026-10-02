<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { useRoute } from 'vue-router'
import { Button, ErrorMessage, Select } from 'frappe-ui'
import { call } from '../api'

const route = useRoute()
const invoice = route.params.invoice as string
const gateway = ref('Stripe')
const result = ref('')
const error = ref('')
const methods = ref<{ name: string; gateway: string; last_four: string }[]>([])

onMounted(async () => {
  methods.value = await call('lube_station.lube_station.portal.apis.my_methods', {}, 'GET')
})

async function pay() {
  try {
    const out = await call<{ url?: string; manual?: boolean }>('lube_station.lube_station.payments.links.payment_link', { invoice, gateway: gateway.value })
    result.value = out.manual ? 'Bank transfer instructions issued. Reference your invoice.' : `Pay here: ${out.url}`
  } catch (e) {
    error.value = String(e)
  }
}

async function auto() {
  try {
    const out = await call<{ action: string }>('lube_station.lube_station.payments.methods.auto_charge_invoice', { invoice })
    result.value = `Auto-charge: ${out.action}`
  } catch (e) {
    error.value = String(e)
  }
}
</script>

<template>
  <div class="space-y-3">
    <h1 class="text-xl font-semibold">Pay {{ invoice }}</h1>
    <ErrorMessage v-if="error" :message="error" />
    <Select v-model="gateway" label="Gateway" :options="['Stripe', 'Razorpay', 'PayPal Checkout', 'Bank Transfer'].map((g) => ({ label: g, value: g }))" />
    <div class="flex gap-2">
      <Button label="Get payment link" variant="solid" @click="pay" />
      <Button label="Auto-charge saved method" @click="auto" />
    </div>
    <p v-if="result" class="text-sm">{{ result }}</p>
    <div v-if="methods.length" class="text-xs">Saved: {{ methods.map((m) => `${m.gateway} ••${m.last_four}`).join(', ') }}</div>
  </div>
</template>
