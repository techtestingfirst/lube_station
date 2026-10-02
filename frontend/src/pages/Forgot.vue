<script setup lang="ts">
import { ref } from 'vue'
import { RouterLink } from 'vue-router'
import { Button, ErrorMessage, TextInput } from 'frappe-ui'
import { call } from '../api'

const email = ref('')
const error = ref('')
const done = ref(false)

async function submit() {
  error.value = ''
  try {
    await call('lube_station.lube_station.portal.apis.forgot_password', { email: email.value })
    done.value = true
  } catch (e) {
    error.value = String(e).replace('ValidationError: ', '')
  }
}
</script>

<template>
  <div class="mx-auto max-w-sm space-y-4">
    <h1 class="text-xl font-semibold">Reset password</h1>
    <p v-if="done" class="text-sm">If account exists, reset link sent. Check inbox.</p>
    <template v-else>
      <TextInput v-model="email" label="Account email" placeholder="you@example.com" />
      <ErrorMessage v-if="error" :message="error" />
      <Button label="Send reset link" variant="solid" @click="submit" />
    </template>
    <p class="text-sm"><RouterLink to="/login" class="text-blue-600">Back to sign in</RouterLink></p>
  </div>
</template>
