<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { Button, ErrorMessage, TextInput } from 'frappe-ui'
import { call } from '../api'

const cart = ref<string | null>(localStorage.getItem('ls_cart'))
const totals = ref<{ subtotal: number; discount: number; grand_total: number } | null>(null)
const coupon = ref('')
const error = ref('')
const router = useRouter()

async function refresh() {
  if (!cart.value) return
  totals.value = await call('lube_station.lube_station.doctype.cart.cart.totals', { cart: cart.value }, 'GET')
}

async function apply() {
  try {
    await call('lube_station.lube_station.doctype.cart.cart.apply_coupon', { cart: cart.value, coupon_code: coupon.value })
    await refresh()
  } catch (e) {
    error.value = String(e)
  }
}

async function order() {
  try {
    const out = await call<{ order: string }>('lube_station.lube_station.doctype.order.order.place_order', { cart: cart.value })
    localStorage.removeItem('ls_cart')
    router.push(`/invoices`)
    return out
  } catch (e) {
    error.value = String(e)
  }
}

onMounted(refresh)
</script>

<template>
  <div class="space-y-4">
    <h1 class="text-xl font-semibold">Cart</h1>
    <ErrorMessage v-if="error" :message="error" />
    <div v-if="totals" class="rounded border p-3 text-sm">
      <div>Subtotal: {{ totals.subtotal }}</div>
      <div>Discount: {{ totals.discount }}</div>
      <div class="font-medium">Total: {{ totals.grand_total }}</div>
    </div>
    <div v-else class="text-sm">Cart empty. Visit storefront.</div>
    <div class="flex gap-2">
      <TextInput v-model="coupon" placeholder="Coupon code" />
      <Button label="Apply" @click="apply" />
    </div>
    <Button label="Place order" variant="solid" @click="order" />
  </div>
</template>
