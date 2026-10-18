<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { RouterLink } from 'vue-router'
import { Badge, Button, TabList, TabPanel, TabTrigger, Tabs } from 'frappe-ui'
import { call, friendlyError } from '../api'
import { formatMoney } from '../format'
import EmptyState from '../components/EmptyState.vue'
import LoadingBlock from '../components/LoadingBlock.vue'

interface Price { billing_cycle: string; recurring_amount: number; setup_fee: number }
interface Plan { name: string; plan_name: string; product_type: string; product_group: string; prices: Price[] }
interface ProductGroup {
  name: string
  group_name: string
  slug: string | null
  description: string | null
  icon: string | null
  sort_order: number
}

const plans = ref<Plan[]>([])
const productGroups = ref<ProductGroup[]>([])
const loading = ref(true)
const active = ref<string>('')

async function fetchData() {
  loading.value = true
  try {
    const [plansData, groupsData] = await Promise.all([
      call('lube_station.lube_station.portal.apis.storefront', {}, 'GET'),
      call('lube_station.lube_station.portal.apis.product_groups', {}, 'GET'),
    ])
    plans.value = plansData
    productGroups.value = groupsData
  } finally {
    loading.value = false
  }
}

onMounted(fetchData)

const shownGroupNames = computed(() => new Set(productGroups.value.map((g) => g.group_name)))

const groupData = (groupName: string): ProductGroup | undefined =>
  productGroups.value.find((g) => g.group_name === groupName)

const groups = computed(() => {
  const map = new Map<string, Plan[]>()
  for (const p of plans.value) {
    const g = p.product_group || p.product_type || 'Plans'
    if (!shownGroupNames.value.has(g)) continue
    if (!map.has(g)) map.set(g, [])
    map.get(g)!.push(p)
  }
  return [...map.entries()]
})

watch(groups, (list) => {
  if (!list.length) return
  if (!list.some(([g]) => g === active.value)) active.value = list[0][0]
})

function fromPrice(p: Plan): string {
  if (!p.prices.length) return 'Pricing on request'
  return `From ${formatMoney(Math.min(...p.prices.map((x) => x.recurring_amount)))} / ${p.prices[0]?.billing_cycle}`
}

function cycles(p: Plan): string {
  return p.prices.map((x) => x.billing_cycle).join(' · ')
}
</script>

<template>
  <div class="space-y-6">
    <div class="flex items-start justify-between gap-3">
      <div>
        <h1 class="text-xl font-semibold tracking-tight text-ink-gray-8">Storefront</h1>
        <p class="mt-1 text-sm text-ink-gray-5">Pick a category, choose a plan, and check out in minutes.</p>
      </div>
      <RouterLink to="/cart" class="shrink-0">
        <Button label="View cart" variant="solid" />
      </RouterLink>
    </div>

    <LoadingBlock v-if="loading" :lines="4" />
    <EmptyState
      v-else-if="!plans.length"
      title="No plans available"
      hint="There is nothing to order right now. Please check back later."
      action-label="Try again"
      @action="fetchData"
    />
    <Tabs v-else v-model="active">
      <TabList>
        <TabTrigger v-for="[group] in groups" :key="group" :value="group" :label="group" />
      </TabList>
      <TabPanel v-for="[group, items] in groups" :key="group" :value="group">
        <div class="space-y-4 pt-4">
          <div class="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3">
            <div class="flex items-center gap-3">
              <img
                v-if="groupData(group)?.icon"
                :src="groupData(group)!.icon"
                :alt="group"
                class="w-10 h-10 rounded object-cover border border-outline-gray-1"
              />
              <div>
                <h2 class="text-lg font-semibold text-ink-gray-8">{{ group }}</h2>
                <div
                  v-html="groupData(group)?.description || ''"
                  class="mt-1 text-sm text-ink-gray-6 leading-relaxed max-w-xl"
                ></div>
              </div>
            </div>
          </div>
          <div class="grid gap-3 sm:grid-cols-2">
            <div
              v-for="p in items"
              :key="p.name"
              class="flex flex-col rounded-lg border border-outline-gray-1 bg-surface-white p-4"
            >
              <div class="flex items-start justify-between gap-2">
                <div class="font-medium text-ink-gray-8">{{ p.plan_name }}</div>
                <Badge theme="blue" :label="p.product_type" />
              </div>
              <div v-if="p.prices.length" class="mt-1 text-sm text-ink-gray-5">{{ cycles(p) }}</div>
              <div class="mt-2 text-sm font-medium text-ink-gray-8">{{ fromPrice(p) }}</div>
              <div class="mt-4 flex justify-end">
                <RouterLink :to="`/checkout/${p.name}`">
                  <Button label="Order" variant="solid" size="sm" />
                </RouterLink>
              </div>
            </div>
          </div>
        </div>
      </TabPanel>
    </Tabs>
  </div>
</template>
