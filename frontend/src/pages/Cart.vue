<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { RouterLink, useRouter } from 'vue-router'
import { Button, Checkbox, Select, TextInput } from 'frappe-ui'
import { call, friendlyError } from '../api'
import { formatMoney } from '../format'
import EmptyState from '../components/EmptyState.vue'
import ErrorState from '../components/ErrorState.vue'
import LoadingBlock from '../components/LoadingBlock.vue'

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
const fetching = ref(true)
const router = useRouter()

async function refresh() {
  error.value = ''
  fetching.value = true
  try {
    const [c, g] = await Promise.all([
      call<CartView>('lube_station.lube_station.portal.apis.cart_current', {}, 'GET'),
      call<{ name: string }[]>('lube_station.lube_station.portal.apis.payment_gateways', {}, 'GET'),
    ])
    cart.value = c
    try {
      localStorage.setItem('lube-last-cart', c.cart)
    } catch {
      // Non-fatal.
    }
    gateways.value = g.map((x) => ({ label: x.name, value: x.name }))
    if (!gateway.value && gateways.value.length) gateway.value = gateways.value[0].value
  } catch (e) {
    error.value = friendlyError(e)
  } finally {
    fetching.value = false
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
    error.value = friendlyError(e)
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
    error.value = friendlyError(e)
  } finally {
    loading.value = false
  }
}

onMounted(refresh)
</script>

<template>
  <div class="space-y-6">
    <div class="flex items-start justify-between gap-3">
      <div>
        <h1 class="text-xl font-semibold tracking-tight text-ink-gray-8">Review &amp; checkout</h1>
        <p class="mt-1 text-sm text-ink-gray-5">Step 3 of 3: options → domain → review &amp; pay</p>
      </div>
      <div class="flex shrink-0 items-center gap-2">
        <RouterLink to="/store">
          <Button label="Continue shopping" variant="subtle" />
        </RouterLink>
        <Button
          label="Place order"
          variant="solid"
          :disabled="!cart?.items.length"
          :loading="loading"
          @click="order"
        />
      </div>
    </div>

    <LoadingBlock v-if="fetching && !cart" :lines="4" />
    <template v-else>
      <ErrorState v-if="error" :message="error" @retry="refresh" />
      <EmptyState
        v-if="cart && !cart.items.length"
        title="Your cart is empty"
        hint="Browse the storefront to find a plan that fits."
        action-label="Browse store"
        @action="router.push('/store')"
      />
      <div v-if="cart?.items.length" class="grid gap-4 sm:grid-cols-5">
        <div class="space-y-4 sm:col-span-3">
          <div class="space-y-2 rounded-lg border border-outline-gray-1 bg-surface-white p-4">
            <div
              v-for="i in cart.items"
              :key="i.row"
              class="flex items-center justify-between gap-3 border-b border-outline-gray-1 py-3 text-sm first:pt-0 last:border-0 last:pb-0"
            >
              <div class="min-w-0">
                <div class="font-medium text-ink-gray-8">{{ i.item_type === 'Domain' ? `Domain: ${i.domain}` : i.hosting_plan }}</div>
                <div class="mt-0.5 text-sm text-ink-gray-5">{{ i.billing_cycle }} · {{ formatMoney(i.unit_price) }} × {{ i.quantity }}</div>
                <div v-if="i.domain && i.item_type !== 'Domain'" class="text-sm text-ink-gray-5">Domain: {{ i.domain }}</div>
              </div>
              <div class="flex shrink-0 items-center gap-2">
                <Button label="-" size="sm" @click="setQty(i.row, i.quantity - 1)" />
                <span class="text-sm text-ink-gray-8">{{ i.quantity }}</span>
                <Button label="+" size="sm" @click="setQty(i.row, i.quantity + 1)" />
                <Button label="Remove" size="sm" @click="removeRow(i.row)" />
              </div>
            </div>
          </div>
          <div class="space-y-3 rounded-lg border border-outline-gray-1 bg-surface-white p-4">
            <div class="flex gap-2">
              <TextInput v-model="coupon" class="flex-1" placeholder="Promo code" />
              <Button label="Apply" @click="apply" />
            </div>
            <TextInput v-model="notes" label="Notes for staff (optional)" placeholder="Anything we should know" />
            <Select v-if="gateways.length" v-model="gateway" label="Payment method" :options="gateways" />
            <Checkbox v-model="tos" label="I accept the Terms of Service" />
          </div>
        </div>
        <div class="h-fit space-y-2 rounded-lg border border-outline-gray-1 bg-surface-white p-4 sm:col-span-2">
          <h2 class="text-sm font-medium text-ink-gray-8">Order summary</h2>
          <div class="flex justify-between text-sm text-ink-gray-5">
            <span>Subtotal</span>
            <span class="text-ink-gray-8">{{ formatMoney(cart.subtotal) }}</span>
          </div>
          <div class="flex justify-between text-sm text-ink-gray-5">
            <span>Discount{{ cart.coupon_code ? ` (${cart.coupon_code})` : '' }}</span>
            <span class="text-ink-gray-8">{{ formatMoney(cart.discount_total) }}</span>
          </div>
          <div class="flex justify-between border-t border-outline-gray-1 pt-2 text-sm font-medium text-ink-gray-8">
            <span>Total</span>
            <span>{{ formatMoney(cart.grand_total) }}</span>
          </div>
        </div>
      </div>
    </template>
  </div>
</template>
