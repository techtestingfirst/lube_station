<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { RouterLink } from 'vue-router'
import { Button, ErrorMessage, TextInput } from 'frappe-ui'
import { call } from '../api'

interface D { domain_name: string; status: string; expiry_date: string }
const list = ref<D[]>([])
const name = ref('')
const error = ref('')

async function refresh() {
  list.value = await call('lube_station.lube_station.portal.apis.my_domains', {}, 'GET')
}

async function register() {
  try {
    await call('lube_station.lube_station.doctype.domain.domain.register_domain', { domain: name.value })
    name.value = ''
    await refresh()
  } catch (e) {
    error.value = String(e)
  }
}

onMounted(refresh)
</script>

<template>
  <div class="space-y-3">
    <h1 class="text-xl font-semibold">Domains</h1>
    <ErrorMessage v-if="error" :message="error" />
    <div class="flex gap-2">
      <TextInput v-model="name" placeholder="example.com" />
      <Button label="Register" variant="solid" @click="register" />
    </div>
    <div v-for="d in list" :key="d.domain_name" class="flex items-center justify-between rounded border p-3 text-sm">
      <div><div class="font-medium">{{ d.domain_name }}</div><div>{{ d.status }} · expires {{ d.expiry_date }}</div></div>
      <RouterLink :to="`/dns/${d.domain_name}`" class="text-blue-600">DNS →</RouterLink>
    </div>
  </div>
</template>
