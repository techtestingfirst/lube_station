<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { RouterLink, useRouter } from 'vue-router'
import { Button, Checkbox, ErrorMessage, Select, TextInput } from 'frappe-ui'
import { call } from '../api'

interface CartItem {
  row: string
  item_type: string
  hosting_plan: string | null
  billing_cycle: string
  domain: string | null
  quantity: number
  unit_price: number
}
interface CartView {
  cart: string
  coupon_code: string | null
  subtotal: number
  discount_total: number
  grand_total: number
  items: CartItem[]
}

const cart = ref<CartView | null>(null)
const coupon = ref('')
const gateway = ref('')
const gateways = ref<{ label: string; value: string }[]>([])
const notes = ref('')
const tos = ref(false)
const error = ref('')
const loading = ref(false)
const router = useRouter()

async function refresh() {
  error.value = ''
  try {
    const [c, g] = await Promise.all([
      call<CartView>('lube_station.lube_station.portal.apis.cart_current', {}, 'GET'),
      call<{ name: string }[]>('lube_station.lube_station.portal.apis.payment_gateways', {}, 'GET'),
    ])
    cart.value = c
    gateways.value = g.map((x) => ({ label: x.name, value: x.name }))
    if (!gateway.value && gateways.value.length) gateway.value = gateways.value[0].value
  } catch (e) {
    error.value = String(e)
  }
}

async function setQty(row: string, quantity: number) {
  if (!cart.value || quantity < 1) return
  cart.value = await call('lube_station.lube_station.portal.apis.cart_set_qty', {
    cart: cart.value.cart, row, quantity,
  })
}

async function removeRow(row: string) {
  if (!cart.value) return
  cart.value = await call('lube_station.lube_station.portal.apis.cart_remove', {
    cart: cart.value.cart, row,
  })
}

async function apply() {
  if (!cart.value) return
  try {
    cart.value = await call('lube_station.lube_station.portal.apis.cart_apply_coupon', {
      cart: cart.value.cart, coupon_code: coupon.value,
    })
  } catch (e) {
    error.value = String(e)
  }
}

async function order() {
  if (!cart.value?.items.length) return
  if (!tos.value) {
    error.value = 'Accept the Terms of Service to check out'
    return
  }
  loading.value = true
  error.value = ''
  try {
    const out = await call<{ order: string; invoice: string; payment?: { url?: string } }>('lube_station.lube_station.portal.apis.checkout', {
      cart: cart.value.cart, gateway: gateway.value, notes: notes.value || undefined, tos_accepted: tos.value,
    })
    // WHMCS auto-redirect: gateway already chosen, go straight to payment.
    if (out.payment?.url) {
      window.location.href = out.payment.url
      return
    }
    router.push(`/order/${out.order}`)
  } catch (e) {
    error.value = String(e)
  } finally {
    loading.value = false
  }
}

onMounted(refresh)
</script>

<template>
  <div class="space-y-4">
    <h1 class="text-xl font-semibold">Review &amp; checkout</h1>
    <p class="text-xs text-gray-500">Step 3 of 3: options → domain → review &amp; pay</p>
    <ErrorMessage v-if="error" :message="error" />
    <div v-if="cart?.items.length" class="space-y-2">
      <div v-for="i in cart.items" :key="i.row" class="flex items-center justify-between rounded border p-3 text-sm">
        <div>
          <div class="font-medium">{{ i.item_type === 'Domain' ? `Domain: ${i.domain}` : i.hosting_plan }}</div>
          <div class="text-xs">{{ i.billing_cycle }} · {{ i.unit_price }} × {{ i.quantity }}</div>
          <div v-if="i.domain && i.item_type !== 'Domain'" class="text-xs text-gray-500">Domain: {{ i.domain }}</div>
        </div>
        <div class="flex items-center gap-2">
          <Button label="-" size="sm" @click="setQty(i.row, i.quantity - 1)" />
          <span>{{ i.quantity }}</span>
          <Button label="+" size="sm" @click="setQty(i.row, i.quantity + 1)" />
          <Button label="Remove" size="sm" @click="removeRow(i.row)" />
        </div>
      </div>
      <div class="rounded border p-3 text-sm">
        <div>Subtotal: {{ cart.subtotal }}</div>
        <div>Discount: {{ cart.discount_total }}</div>
        <div class="font-medium">Total: {{ cart.grand_total }}</div>
      </div>
      <div class="flex gap-2">
        <TextInput v-model="coupon" placeholder="Promo code" />
        <Button label="Apply" @click="apply" />
      </div>
      <TextInput v-model="notes" label="Notes for staff (optional)" placeholder="Anything we should know" />
      <Select v-if="gateways.length" v-model="gateway" label="Payment method" :options="gateways" />
      <Checkbox v-model="tos" label="I accept the Terms of Service" />
      <div class="flex gap-2">
        <RouterLink to="/store"><Button label="Continue shopping" /></RouterLink>
        <Button label="Complete order" variant="solid" :loading="loading" @click="order" />
      </div>
    </div>
    <div v-else class="text-sm">Cart empty. Visit storefront.</div>
  </div>
</template>
