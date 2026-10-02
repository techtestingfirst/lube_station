<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { RouterLink } from 'vue-router'
import { Button } from 'frappe-ui'
import { call } from '../api'

interface Price { billing_cycle: string; recurring_amount: number; setup_fee: number }
interface Plan { name: string; plan_name: string; product_type: string; product_group: string; prices: Price[] }

const plans = ref<Plan[]>([])
onMounted(async () => {
  plans.value = await call('lube_station.lube_station.portal.apis.storefront', {}, 'GET')
})

const groups = computed(() => {
  const map = new Map<string, Plan[]>()
  for (const p of plans.value) {
    const g = p.product_group || p.product_type || 'Plans'
    if (!map.has(g)) map.set(g, [])
    map.get(g)!.push(p)
  }
  return [...map.entries()]
})
</script>

<template>
  <div class="space-y-6">
    <h1 class="text-xl font-semibold">Storefront</h1>
    <div v-for="[group, items] in groups" :key="group" class="space-y-3">
      <h2 class="text-base font-medium text-gray-700">{{ group }}</h2>
      <div v-for="p in items" :key="p.name" class="rounded border p-3">
        <div class="flex items-center justify-between">
          <div><div class="font-medium">{{ p.plan_name }}</div><div class="text-xs">{{ p.product_type }}</div></div>
          <RouterLink :to="`/checkout/${p.name}`"><Button label="Order Now" variant="solid" size="sm" /></RouterLink>
        </div>
        <div class="mt-2 text-xs">{{ p.prices.length ? `From ${Math.min(...p.prices.map((x) => x.recurring_amount))} / ${p.prices[0]?.billing_cycle}` : 'Pricing on request' }}</div>
      </div>
    </div>
  </div>
</template>
