<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { Button, TextInput } from 'frappe-ui'
import { call, logout } from '../api'

const account = ref<Record<string, unknown> | null>(null)
const gateway = ref('Stripe')
const token = ref('')
const last4 = ref('')

onMounted(async () => {
  account.value = await call('lube_station.lube_station.portal.apis.my_account', {}, 'GET')
})

async function save() {
  await call('lube_station.lube_station.portal.apis.save_method', { gateway: gateway.value, token: token.value, last_four: last4.value, make_default: true })
  token.value = ''
}
</script>

<template>
  <div class="space-y-4">
    <h1 class="text-xl font-semibold">Account</h1>
    <pre v-if="account" class="overflow-auto rounded bg-surface-gray-1 p-3 text-xs">{{ JSON.stringify({ company: account.company, status: account.status, credit_balance: account.credit_balance }, null, 2) }}</pre>
    <div class="space-y-2">
      <h2 class="font-medium">Save payment method (token only)</h2>
      <TextInput v-model="gateway" label="Gateway" />
      <TextInput v-model="token" label="Provider token" type="password" />
      <TextInput v-model="last4" label="Last four" />
      <Button label="Save + default" @click="save" />
    </div>
    <Button label="Sign out" @click="logout" />
  </div>
</template>
