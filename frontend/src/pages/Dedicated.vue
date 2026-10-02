<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { call } from '../api'

interface D { name: string; asset_id: string; location: string; status: string; assigned_service: string }
const list = ref<D[]>([])
onMounted(async () => {
  list.value = await call('lube_station.lube_station.portal.apis.my_dedicated', {}, 'GET')
})
</script>

<template>
  <div class="space-y-3">
    <h1 class="text-xl font-semibold">Dedicated servers</h1>
    <div v-for="d in list" :key="d.name" class="rounded border p-3 text-sm">
      <div class="font-medium">{{ d.asset_id || d.name }} · {{ d.location }}</div>
      <div>{{ d.status }} · service {{ d.assigned_service }}</div>
      <div class="text-xs">Credentials via portal vault. Wipe verified before release.</div>
    </div>
    <p v-if="!list.length" class="text-sm">No dedicated servers assigned.</p>
  </div>
</template>
