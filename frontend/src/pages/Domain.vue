<script setup lang="ts">
import { ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { Button, ErrorMessage, Select, TextInput } from 'frappe-ui'
import { call, friendlyError } from '../api'
import StatusBadge from '../components/StatusBadge.vue'

const route = useRoute()
const router = useRouter()
const row = route.params.row as string
const option = ref<'register' | 'transfer' | 'own' | 'none'>('register')
const domain = ref('')
const years = ref(1)
const authCode = ref('')
const status = ref('')
const checking = ref(false)
const error = ref('')

async function check() {
  error.value = ''
  status.value = ''
  if (!domain.value) return
  checking.value = true
  try {
    const out = await call<{ status: string; premium_price: number }>(
      'lube_station.lube_station.portal.apis.domain_check', { domain: domain.value }, 'GET')
    status.value = out.status
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
    await call('lube_station.lube_station.portal.apis.cart_set_domain', {
      cart: cart.cart, row, domain: domain.value || undefined,
      domain_action: option.value, years: years.value, auth_code: authCode.value || undefined,
    })
    router.push('/cart')
  } catch (e) {
    error.value = friendlyError(e)
  }
}
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
        { label: 'No domain needed', value: 'none' },
      ]" class="mt-2" />
    </div>

    <div v-if="option !== 'none'" class="rounded-lg border border-outline-gray-1 bg-surface-white p-4">
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
        <Select v-if="option === 'register'" v-model="years" label="Registration years" :options="[1, 2, 3, 5, 10].map((y) => ({ label: `${y} year${y > 1 ? 's' : ''}`, value: y }))" />
        <TextInput v-if="option === 'transfer'" v-model="authCode" label="EPP / transfer code *" />
      </div>
    </div>
  </div>
</template>
