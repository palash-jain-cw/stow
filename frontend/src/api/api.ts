const BASE = import.meta.env.VITE_API_BASE_URL ?? 'http://localhost:8000'

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    headers: { 'Content-Type': 'application/json', ...init?.headers },
    ...init,
  })
  if (!res.ok) {
    const text = await res.text().catch(() => res.statusText)
    throw new Error(`${res.status}: ${text}`)
  }
  return res.json() as Promise<T>
}

export const api = {
  get: <T>(path: string) => request<T>(path),
  post: <T>(path: string, body: unknown) =>
    request<T>(path, { method: 'POST', body: JSON.stringify(body) }),
  put: <T>(path: string, body: unknown) =>
    request<T>(path, { method: 'PUT', body: JSON.stringify(body) }),
  delete: <T>(path: string) => request<T>(path, { method: 'DELETE' }),
}

export const queryKeys = {
  financialYears: {
    all: () => ['financial-years'] as const,
    detail: (id: string) => ['financial-years', id] as const,
  },
  transactions: {
    list: (filters?: Record<string, unknown>) => ['transactions', filters] as const,
    detail: (id: string) => ['transactions', id] as const,
  },
  accounts: {
    list: () => ['accounts'] as const,
    detail: (id: string) => ['accounts', id] as const,
    ledger: (id: string) => ['accounts', id, 'ledger'] as const,
    openingBalance: (id: number) => ['accounts', id, 'opening-balance'] as const,
  },
  accountGroups: {
    all: () => ['account-groups'] as const,
  },
  reports: {
    trialBalance: (fyId: string) => ['reports', 'trial-balance', fyId] as const,
    profitLoss: (fyId: string) => ['reports', 'profit-loss', fyId] as const,
    balanceSheet: (fyId: string) => ['reports', 'balance-sheet', fyId] as const,
    cashFlow: (fyId: string) => ['reports', 'cash-flow', fyId] as const,
  },
  investments: {
    holdings: (accountId: string) => ['investments', accountId, 'holdings'] as const,
    capitalGains: (accountId: string) => ['investments', accountId, 'capital-gains'] as const,
    portfolio: (accountId: string) => ['investments', accountId, 'portfolio'] as const,
    fds: () => ['investments', 'fds'] as const,
  },
  imports: {
    batch: (batchId: string) => ['imports', batchId] as const,
    rows: (batchId: string) => ['imports', batchId, 'rows'] as const,
  },
  merchantRules: {
    all: () => ['merchant-rules'] as const,
  },
  prices: {
    latest: (accountId: string) => ['prices', 'latest', accountId] as const,
  },
  recurring: {
    schedules: () => ['recurring', 'schedules'] as const,
    dueToday: () => ['recurring', 'due-today'] as const,
  },
  ai: {
    config: () => ['ai', 'config'] as const,
  },
}
