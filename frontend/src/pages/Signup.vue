<script setup lang="ts">
import { onMounted, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import { RouterLink } from 'vue-router'
import { Button, Checkbox, ErrorMessage, Select, TextInput } from 'frappe-ui'
import { call, login } from '../api'

const name = ref('')
const email = ref('')
const password = ref('')
const company = ref('')
const phone = ref('')
const address = ref('')
const city = ref('')
const state = ref('')
const postcode = ref('')
const country = ref('')
const tos = ref(false)
const error = ref('')
const lookupHint = ref('')
const lookingUp = ref(false)
const loading = ref(false)
const router = useRouter()
const countries = ref<{ label: string; value: string }[]>([])

// Postcode/city/state belong to a country: changing it clears all three
// so a stale PIN can't fetch (or fail) against the new country.
watch(country, () => {
  postcode.value = ''
  city.value = ''
  state.value = ''
  lookupHint.value = ''
})

onMounted(async () => {
  try {
    const list = await call<{ name: string }[]>('lube_station.lube_station.portal.apis.country_list', {}, 'GET')
    countries.value = list.map((c) => ({ label: c.name, value: c.name }))
    if (!country.value) country.value = 'India'
  } catch {
    countries.value = []
  }
})

async function lookup() {
  if (!postcode.value) return
  lookingUp.value = true
  lookupHint.value = ''
  try {
    const out = await call<{ city: string; state: string }>(
      'lube_station.lube_station.portal.apis.pincode_lookup',
      { postcode: postcode.value, country: country.value || undefined }, 'GET')
    if (out.city) city.value = out.city
    if (out.state) state.value = out.state
    lookupHint.value = `Found: ${out.city}, ${out.state}`
  } catch (e) {
    lookupHint.value = String(e)
  } finally {
    lookingUp.value = false
  }
}

async function submit() {
  loading.value = true
  error.value = ''
  try {
    await call('lube_station.lube_station.portal.apis.signup_customer', {
      full_name: name.value, email: email.value, password: password.value,
      company: company.value || undefined, phone: phone.value || undefined,
      address_line1: address.value || undefined, city: city.value || undefined,
      state: state.value || undefined, postcode: postcode.value || undefined,
      country: country.value || undefined, tos_accepted: tos.value,
    })
  } catch (e) {
    error.value = String(e).replace('ValidationError: ', '')
    loading.value = false
    return
  }
  try {
    await login(email.value, password.value)
    return
  } catch (e) {
    router.push({ path: '/login', query: { email: email.value, created: '1' } })
  }
}
</script>

<template>
  <div class="mx-auto max-w-sm space-y-4">
    <h1 class="text-xl font-semibold">Create account</h1>
    <TextInput v-model="name" label="Full name *" />
    <TextInput v-model="email" label="Email *" placeholder="you@example.com" />
    <TextInput v-model="password" label="Password (8+ characters) *" type="password" />
    <TextInput v-model="company" label="Company (optional)" />
    <TextInput v-model="phone" label="Phone" />
    <TextInput v-model="address" label="Street address" />
    <div class="grid grid-cols-2 gap-2">
      <TextInput v-model="city" label="City" />
      <TextInput v-model="state" label="State / County" />
      <div>
        <TextInput v-model="postcode" label="Postcode" @blur="lookup" @keyup.enter="lookup" />
        <Button class="mt-1" label="Find city" size="sm" :loading="lookingUp" @click="lookup" />
      </div>
      <Select v-if="countries.length" v-model="country" label="Country" :options="countries" />
      <TextInput v-else v-model="country" label="Country" />
    </div>
    <p v-if="lookingUp" class="text-xs text-gray-500">Looking up postcode…</p>
    <p v-else-if="lookupHint" class="text-xs text-gray-500">{{ lookupHint }}</p>
    <Checkbox v-model="tos" label="I accept the Terms of Service *" />
    <ErrorMessage v-if="error" :message="error" />
    <Button label="Sign up" variant="solid" :loading="loading" @click="submit" />
    <p class="text-sm">Have account? <RouterLink to="/login" class="text-blue-600">Sign in</RouterLink></p>
  </div>
</template>
