<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { Button, ErrorMessage, Select, TextInput } from 'frappe-ui'
import { call, friendlyError } from '../api'
import { formatMoney } from '../format'
import StatusBadge from '../components/StatusBadge.vue'

const route = useRoute()
const router = useRouter()
const row = route.params.row as string
const option = ref<'register' | 'transfer' | 'own' | 'subdomain' | 'none'>('register')
const domain = ref('')
const subPrefix = ref('')
const subSuffix = ref('')
const suffixes = ref<{ label: string; value: string }[]>([])
const years = ref(1)
const authCode = ref('')
const status = ref('')
const premium = ref(0)
const pricing = ref<{ register: number; renew: number; transfer: number } | null>(null)
const checking = ref(false)
const error = ref('')

async function check() {
  error.value = ''
  status.value = ''
  pricing.value = null
  if (!domain.value) return
  checking.value = true
  try {
    const out = await call<{ status: string; premium_price: number; pricing?: { register: number; renew: number; transfer: number } }>(
      'lube_station.lube_station.portal.apis.domain_check', { domain: domain.value }, 'GET')
    status.value = out.status
    pricing.value = out.pricing ?? null
    premium.value = out.status === 'Premium' ? (out.premium_price || 0) : 0
    if (premium.value) years.value = 1
  } catch (e) {
    error.value = friendlyError(e)
  } finally {
    checking.value = false
  }
}

async function cont() {
  error.value = ''
  try {
    const cart = await call<{ cart: string }>('lube_station.lube_station.portal.apis.cart_current', {}, 'GET')
    const full = option.value === 'subdomain' ? `${subPrefix.value.trim().toLowerCase()}.${subSuffix.value}` : (domain.value || undefined)
    await call('lube_station.lube_station.portal.apis.cart_set_domain', {
      cart: cart.cart, row, domain: full,
      domain_action: option.value, years: years.value, auth_code: authCode.value || undefined,
    })
    router.push('/cart')
  } catch (e) {
    error.value = friendlyError(e)
  }
}

onMounted(async () => {
  try {
    const list = await call<string[]>('lube_station.lube_station.portal.apis.subdomain_suffixes', {}, 'GET')
    suffixes.value = list.map((s) => ({ label: `.${s}`, value: s }))
    if (suffixes.value.length && !subSuffix.value) subSuffix.value = suffixes.value[0].value
  } catch {
    suffixes.value = []
  }
})
</script>

<template>
  <div class="space-y-4">
    <div class="flex flex-wrap items-start justify-between gap-3">
      <div>
        <h1 class="text-xl font-semibold tracking-tight text-ink-gray-8">Domain options</h1>
        <p class="mt-1 text-sm text-ink-gray-5">Step 2 of 3: options → domain → review &amp; pay</p>
      </div>
      <Button label="Continue to cart" variant="solid" size="sm" @click="cont" />
    </div>

    <ErrorMessage v-if="error" :message="error" />

    <div class="rounded-lg border border-outline-gray-1 bg-surface-white p-4">
      <div class="text-sm font-medium text-ink-gray-8">Domain choice</div>
      <Select v-model="option" label="Domain choice" :options="[
        { label: 'Register a new domain', value: 'register' },
        { label: 'Transfer my domain', value: 'transfer' },
        { label: 'I will use my own domain', value: 'own' },
        ...(suffixes.length ? [{ label: 'Use a free subdomain', value: 'subdomain' }] : []),
        { label: 'No domain needed', value: 'none' },
      ]" class="mt-2" />
    </div>

    <div v-if="option === 'subdomain'" class="rounded-lg border border-outline-gray-1 bg-surface-white p-4">
      <div class="text-sm font-medium text-ink-gray-8">Free subdomain</div>
      <div class="mt-2 space-y-3">
        <TextInput v-model="subPrefix" label="Your name" placeholder="mywebsite" />
        <Select v-model="subSuffix" label="Ending" :options="suffixes" />
        <div v-if="subPrefix" class="text-sm text-ink-gray-5">
          Your address: <span class="font-medium text-ink-gray-8">{{ subPrefix.trim().toLowerCase() }}.{{ subSuffix }}</span>
        </div>
      </div>
    </div>

    <div v-if="option !== 'none' && option !== 'subdomain'" class="rounded-lg border border-outline-gray-1 bg-surface-white p-4">
      <div class="text-sm font-medium text-ink-gray-8">Domain details</div>
      <div class="mt-2 space-y-3">
        <TextInput v-model="domain" label="Domain name" placeholder="example.com" />
        <div>
          <Button label="Check availability" :loading="checking" @click="check" />
        </div>
        <div v-if="status" class="flex flex-wrap items-center gap-2 text-sm text-ink-gray-5">
          <span>Status:</span>
          <StatusBadge :status="status" />
        </div>
        <div v-if="pricing" class="text-sm text-ink-gray-5">
          Register {{ formatMoney(pricing.register) }}/yr · Renew {{ formatMoney(pricing.renew) }}/yr · Transfer {{ formatMoney(pricing.transfer) }}
        </div>
        <div v-if="premium" class="rounded-md bg-surface-gray-1 p-2 text-sm text-ink-gray-8">
          Premium domain: {{ formatMoney(premium) }} one-time for year 1, then renews at the regular rate.
        </div>
        <Select v-if="option === 'register' && !premium" v-model="years" label="Registration years" :options="[1, 2, 3, 5, 10].map((y) => ({ label: `${y} year${y > 1 ? 's' : ''}`, value: y }))" />
        <TextInput v-if="option === 'transfer'" v-model="authCode" label="EPP / transfer code *" />
      </div>
    </div>
  </div>
</template>
