<script setup lang="ts">
import { ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { Button, ErrorMessage, Select, TextInput } from 'frappe-ui'
import { call } from '../api'

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
    error.value = String(e)
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
    error.value = String(e)
  }
}
</script>

<template>
  <div class="space-y-4">
    <h1 class="text-xl font-semibold">Domain options</h1>
    <p class="text-xs text-gray-500">Step 2 of 3: options → domain → review &amp; pay</p>
    <ErrorMessage v-if="error" :message="error" />
    <Select v-model="option" label="Domain choice" :options="[
      { label: 'Register a new domain', value: 'register' },
      { label: 'Transfer my domain', value: 'transfer' },
      { label: 'I will use my own domain', value: 'own' },
      { label: 'No domain needed', value: 'none' },
    ]" />
    <div v-if="option !== 'none'" class="space-y-2">
      <TextInput v-model="domain" label="Domain name" placeholder="example.com" />
      <div class="flex gap-2">
        <Button label="Check availability" :loading="checking" @click="check" />
      </div>
      <p v-if="status" class="text-sm">Status: {{ status }}</p>
      <Select v-if="option === 'register'" v-model="years" label="Registration years" :options="[1, 2, 3, 5, 10].map((y) => ({ label: `${y} year${y > 1 ? 's' : ''}`, value: y }))" />
      <TextInput v-if="option === 'transfer'" v-model="authCode" label="EPP / transfer code *" />
    </div>
    <Button label="Continue to cart" variant="solid" @click="cont" />
  </div>
</template>
