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

let _session: string | null | undefined
function loggedUserOf(payload: unknown): string | null {
  const d = (payload ?? {}) as Record<string, unknown>
  const user = (d.data as string) || (d.message as string) || null
  return user && user !== 'Guest' ? user : null
}

export async function sessionUser(): Promise<string | null> {
  if (_session !== undefined) return _session
  try {
    const res = await fetch('/api/v2/method/frappe.auth.get_logged_user', { credentials: 'include' })
    _session = loggedUserOf(await res.json())
  } catch {
    _session = null
  }
  return _session
}

export async function login(usr: string, pwd: string): Promise<void> {
  usr = usr.trim()
  const res = await fetch('/api/method/login', {
    method: 'POST',
    credentials: 'include',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ usr, pwd }),
  })
  const data = await res.json().catch(() => ({}))
  const ok = res.ok && (data.message === 'Logged In' || data.message === 'No App' || data.full_name || data.home_page)
  if (!ok) throw new Error(data.message || 'Invalid credentials')
  // Confirm session cookie landed before leaving login page.
  const me = await fetch('/api/v2/method/frappe.auth.get_logged_user', { credentials: 'include' })
    .then((r) => r.json())
    .catch(() => ({}))
  if (!loggedUserOf(me)) throw new Error('Session not established, try again')
  window.location.href = '/store/'
}

export async function logout(): Promise<void> {
  await fetch('/api/method/logout', { method: 'POST', credentials: 'include' })
  window.location.href = '/store/login'
}

// eslint-disable-next-line @typescript-eslint/no-explicit-any
export async function call<T = any>(dotted: string, args: Record<string, unknown> = {}, method = 'POST'): Promise<T> {
  let url = `/api/v2/method/${dotted}`
  let body: string | undefined = JSON.stringify(args)
  if (method === 'GET') {
    // fetch() drops GET bodies: serialize args into the query string instead.
    const qs = new URLSearchParams()
    for (const [k, v] of Object.entries(args)) {
      if (v !== undefined && v !== null) qs.append(k, String(v))
    }
    const q = qs.toString()
    if (q) url += `?${q}`
    body = undefined
  }
  const res = await fetch(url, {
    method,
    credentials: 'include',
    headers: {
      'Content-Type': 'application/json',
      'X-Frappe-CSRF-Token': csrf(),
    },
    body,
  })
  const data = await res.json().catch(() => ({}))
  if (!res.ok) throw new Error(data.message || data.exc || `Call ${dotted} failed`)
  return (data.data ?? data.message ?? data) as T
}

export async function getDoc<T>(doctype: string, name: string): Promise<T> {
  return call<T>(`frappe.client.get`, { doctype, name }, 'POST')
}

/** Customer-safe error text. Strips framework prefixes and technical dumps. */
export function friendlyError(e: unknown): string {
  let msg = e instanceof Error ? e.message : String(e ?? '')
  msg = msg.replace(/^Error:\s*/, '')
  msg = msg.replace(
    /^(ValidationError|PermissionError|MandatoryError|LinkValidationError|DoesNotExistError|DuplicateEntryError|DataError|IntegrityError):\s*/,
    '',
  )
  if (/^Call \S+ failed/.test(msg) || /Traceback|frappe\/exceptions|\.py", line/i.test(msg)) {
    return 'Something went wrong. Please try again.'
  }
  msg = msg.split('\n')[0].trim()
  if (msg.length > 180) msg = `${msg.slice(0, 177).trimEnd()}…`
  return msg || 'Something went wrong. Please try again.'
}
