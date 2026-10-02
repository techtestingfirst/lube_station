<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { Button, ErrorMessage, Select } from 'frappe-ui'
import { call } from '../api'

const route = useRoute()
const router = useRouter()
const invoice = route.params.invoice as string
const gateway = ref('')
const gateways = ref<{ label: string; value: string }[]>([])
const result = ref('')
const error = ref('')
const methods = ref<{ name: string; gateway: string; last_four: string }[]>([])

onMounted(async () => {
  const [m, g, invs] = await Promise.all([
    call('lube_station.lube_station.portal.apis.my_methods', {}, 'GET'),
    call<{ name: string }[]>('lube_station.lube_station.portal.apis.payment_gateways', {}, 'GET'),
    call<{ name: string; gateway: string }[]>('lube_station.lube_station.portal.apis.my_invoices', {}, 'GET'),
  ])
  methods.value = m as typeof methods.value
  gateways.value = g.map((x) => ({ label: x.name, value: x.name }))
  // Preselect the gateway chosen at checkout, if any.
  const current = (invs as { name: string; gateway: string }[]).find((i) => i.name === invoice)
  gateway.value = current?.gateway && gateways.value.some((x) => x.value === current.gateway)
    ? current.gateway
    : gateways.value[0]?.value || ''
})

async function pay() {
  try {
    const out = await call<{ url?: string; manual?: boolean; instructions?: string }>('lube_station.lube_station.portal.apis.invoice_payment_link', { invoice, gateway: gateway.value })
    if (out.manual) {
      result.value = out.instructions || 'Bank transfer instructions issued. Reference your invoice.'
      return
    }
    // Hosted gateway page (Razorpay checkout) — full redirect.
    window.location.href = out.url as string
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

async function verify() {
  error.value = ''
  result.value = ''
  try {
    const out = await call<{ status: string; reason?: string }>('lube_station.lube_station.payments.verify.verify_razorpay_payment', { invoice })
    if (out.status === 'paid') {
      result.value = 'Payment confirmed. Services activating.'
      router.push('/services')
    } else {
      result.value = `Still pending: ${out.reason || 'no captured payment yet'}`
    }
  } catch (e) {
    error.value = String(e)
  }
}
</script>

<template>
  <div class="space-y-3">
    <h1 class="text-xl font-semibold">Pay {{ invoice }}</h1>
    <ErrorMessage v-if="error" :message="error" />
    <Select v-if="gateways.length" v-model="gateway" label="Payment method" :options="gateways" />
    <div class="flex gap-2">
      <Button :label="`Pay now${gateway ? ` with ${gateway}` : ''}`" variant="solid" @click="pay" />
      <Button label="Use saved card" @click="auto" />
      <Button label="I've paid — verify" @click="verify" />
    </div>
    <p class="text-xs text-gray-500">Paid via UPI/app and page stuck? Click verify — it checks Razorpay directly.</p>
    <p v-if="result" class="text-sm">{{ result }}</p>
    <div v-if="methods.length" class="text-xs">Saved: {{ methods.map((m) => `${m.gateway} ••${m.last_four}`).join(', ') }}</div>
  </div>
</template>
