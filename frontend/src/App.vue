<script setup lang="ts">
import { FrappeUIProvider } from 'frappe-ui'
import { RouterLink } from 'vue-router'
import { bootUser } from './api'

const user = bootUser()
const links = [
  ['/', 'Dashboard'],
  ['/store', 'Store'],
  ['/cart', 'Cart'],
  ['/invoices', 'Invoices'],
  ['/services', 'Services'],
  ['/vps', 'VPS'],
  ['/dedicated', 'Dedicated'],
  ['/domains', 'Domains'],
  ['/downloads', 'Downloads'],
  ['/support', 'Support'],
  ['/account', 'Account'],
] as const
</script>

<template>
  <FrappeUIProvider>
    <div class="min-h-screen bg-surface-base text-ink-gray-8">
      <nav class="flex flex-wrap items-center gap-1 border-b border-outline-gray-1 px-3 py-2">
        <span class="mr-2 text-base font-semibold">Lube Station</span>
        <RouterLink
          v-for="[to, label] in links"
          :key="to"
          :to="to"
          class="rounded px-2 py-1 text-sm hover:bg-surface-gray-2"
          active-class="bg-surface-gray-2 font-medium"
        >
          {{ label }}
        </RouterLink>
        <span class="ml-auto text-xs text-ink-gray-5">{{ user || 'Guest' }}</span>
      </nav>
      <main class="mx-auto max-w-5xl px-3 py-6">
        <RouterView />
      </main>
    </div>
  </FrappeUIProvider>
</template>
