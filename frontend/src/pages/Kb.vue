<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { Button, ErrorMessage, TextInput } from 'frappe-ui'
import { call, friendlyError } from '../api'
import EmptyState from '../components/EmptyState.vue'

interface Category {
  name: string
  category_name: string
  description?: string | null
  article_count: number
}

interface Article {
  name: string
  title: string
  category: string
  published_on?: string | null
  modified?: string
}

const categories = ref<Category[]>([])
const articles = ref<Article[]>([])
const loading = ref(false)
const listError = ref('')
const q = ref('')
const searching = ref(false)

const API = 'lube_station.lube_station.support.articles'

/** Helpdesk SPA lives on backend origin (:8000). Dev Vite runs :8080. */
function backendOrigin(): string {
  const { protocol, hostname, port } = window.location
  if (port === '8080') return `${protocol}//${hostname}:8000`
  return ''
}

const kbUrl = computed(() => `${backendOrigin()}/helpdesk/kb-public`)

function articleUrl(name: string): string {
  return `${backendOrigin()}/helpdesk/kb-public/articles/${name}`
}

function categoryUrl(name: string): string {
  return `${backendOrigin()}/helpdesk/kb-public/${name}`
}

const catName = computed(() => {
  const m: Record<string, string> = {}
  for (const c of categories.value) m[c.name] = c.category_name
  return m
})

const grouped = computed(() => {
  const groups: Record<string, Article[]> = {}
  for (const a of articles.value) {
    const key = a.category || ''
    ;(groups[key] ||= []).push(a)
  }
  return Object.entries(groups).sort(([, x], [, y]) => y.length - x.length)
})

function sectionTitle(key: string): string {
  return catName.value[key] || 'More articles'
}

onMounted(() => load())

async function load() {
  listError.value = ''
  loading.value = true
  try {
    const [cats, arts] = await Promise.all([
      call<Category[]>(`${API}.my_kb_categories`, {}, 'GET'),
      call<Article[]>(`${API}.my_kb_articles`, { q: q.value || undefined }, 'GET'),
    ])
    categories.value = cats
    articles.value = arts
  } catch (e) {
    listError.value = friendlyError(e)
  } finally {
    loading.value = false
  }
}

async function search() {
  searching.value = true
  try {
    articles.value = await call<Article[]>(`${API}.my_kb_articles`, { q: q.value || undefined }, 'GET')
  } catch (e) {
    listError.value = friendlyError(e)
  } finally {
    searching.value = false
  }
}

function openKb() {
  window.open(kbUrl.value, '_blank')
}
</script>

<template>
  <div class="space-y-4">
    <div class="flex flex-wrap items-start justify-between gap-3">
      <div>
        <h1 class="text-xl font-semibold tracking-tight text-ink-gray-8">Knowledge Base</h1>
        <p class="mt-1 text-sm text-ink-gray-5">
          Guides live in Helpdesk — search here, read there.
        </p>
      </div>
      <a :href="kbUrl" target="_blank" rel="noopener">
        <Button label="Open Knowledge Base" variant="solid" size="sm" />
      </a>
    </div>

    <div class="flex gap-2">
      <TextInput
        v-model="q"
        class="flex-1"
        placeholder="Search articles…"
        @keydown.enter="search"
      />
      <Button label="Search" variant="subtle" size="sm" :loading="searching" @click="search" />
    </div>

    <div class="rounded-lg border border-outline-gray-1 bg-surface-white p-4">
      <div v-if="loading" class="text-sm text-ink-gray-5">Loading articles…</div>
      <ErrorMessage v-else-if="listError" :message="listError" />
      <div v-else-if="articles.length" class="space-y-5">
        <section v-for="[key, arts] in grouped" :key="key">
          <div class="flex items-center justify-between">
            <div class="text-sm font-medium text-ink-gray-8">{{ sectionTitle(key) }}</div>
            <a
              v-if="key && catName[key]"
              :href="categoryUrl(key)"
              target="_blank"
              rel="noopener"
              class="text-xs text-ink-gray-5 hover:underline"
            >
              View all →
            </a>
          </div>
          <div class="mt-1 divide-y divide-outline-gray-1">
            <a
              v-for="a in arts"
              :key="a.name"
              :href="articleUrl(a.name)"
              target="_blank"
              rel="noopener"
              class="block px-1 py-2 hover:bg-surface-gray-1"
            >
              <div class="truncate text-sm font-medium text-ink-gray-8">{{ a.title }}</div>
              <div class="mt-0.5 text-xs text-ink-gray-5">
                Published {{ a.published_on || a.modified || '—' }}
              </div>
            </a>
          </div>
        </section>
      </div>
      <EmptyState
        v-else
        title="No articles found"
        hint="Try a different search, or browse the full base in Helpdesk."
        action-label="Open Knowledge Base"
        @action="openKb"
      />
    </div>
  </div>
</template>
