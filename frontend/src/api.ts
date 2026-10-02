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
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ usr, pwd }),
  })
  if (!res.ok) throw new Error('Login failed')
  window.location.href = '/lube_station/'
}

export async function logout(): Promise<void> {
  await fetch('/api/method/logout', { method: 'POST' })
  window.location.href = '/lube_station/login'
}

// eslint-disable-next-line @typescript-eslint/no-explicit-any
export async function call<T = any>(dotted: string, args: Record<string, unknown> = {}, method = 'POST'): Promise<T> {
  const res = await fetch(`/api/v2/method/${dotted}`, {
    method,
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
