<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { RouterLink, useRouter } from 'vue-router'
import {
  FrappeUIProvider,
  Sidebar,
  SidebarHeader,
  SidebarItem,
  SidebarLabel,
  SidebarSection,
  useColorScheme,
} from 'frappe-ui'
import { bootUser, logout, sessionUser } from './api'
import ThemeToggle from './components/ThemeToggle.vue'

useColorScheme()

const router = useRouter()
const user = ref<string | null>(bootUser())
const sidebarCollapsed = ref<boolean | null>(null)

function toggleSidebar() {
  sidebarCollapsed.value = sidebarCollapsed.value == null ? false : !sidebarCollapsed.value
}

onMounted(async () => {
  if (!user.value) user.value = await sessionUser()
})

async function signOut() {
  await logout()
  user.value = null
  router.push('/login')
}
</script>

<template>
  <FrappeUIProvider>
    <div class="flex h-screen overflow-hidden bg-surface-base text-ink-gray-8">
      <Sidebar v-if="user" v-model:collapsed="sidebarCollapsed" collapsible>
        <SidebarHeader title="Lube Station" subtitle="Client portal" />
        <div class="flex-1 overflow-y-auto">
          <SidebarSection>
            <SidebarItem label="Dashboard" route="/" icon="layout-dashboard" />
            <SidebarItem label="Store" route="/store" icon="store" />
          </SidebarSection>
          <SidebarSection>
            <SidebarLabel>Manage</SidebarLabel>
            <SidebarItem label="Services" route="/services" icon="server" />
            <SidebarItem label="VPS" route="/vps" icon="cpu" />
            <SidebarItem label="Dedicated" route="/dedicated" icon="hard-drive" />
            <SidebarItem label="Domains" route="/domains" icon="globe" />
            <SidebarItem label="Downloads" route="/downloads" icon="download" />
            <SidebarItem label="Support" route="/support" icon="life-buoy" />
            <SidebarItem label="Knowledge Base" route="/kb" icon="book-open" />
          </SidebarSection>
          <SidebarSection>
            <SidebarLabel>Billing</SidebarLabel>
            <SidebarItem label="Cart" route="/cart" icon="shopping-cart" />
            <SidebarItem label="Orders" route="/orders" icon="package" />
            <SidebarItem label="Invoices" route="/invoices" icon="receipt" />
            <SidebarItem label="Wallet" route="/wallet" icon="wallet" />
          </SidebarSection>
          <SidebarSection>
            <SidebarItem label="Account" route="/account" icon="user" />
          </SidebarSection>
        </div>
      </Sidebar>

      <div class="flex min-w-0 flex-1 flex-col">
        <header class="flex h-12 flex-shrink-0 items-center gap-2 border-b border-outline-gray-1 px-3">
          <button
            v-if="user"
            class="rounded px-2 py-1 text-sm text-ink-gray-6 hover:bg-surface-gray-2"
            :title="sidebarCollapsed ? 'Expand menu' : 'Collapse menu'"
            @click="toggleSidebar"
          >
            ☰
          </button>
          <RouterLink v-if="!user" to="/store" class="text-sm font-semibold">Lube Station</RouterLink>
          <div class="ml-auto flex items-center gap-2">
            <template v-if="!user">
              <RouterLink to="/store" class="rounded px-2 py-1 text-sm hover:bg-surface-gray-2">Store</RouterLink>
              <RouterLink to="/login" class="rounded px-2 py-1 text-sm hover:bg-surface-gray-2">Sign in</RouterLink>
              <RouterLink to="/signup" class="rounded px-2 py-1 text-sm hover:bg-surface-gray-2">Sign up</RouterLink>
            </template>
            <span v-else class="hidden text-xs text-ink-gray-5 sm:inline">{{ user }}</span>
            <button
              v-if="user"
              class="rounded px-2 py-1 text-sm text-ink-gray-6 hover:bg-surface-gray-2"
              @click="signOut"
            >
              Sign out
            </button>
            <ThemeToggle />
          </div>
        </header>
        <main class="mx-auto w-full max-w-5xl flex-1 overflow-y-auto px-4 py-6">
          <RouterView />
        </main>
      </div>
    </div>
  </FrappeUIProvider>
</template>
