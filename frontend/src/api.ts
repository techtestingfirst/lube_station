function csrf(): string {
  const w = window as unknown as Record<string, unknown>
  const boot = (w.boot ?? {}) as Record<string, unknown>
  return (boot.csrf_token as string) || (w.csrf_token as string) || ''
}

export function bootUser(): string | null {
  const w = window as unknown as Record<string, unknown>
  const boot = (w.boot ?? {}) as Record<string, unknown>
  return (boot.user as string) || (w.user as string) || null
}

export async function login(usr: string, pwd: string): Promise<void> {
  const res = await fetch('/api/method/login', {
    method: 'POST',
    credentials: 'include',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ usr, pwd }),
  })
  const data = await res.json().catch(() => ({}))
  const ok = res.ok && (data.message === 'Logged In' || data.full_name || data.home_page)
  if (!ok) throw new Error(data.message || 'Invalid credentials')
  // Confirm session cookie landed before leaving login page.
  const me = await fetch('/api/v2/method/frappe.auth.get_logged_user', { credentials: 'include' })
    .then((r) => r.json())
    .catch(() => ({}))
  if (!me.message || me.message === 'Guest') throw new Error('Session not established, try again')
  window.location.href = '/lube_station/'
}

export async function logout(): Promise<void> {
  await fetch('/api/method/logout', { method: 'POST', credentials: 'include' })
  window.location.href = '/lube_station/login'
}

// eslint-disable-next-line @typescript-eslint/no-explicit-any
export async function call<T = any>(dotted: string, args: Record<string, unknown> = {}, method = 'POST'): Promise<T> {
  const res = await fetch(`/api/v2/method/${dotted}`, {
    method,
    credentials: 'include',
    headers: {
      'Content-Type': 'application/json',
      'X-Frappe-CSRF-Token': csrf(),
    },
    body: method === 'GET' ? undefined : JSON.stringify(args),
  })
  const data = await res.json().catch(() => ({}))
  if (!res.ok) throw new Error(data.message || data.exc || `Call ${dotted} failed`)
  return (data.message ?? data) as T
}

export async function getDoc<T>(doctype: string, name: string): Promise<T> {
  return call<T>(`frappe.client.get`, { doctype, name }, 'POST')
}
