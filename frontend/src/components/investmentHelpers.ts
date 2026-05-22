/** Convert decimal units (e.g. 12.345) to milliunits for the API. */
export function unitsToMilliunits(units: string): number {
  const n = parseFloat(units)
  if (!Number.isFinite(n) || n <= 0) return 0
  return Math.round(n * 1000)
}

/** Convert rupees per unit (e.g. 810.45) to paise per unit for the API. */
export function rupeesPerUnitToPaise(rupees: string): number {
  const n = parseFloat(rupees)
  if (!Number.isFinite(n) || n <= 0) return 0
  return Math.round(n * 100)
}

/** Convert rupee amount string to paise. */
export function rupeesToPaise(rupees: string): number {
  const n = parseFloat(rupees)
  if (!Number.isFinite(n) || n <= 0) return 0
  return Math.round(n * 100)
}

/** Total cost/proceeds in paise: milliunits × paise_per_unit // 1000 */
export function totalPaise(unitsMilli: number, paisePerUnit: number): number {
  return Math.floor(unitsMilli * paisePerUnit / 1000)
}

export interface AccountOption {
  id: number
  name: string
  group_name: string
  nature: string
  investment_subtype: string | null
  is_archived: boolean
}

/** Bank / cash accounts suitable for funding investments (excludes investment accounts). */
export function bankAccountsForSelect(accounts: AccountOption[]): AccountOption[] {
  return accounts.filter(a => !a.is_archived && !a.investment_subtype)
}

export function investmentAccountsForSelect(
  accounts: AccountOption[],
  subtype: 'equity_mf' | 'stock',
): AccountOption[] {
  return accounts.filter(a => !a.is_archived && a.investment_subtype === subtype)
}

export interface FinancialYearOption {
  id: number
  status: string
}

export function resolveActiveFy(fys: FinancialYearOption[]) {
  return fys.find(fy => fy.status === 'active') ?? fys.find(fy => fy.status === 'open')
}

export const inputCls =
  'w-full px-3.5 py-2.5 text-sm border border-zinc-200 rounded-xl focus:outline-none focus:ring-2 focus:ring-blue-500 bg-white transition'

export function formatRupees(paise: number): string {
  return new Intl.NumberFormat('en-IN', {
    style: 'currency',
    currency: 'INR',
    minimumFractionDigits: 0,
    maximumFractionDigits: 2,
  }).format(paise / 100)
}
