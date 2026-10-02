<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { call } from '../api'

interface Svc { name: string; hosting_plan: string; status: string; next_due_date: string }
const list = ref<Svc[]>([])
onMounted(async () => {
  list.value = await call('lube_station.lube_station.portal.apis.my_services', {}, 'GET')
})
</script>

<template>
  <div class="space-y-3">
    <h1 class="text-xl font-semibold">Services</h1>
    <div v-for="s in list" :key="s.name" class="rounded border p-3 text-sm">
      <div class="font-medium">{{ s.name }} · {{ s.hosting_plan }}</div>
      <div>{{ s.status }} · next due {{ s.next_due_date }}</div>
    </div>
  </div>
</template>
