<script setup lang="ts">
import { Button } from 'frappe-ui'
</script>

<template>
  <div class="flex min-h-[50vh] items-center justify-center">
    <div class="w-full max-w-md rounded-lg border border-outline-gray-1 bg-surface-white px-6 py-12 text-center">
      <p class="text-3xl font-semibold tracking-tight text-ink-gray-8">404</p>
      <p class="mt-2 text-sm font-medium text-ink-gray-8">Page not found</p>
      <p class="mx-auto mt-1 max-w-sm text-sm text-ink-gray-5">There's nothing at this address.</p>
      <Button class="mt-4" variant="solid" label="Go home" route="/" />
    </div>
  </div>
</template>
