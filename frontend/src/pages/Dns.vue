<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { useRoute } from 'vue-router'
import { Button, ErrorMessage, Select, TextInput } from 'frappe-ui'
import { call } from '../api'

const route = useRoute()
const domain = route.params.domain as string
interface R { name: string; record_type: string; hostname: string; record_value: string; ttl: number }
const list = ref<R[]>([])
const rtype = ref('A')
const host = ref('@')
const value = ref('')
const error = ref('')

async function refresh() {
  list.value = await call('lube_station.lube_station.portal.apis.dns_list', { domain }, 'GET')
}

async function add() {
  try {
    await call('lube_station.lube_station.portal.apis.dns_add', { domain, record_type: rtype.value, hostname: host.value, value: value.value })
    value.value = ''
    await refresh()
  } catch (e) {
    error.value = String(e)
  }
}

onMounted(refresh)
</script>

<template>
  <div class="space-y-3">
    <h1 class="text-xl font-semibold">DNS · {{ domain }}</h1>
    <ErrorMessage v-if="error" :message="error" />
    <div class="flex flex-wrap gap-2">
      <Select v-model="rtype" label="Type" :options="['A', 'AAAA', 'CNAME', 'MX', 'TXT', 'NS', 'SRV'].map((t) => ({ label: t, value: t }))" />
      <TextInput v-model="host" label="Host" />
      <TextInput v-model="value" label="Value" />
      <Button label="Add" variant="solid" @click="add" />
    </div>
    <div v-for="r in list" :key="r.name" class="rounded border p-2 text-sm">{{ r.record_type }} {{ r.hostname }} → {{ r.record_value }} ({{ r.ttl }})</div>
  </div>
</template>
