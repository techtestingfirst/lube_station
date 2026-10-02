<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { RouterLink } from 'vue-router'
import { Button } from 'frappe-ui'
import { call } from '../api'

interface Price { billing_cycle: string; recurring_amount: number; setup_fee: number }
interface Plan { name: string; plan_name: string; product_type: string; prices: Price[] }

const plans = ref<Plan[]>([])
onMounted(async () => {
  plans.value = await call('lube_station.lube_station.portal.apis.storefront', {}, 'GET')
})
</script>

<template>
  <div class="space-y-4">
    <h1 class="text-xl font-semibold">Storefront</h1>
    <div v-for="p in plans" :key="p.name" class="rounded border p-3">
      <div class="flex items-center justify-between">
        <div><div class="font-medium">{{ p.plan_name }}</div><div class="text-xs">{{ p.product_type }}</div></div>
        <RouterLink :to="`/checkout/${p.name}`"><Button label="Configure" variant="solid" size="sm" /></RouterLink>
      </div>
      <div class="mt-2 text-xs">From {{ Math.min(...p.prices.map((x) => x.recurring_amount)) }} / {{ p.prices[0]?.billing_cycle }}</div>
    </div>
  </div>
</template>
