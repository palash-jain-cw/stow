import { request } from '@playwright/test'

export const API_BASE = 'http://localhost:8000'

export interface FY { id: number; start_date: string; end_date: string; status: string }
export interface Account { id: number; name: string; group_id: number; nature: string }
export interface Transaction { id: number; number: string; type: string; date: string; narration: string }
export interface MerchantRule { id: number; pattern: string; account_id: number }

export interface TestState {
  fyId: number
  hdfcId: number
  iciciId: number
  foodId: number
  salaryId: number
  bankGroupId: number
  expGroupId: number
  incGroupId: number
  invGroupId: number
}

export async function resetDB(): Promise<void> {
  const ctx = await request.newContext({ baseURL: API_BASE })
  const res = await ctx.post('/reset')
  if (!res.ok()) throw new Error(`Reset failed: ${res.status()}`)
  await ctx.dispose()
}

export async function setupBaseState(): Promise<TestState> {
  const ctx = await request.newContext({ baseURL: API_BASE })

  const fyRes = await ctx.post('/financial-years', {
    data: { start_date: '2026-04-01', end_date: '2027-03-31' },
  })
  const fy: FY = await fyRes.json()

  const groupsRes = await ctx.get('/account-groups')
  const groups: Array<{ id: number; name: string }> = await groupsRes.json()
  const g = (name: string) => groups.find(x => x.name === name)!.id
  const bankGroupId = g('Bank Accounts')
  const expGroupId = g('Indirect Expenses')
  const incGroupId = g('Indirect Income')
  const invGroupId = g('Investments')

  const mk = async (name: string, groupId: number, extra?: object) => {
    const r = await ctx.post('/accounts', { data: { name, group_id: groupId, ...extra } })
    return (await r.json()) as Account
  }

  const hdfc = await mk('HDFC Savings', bankGroupId)
  const icici = await mk('ICICI Current', bankGroupId)
  const food = await mk('Food & Dining', expGroupId)
  const salary = await mk('Salary', incGroupId)

  // Give HDFC a ₹10,000 opening balance
  await ctx.put(`/accounts/${hdfc.id}/opening-balance`, {
    data: { fy_id: fy.id, amount: 1_000_000 },
  })

  await ctx.dispose()
  return {
    fyId: fy.id,
    hdfcId: hdfc.id,
    iciciId: icici.id,
    foodId: food.id,
    salaryId: salary.id,
    bankGroupId,
    expGroupId,
    incGroupId,
    invGroupId,
  }
}

export async function createTransaction(params: {
  type: string
  date: string
  narration: string
  fyId: number
  entries: Array<{ account_id: number; amount: number }>
  tags?: string[]
}): Promise<Transaction> {
  const ctx = await request.newContext({ baseURL: API_BASE })
  const res = await ctx.post('/transactions', {
    data: {
      type: params.type,
      date: params.date,
      narration: params.narration,
      fy_id: params.fyId,
      entries: params.entries,
      tags: params.tags ?? [],
    },
  })
  const txn: Transaction = await res.json()
  await ctx.dispose()
  return txn
}

export async function createMerchantRule(pattern: string, accountId: number): Promise<MerchantRule> {
  const ctx = await request.newContext({ baseURL: API_BASE })
  const res = await ctx.post('/merchant-rules', { data: { pattern, account_id: accountId } })
  const rule: MerchantRule = await res.json()
  await ctx.dispose()
  return rule
}

export async function createRecurringSchedule(params: {
  templateTransactionId: number
  frequency: string
  firstDueDate: string
  dayOfPeriod?: number
  endDate?: string
}): Promise<{ id: number; next_due_date: string; frequency: string }> {
  const ctx = await request.newContext({ baseURL: API_BASE })
  const res = await ctx.post('/recurring/schedules', {
    data: {
      template_transaction_id: params.templateTransactionId,
      frequency: params.frequency,
      first_due_date: params.firstDueDate,
      day_of_period: params.dayOfPeriod ?? null,
      end_date: params.endDate ?? null,
    },
  })
  const sched = await res.json()
  await ctx.dispose()
  return sched
}

export async function createFD(params: {
  accountId: number
  name: string
  principal: number
  interestRate: number
  startDate: string
  maturityDate: string
  compounding: string
}): Promise<{ id: number; status: string }> {
  const ctx = await request.newContext({ baseURL: API_BASE })
  const res = await ctx.post('/investments/fds', {
    data: {
      account_id: params.accountId,
      name: params.name,
      principal: params.principal,
      interest_rate: params.interestRate,
      start_date: params.startDate,
      maturity_date: params.maturityDate,
      compounding: params.compounding,
    },
  })
  const fd = await res.json()
  await ctx.dispose()
  return fd
}
