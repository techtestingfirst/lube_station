<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { Button, Select } from 'frappe-ui'
import { call, friendlyError } from '../api'
import ErrorState from '../components/ErrorState.vue'
import LoadingBlock from '../components/LoadingBlock.vue'

const route = useRoute()
const router = useRouter()
const invoice = route.params.invoice as string
const gateway = ref('')
const gateways = ref<{ label: string; value: string }[]>([])
const result = ref('')
const error = ref('')
const fetching = ref(true)
const paying = ref(false)
const methods = ref<{ name: string; gateway: string; last_four: string }[]>([])

async function load() {
  fetching.value = true
  error.value = ''
  try {
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
  } catch (e) {
    error.value = friendlyError(e)
  } finally {
    fetching.value = false
  }
}

onMounted(load)

async function pay() {
  paying.value = true
  try {
    const out = await call<{ url?: string; manual?: boolean; instructions?: string }>('lube_station.lube_station.portal.apis.invoice_payment_link', { invoice, gateway: gateway.value })
    if (out.manual) {
      result.value = out.instructions || 'Bank transfer instructions issued. Reference your invoice.'
      return
    }
    // Hosted gateway page (Razorpay checkout) — full redirect.
    window.location.href = out.url as string
  } catch (e) {
    error.value = friendlyError(e)
  } finally {
    paying.value = false
  }
}

async function auto() {
  try {
    const out = await call<{ action: string }>('lube_station.lube_station.payments.methods.auto_charge_invoice', { invoice })
    result.value = `Auto-charge: ${out.action}`
  } catch (e) {
    error.value = friendlyError(e)
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
    error.value = friendlyError(e)
  }
}
</script>

<template>
  <div class="space-y-6">
    <div class="flex items-start justify-between gap-3">
      <div>
        <h1 class="text-xl font-semibold tracking-tight text-ink-gray-8">Pay {{ invoice }}</h1>
        <p class="mt-1 text-sm text-ink-gray-5">Complete payment to activate your services.</p>
      </div>
      <Button
        class="shrink-0"
        :label="`Pay now${gateway ? ` with ${gateway}` : ''}`"
        variant="solid"
        :disabled="fetching || !gateways.length"
        :loading="paying"
        @click="pay"
      />
    </div>

    <LoadingBlock v-if="fetching" :lines="3" />
    <template v-else>
      <ErrorState v-if="error" :message="error" @retry="load" />
      <div class="grid gap-4 sm:grid-cols-5">
        <div class="space-y-3 rounded-lg border border-outline-gray-1 bg-surface-white p-4 sm:col-span-3">
          <Select v-if="gateways.length" v-model="gateway" label="Payment method" :options="gateways" />
          <div class="flex flex-wrap gap-2">
            <Button label="Use saved card" variant="subtle" @click="auto" />
            <Button label="I've paid — verify" variant="subtle" @click="verify" />
          </div>
          <p class="text-sm text-ink-gray-5">Paid via UPI/app and page stuck? Click verify — it checks Razorpay directly.</p>
          <p v-if="result" class="text-sm text-ink-gray-8">{{ result }}</p>
        </div>
        <div class="h-fit space-y-2 rounded-lg border border-outline-gray-1 bg-surface-white p-4 sm:col-span-2">
          <h2 class="text-sm font-medium text-ink-gray-8">Payment summary</h2>
          <div class="flex justify-between text-sm text-ink-gray-5">
            <span>Invoice</span>
            <span class="text-ink-gray-8">{{ invoice }}</span>
          </div>
          <div class="flex justify-between text-sm text-ink-gray-5">
            <span>Method</span>
            <span class="text-ink-gray-8">{{ gateway || '—' }}</span>
          </div>
          <div v-if="methods.length" class="border-t border-outline-gray-1 pt-2 text-sm text-ink-gray-5">
            Saved: {{ methods.map((m) => `${m.gateway} ••${m.last_four}`).join(', ') }}
          </div>
        </div>
      </div>
    </template>
  </div>
</template>
