import { useEffect, useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { ChevronDown, ChevronRight } from 'lucide-react'
import { api, queryKeys } from '../api/api'
import { refreshAllLivePrices } from '../api/prices'
import { MonoAmount } from '../components/MonoAmount'
import { InvestmentTradeSheet } from '../components/InvestmentTradeSheet'
import { FdSheet } from '../components/FdSheet'
import type { AccountOption } from '../components/investmentHelpers'

// ── Types ─────────────────────────────────────────────────────────────────────

interface AccountOut extends AccountOption {
  balance: number
  price_source_id: string | null
}

interface PortfolioItemOut {
  lot_id: number
  acquisition_date: string
  units: number
  remaining_units: number
  cost_per_unit: number
  cost_basis: number
  current_price_per_unit: number | null
  current_value: number | null
  unrealized_gain: number | null
}

interface FdListItemOut {
  account_id: number
  name: string
  principal: number
  interest_rate: number
  start_date: string
  maturity_date: string
  compounding: string
  status: string
  days_to_maturity: number
  accrued_interest: number
}

// ── Helpers ───────────────────────────────────────────────────────────────────

function rupees(paise: number) {
  return new Intl.NumberFormat('en-IN', {
    style: 'currency',
    currency: 'INR',
    minimumFractionDigits: 0,
    maximumFractionDigits: 0,
  }).format(Math.round(paise) / 100)
}

function formatDate(iso: string) {
  return new Date(iso).toLocaleDateString('en-IN', { day: '2-digit', month: 'short', year: 'numeric' })
}

function ageMonths(isoDate: string) {
  const d = new Date(isoDate)
  const today = new Date()
  return Math.floor((today.getTime() - d.getTime()) / (1000 * 60 * 60 * 24 * 30.44))
}

function ageDays(isoDate: string) {
  const d = new Date(isoDate)
  const today = new Date()
  return Math.floor((today.getTime() - d.getTime()) / (1000 * 60 * 60 * 24))
}

type CgType = 'STCG' | 'LTCG' | 'Mixed'

function cgTypeForLots(lots: PortfolioItemOut[]): CgType {
  if (lots.length === 0) return 'STCG'
  const types = lots.map(l => ageDays(l.acquisition_date) > 365 ? 'LTCG' : 'STCG')
  if (types.every(t => t === 'LTCG')) return 'LTCG'
  if (types.every(t => t === 'STCG')) return 'STCG'
  return 'Mixed'
}

function CgPill({ type }: { type: CgType }) {
  const cls =
    type === 'LTCG' ? 'bg-emerald-100 text-emerald-800' :
    type === 'STCG' ? 'bg-amber-100 text-amber-800' :
                     'bg-zinc-100 text-zinc-600'
  return <span className={`text-[10px] font-medium px-1.5 py-0.5 rounded-full ${cls}`}>{type}</span>
}

function GainDisplay({ paise }: { paise: number | null }) {
  if (paise === null) return <span className="text-zinc-400">—</span>
  const cls = paise >= 0 ? 'text-emerald-600' : 'text-red-600'
  const sign = paise >= 0 ? '+' : '−'
  return <span className={cls}>{sign}{rupees(Math.abs(paise))}</span>
}

function LoadingRows({ cols }: { cols: number }) {
  return (
    <>
      {[...Array(4)].map((_, i) => (
        <tr key={i}>
          {[...Array(cols)].map((_, j) => (
            <td key={j} className="px-3 py-3">
              <div className="h-3 bg-zinc-100 rounded animate-pulse" style={{ width: `${60 + (j * 15) % 40}%` }} />
            </td>
          ))}
        </tr>
      ))}
    </>
  )
}

function NoData({ message }: { message: string }) {
  return <p className="text-center text-zinc-400 py-12 text-sm">{message}</p>
}

function LivePriceHint({ items }: { items: AccountWithPortfolio[] }) {
  const needsSourceId = items.filter(({ account, lots }) => {
    const active = lots.filter(l => l.remaining_units > 0)
    return active.length > 0 && !account.price_source_id
  })
  const needsFetch = items.filter(({ account, lots }) => {
    const active = lots.filter(l => l.remaining_units > 0)
    return (
      active.length > 0 &&
      !!account.price_source_id &&
      active.some(l => l.current_value === null)
    )
  })

  if (needsSourceId.length === 0 && needsFetch.length === 0) return null

  return (
    <div className="mb-4 rounded-xl border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-900">
      {needsSourceId.length > 0 && (
        <p>
          Add a price source ID on{' '}
          {needsSourceId.map(({ account }) => account.name).join(', ')}{' '}
          in Accounts (AMFI scheme code for MFs, NSE ticker for stocks) to see current value.
        </p>
      )}
      {needsFetch.length > 0 && (
        <p className={needsSourceId.length > 0 ? 'mt-2' : undefined}>
          Live price unavailable for{' '}
          {needsFetch.map(({ account }) => account.name).join(', ')}.
          Check the price source ID or try refreshing this page.
        </p>
      )}
    </div>
  )
}

// ── Allocation bar ────────────────────────────────────────────────────────────

interface AllocationBarProps {
  mfBalance: number
  stockBalance: number
  fdBalance: number
}

function AllocationBar({ mfBalance, stockBalance, fdBalance }: AllocationBarProps) {
  const total = mfBalance + stockBalance + fdBalance
  if (total === 0) return null

  const pct = (v: number) => ((v / total) * 100).toFixed(1)

  const segments = [
    { label: 'Equity MF', value: mfBalance, color: 'bg-blue-600', pctColor: 'text-blue-600' },
    { label: 'Stocks', value: stockBalance, color: 'bg-violet-600', pctColor: 'text-violet-600' },
    { label: 'Fixed Deposits', value: fdBalance, color: 'bg-amber-500', pctColor: 'text-amber-600' },
  ].filter(s => s.value > 0)

  return (
    <div className="mb-6">
      <div className="flex items-baseline gap-3 mb-3">
        <span className="text-2xl font-semibold text-zinc-900 font-mono">{rupees(total)}</span>
        <span className="text-sm text-zinc-500">total invested</span>
      </div>
      <div className="flex h-1.5 rounded-full overflow-hidden gap-0.5 mb-3">
        {segments.map(s => (
          <div
            key={s.label}
            className={`${s.color} rounded-full`}
            style={{ width: `${(s.value / total) * 100}%` }}
          />
        ))}
      </div>
      <div className="flex flex-wrap gap-4">
        {segments.map(s => (
          <div key={s.label} className="flex items-center gap-2 text-sm">
            <div className={`w-2 h-2 rounded-full ${s.color}`} />
            <span className="text-zinc-600">{s.label}</span>
            <span className="font-mono text-zinc-900">{rupees(s.value)}</span>
            <span className={`text-xs ${s.pctColor}`}>{pct(s.value)}%</span>
          </div>
        ))}
      </div>
    </div>
  )
}

// ── Holdings table (Equity MF + Stocks) ──────────────────────────────────────

interface AccountWithPortfolio {
  account: AccountOut
  lots: PortfolioItemOut[]
}

interface HoldingsTableProps {
  items: AccountWithPortfolio[]
  isLoading: boolean
  unitLabel: string
  navLabel: string
  onBuy: (account: AccountOut) => void
  onSell: (account: AccountOut, maxUnitsMilli: number) => void
}

function HoldingsTable({ items, isLoading, unitLabel, navLabel, onBuy, onSell }: HoldingsTableProps) {
  const [expanded, setExpanded] = useState<number | null>(null)

  if (!isLoading && items.length === 0) {
    return <NoData message={`No ${unitLabel === 'Units' ? 'Equity MF' : 'Stock'} accounts found.`} />
  }

  const toggleExpand = (id: number) => setExpanded(prev => prev === id ? null : id)

  return (
    <div className="overflow-x-auto">
      <table className="w-full text-sm">
        <thead>
          <tr className="border-b border-zinc-200">
            <th className="text-left px-3 py-2 font-medium text-zinc-500">Fund</th>
            <th className="text-right px-3 py-2 font-medium text-zinc-500">{unitLabel} held</th>
            <th className="text-right px-3 py-2 font-medium text-zinc-500">{navLabel}</th>
            <th className="text-right px-3 py-2 font-medium text-zinc-500">Invested</th>
            <th className="text-right px-3 py-2 font-medium text-zinc-500">Current value</th>
            <th className="text-right px-3 py-2 font-medium text-zinc-500">Unrealized</th>
            <th className="text-center px-3 py-2 font-medium text-zinc-500">CG type</th>
            <th className="text-right px-3 py-2 font-medium text-zinc-500">Actions</th>
            <th className="w-8" />
          </tr>
        </thead>
        <tbody>
          {isLoading && <LoadingRows cols={9} />}
          {items.map(({ account, lots }) => {
            const activeLots = lots.filter(l => l.remaining_units > 0)
            const totalUnits = activeLots.reduce((s, l) => s + l.remaining_units, 0)
            const totalCostBasis = activeLots.reduce((s, l) => s + l.cost_basis, 0)
            const totalCurrentValue = activeLots.every(l => l.current_value !== null)
              ? activeLots.reduce((s, l) => s + (l.current_value ?? 0), 0)
              : null
            const totalUnrealizedGain = activeLots.every(l => l.unrealized_gain !== null)
              ? activeLots.reduce((s, l) => s + (l.unrealized_gain ?? 0), 0)
              : null
            const avgNav = totalUnits > 0 ? Math.round(totalCostBasis / (totalUnits / 1000)) : 0
            const cgType = cgTypeForLots(activeLots)
            const isOpen = expanded === account.id

            return (
              <>
                <tr
                  key={account.id}
                  className={`border-b border-zinc-100 cursor-pointer hover:bg-zinc-50 transition-colors ${isOpen ? 'bg-zinc-50' : ''}`}
                  onClick={() => toggleExpand(account.id)}
                >
                  <td className="px-3 py-3 font-medium text-zinc-900">{account.name}</td>
                  <td className="px-3 py-3 text-right font-mono text-zinc-700">
                    {(totalUnits / 1000).toLocaleString('en-IN', { maximumFractionDigits: 3 })}
                  </td>
                  <td className="px-3 py-3 text-right font-mono text-zinc-700">{rupees(avgNav)}</td>
                  <td className="px-3 py-3 text-right font-mono text-zinc-700">
                    <MonoAmount amount={totalCostBasis} />
                  </td>
                  <td className="px-3 py-3 text-right font-mono text-zinc-700">
                    {totalCurrentValue !== null ? <MonoAmount amount={totalCurrentValue} /> : <span className="text-zinc-400">—</span>}
                  </td>
                  <td className="px-3 py-3 text-right font-mono">
                    <GainDisplay paise={totalUnrealizedGain} />
                  </td>
                  <td className="px-3 py-3 text-center">
                    <CgPill type={cgType} />
                  </td>
                  <td className="px-3 py-3 text-right">
                    <div className="flex justify-end gap-1" onClick={e => e.stopPropagation()}>
                      <button
                        type="button"
                        onClick={() => onBuy(account)}
                        className="text-xs font-medium px-2 py-1 rounded-md border border-zinc-200 text-zinc-600 hover:border-zinc-300 hover:bg-white"
                      >
                        Buy
                      </button>
                      <button
                        type="button"
                        disabled={totalUnits === 0}
                        onClick={() => onSell(account, totalUnits)}
                        className="text-xs font-medium px-2 py-1 rounded-md border border-zinc-200 text-zinc-600 hover:border-zinc-300 hover:bg-white disabled:opacity-40 disabled:cursor-not-allowed"
                      >
                        Sell
                      </button>
                    </div>
                  </td>
                  <td className="px-3 py-3 text-zinc-400">
                    {isOpen ? <ChevronDown size={16} /> : <ChevronRight size={16} />}
                  </td>
                </tr>
                <tr key={`${account.id}-lots`} className="border-b border-zinc-100">
                  <td colSpan={9} className="p-0">
                    <div
                      className="grid transition-all duration-250 ease-in-out"
                      style={{ gridTemplateRows: isOpen ? '1fr' : '0fr' }}
                    >
                      <div className="overflow-hidden">
                        <div className="bg-zinc-50 px-4 py-3">
                          <p className="text-xs font-semibold text-zinc-500 uppercase tracking-wide mb-2">FIFO Lots</p>
                          <table className="w-full text-xs">
                            <thead>
                              <tr className="text-zinc-400">
                                <th className="text-left py-1 pr-4">Lot</th>
                                <th className="text-right pr-4">{unitLabel}</th>
                                <th className="text-right pr-4">Buy {navLabel}</th>
                                <th className="text-right pr-4">Buy date</th>
                                <th className="text-right pr-4">Age</th>
                                <th className="text-right pr-4">Unrealized</th>
                                <th className="text-right">Type</th>
                              </tr>
                            </thead>
                            <tbody>
                              {activeLots.map((lot, idx) => {
                                const lotType: CgType = ageDays(lot.acquisition_date) > 365 ? 'LTCG' : 'STCG'
                                return (
                                  <tr key={lot.lot_id} className="border-t border-zinc-200">
                                    <td className="py-1.5 pr-4 text-zinc-500">#{idx + 1}</td>
                                    <td className="py-1.5 pr-4 text-right font-mono">
                                      {(lot.remaining_units / 1000).toLocaleString('en-IN', { maximumFractionDigits: 3 })}
                                    </td>
                                    <td className="py-1.5 pr-4 text-right font-mono">{rupees(lot.cost_per_unit)}</td>
                                    <td className="py-1.5 pr-4 text-right">{formatDate(lot.acquisition_date)}</td>
                                    <td className="py-1.5 pr-4 text-right">{ageMonths(lot.acquisition_date)} mo</td>
                                    <td className="py-1.5 pr-4 text-right font-mono">
                                      <GainDisplay paise={lot.unrealized_gain} />
                                    </td>
                                    <td className="py-1.5 text-right">
                                      <CgPill type={lotType} />
                                    </td>
                                  </tr>
                                )
                              })}
                            </tbody>
                          </table>
                        </div>
                      </div>
                    </div>
                  </td>
                </tr>
              </>
            )
          })}
          {!isLoading && items.length > 0 && (
            <tr className="border-t-2 border-zinc-300 bg-zinc-50 font-semibold text-sm">
              <td className="px-3 py-2" colSpan={3}>Total</td>
              <td className="px-3 py-2 text-right font-mono">
                <MonoAmount amount={items.reduce((s, { lots }) =>
                  s + lots.filter(l => l.remaining_units > 0).reduce((a, l) => a + l.cost_basis, 0), 0)} />
              </td>
              <td className="px-3 py-2 text-right font-mono">
                {items.every(({ lots }) => lots.filter(l => l.remaining_units > 0).every(l => l.current_value !== null)) ? (
                  <MonoAmount amount={items.reduce((s, { lots }) =>
                    s + lots.filter(l => l.remaining_units > 0).reduce((a, l) => a + (l.current_value ?? 0), 0), 0)} />
                ) : <span className="text-zinc-400">—</span>}
              </td>
              <td className="px-3 py-2 text-right font-mono">
                {items.every(({ lots }) => lots.filter(l => l.remaining_units > 0).every(l => l.unrealized_gain !== null)) ? (
                  <GainDisplay paise={items.reduce((s, { lots }) =>
                    s + lots.filter(l => l.remaining_units > 0).reduce((a, l) => a + (l.unrealized_gain ?? 0), 0), 0)} />
                ) : <span className="text-zinc-400">—</span>}
              </td>
              <td colSpan={3} />
            </tr>
          )}
        </tbody>
      </table>
    </div>
  )
}

// ── Fixed Deposits tab ────────────────────────────────────────────────────────

function FdStatusBadge({ fd }: { fd: FdListItemOut }) {
  if (fd.status === 'matured') {
    return <span className="text-xs font-medium px-2 py-0.5 rounded-full bg-zinc-100 text-zinc-600">Matured</span>
  }
  if (fd.days_to_maturity <= 30) {
    return <span className="text-xs font-medium px-2 py-0.5 rounded-full bg-amber-100 text-amber-800">Matures in {fd.days_to_maturity}d</span>
  }
  return <span className="text-xs font-medium px-2 py-0.5 rounded-full bg-emerald-100 text-emerald-800">Active</span>
}

function FdTab({
  fds,
  isLoading,
  onMature,
}: {
  fds: FdListItemOut[]
  isLoading: boolean
  onMature: (fd: FdListItemOut) => void
}) {
  const [expanded, setExpanded] = useState<number | null>(null)

  if (!isLoading && fds.length === 0) {
    return <NoData message="No Fixed Deposits found." />
  }

  const toggle = (id: number) => setExpanded(prev => prev === id ? null : id)

  return (
    <div className="overflow-x-auto">
      <table className="w-full text-sm">
        <thead>
          <tr className="border-b border-zinc-200">
            <th className="text-left px-3 py-2 font-medium text-zinc-500">Bank / FD</th>
            <th className="text-right px-3 py-2 font-medium text-zinc-500">Principal</th>
            <th className="text-right px-3 py-2 font-medium text-zinc-500">Rate</th>
            <th className="text-right px-3 py-2 font-medium text-zinc-500">Start date</th>
            <th className="text-right px-3 py-2 font-medium text-zinc-500">Maturity date</th>
            <th className="text-right px-3 py-2 font-medium text-zinc-500">Interest accrued</th>
            <th className="text-center px-3 py-2 font-medium text-zinc-500">Status</th>
            <th className="text-right px-3 py-2 font-medium text-zinc-500">Actions</th>
            <th className="w-8" />
          </tr>
        </thead>
        <tbody>
          {isLoading && <LoadingRows cols={9} />}
          {fds.map(fd => {
            const isOpen = expanded === fd.account_id
            const isMaturing = fd.status !== 'matured' && fd.days_to_maturity <= 30

            return (
              <>
                <tr
                  key={fd.account_id}
                  className={`border-b border-zinc-100 cursor-pointer hover:bg-zinc-50 transition-colors ${isMaturing ? 'border-l-2 border-l-amber-400' : ''}`}
                  onClick={() => toggle(fd.account_id)}
                >
                  <td className="px-3 py-3 font-medium text-zinc-900">{fd.name}</td>
                  <td className="px-3 py-3 text-right font-mono"><MonoAmount amount={fd.principal} /></td>
                  <td className="px-3 py-3 text-right font-mono">{(fd.interest_rate / 100).toFixed(2)}%</td>
                  <td className="px-3 py-3 text-right text-zinc-600">{formatDate(fd.start_date)}</td>
                  <td className="px-3 py-3 text-right text-zinc-600">{formatDate(fd.maturity_date)}</td>
                  <td className="px-3 py-3 text-right font-mono"><MonoAmount amount={fd.accrued_interest} /></td>
                  <td className="px-3 py-3 text-center"><FdStatusBadge fd={fd} /></td>
                  <td className="px-3 py-3 text-right">
                    <div onClick={e => e.stopPropagation()}>
                      <button
                        type="button"
                        disabled={fd.status !== 'active'}
                        onClick={() => onMature(fd)}
                        className="text-xs font-medium px-2 py-1 rounded-md border border-zinc-200 text-zinc-600 hover:border-zinc-300 hover:bg-white disabled:opacity-40 disabled:cursor-not-allowed"
                      >
                        Mature
                      </button>
                    </div>
                  </td>
                  <td className="px-3 py-3 text-zinc-400">
                    {isOpen ? <ChevronDown size={16} /> : <ChevronRight size={16} />}
                  </td>
                </tr>
                <tr key={`${fd.account_id}-detail`} className="border-b border-zinc-100">
                  <td colSpan={9} className="p-0">
                    <div
                      className="grid transition-all duration-250 ease-in-out"
                      style={{ gridTemplateRows: isOpen ? '1fr' : '0fr' }}
                    >
                      <div className="overflow-hidden">
                        <div className="bg-zinc-50 px-6 py-3">
                          {(() => {
                            const startDate = new Date(fd.start_date)
                            const maturityDate = new Date(fd.maturity_date)
                            const tenureDays = Math.round((maturityDate.getTime() - startDate.getTime()) / (1000 * 60 * 60 * 24))
                            const maturityAmount = fd.principal + fd.accrued_interest
                            return (
                              <dl className="grid grid-cols-4 gap-4 text-sm">
                                <div>
                                  <dt className="text-zinc-400 text-xs">Tenure</dt>
                                  <dd className="font-medium text-zinc-800">{Math.round(tenureDays / 30)} months ({tenureDays}d)</dd>
                                </div>
                                <div>
                                  <dt className="text-zinc-400 text-xs">Compounding</dt>
                                  <dd className="font-medium text-zinc-800 capitalize">{fd.compounding}</dd>
                                </div>
                                <div>
                                  <dt className="text-zinc-400 text-xs">Maturity amount</dt>
                                  <dd className="font-mono font-medium text-zinc-800"><MonoAmount amount={maturityAmount} /></dd>
                                </div>
                                <div>
                                  <dt className="text-zinc-400 text-xs">Days to maturity</dt>
                                  <dd className="font-medium text-zinc-800">
                                    {fd.status === 'matured' ? 'Matured' : `${fd.days_to_maturity} days`}
                                  </dd>
                                </div>
                              </dl>
                            )
                          })()}
                        </div>
                      </div>
                    </div>
                  </td>
                </tr>
              </>
            )
          })}
        </tbody>
      </table>
    </div>
  )
}

// ── Main component ────────────────────────────────────────────────────────────

const TABS = [
  { id: 'mf', label: 'Equity MF' },
  { id: 'stocks', label: 'Stocks' },
  { id: 'fds', label: 'Fixed Deposits' },
] as const

type TabId = typeof TABS[number]['id']

type TradeSheetState = {
  mode: 'buy' | 'sell'
  subtype: 'equity_mf' | 'stock'
  account?: AccountOut
  maxUnitsMilli?: number
} | null

type FdSheetState = {
  mode: 'open' | 'mature'
  fd?: FdListItemOut
} | null

export default function Portfolio() {
  const [searchParams, setSearchParams] = useSearchParams()
  const tab = (searchParams.get('tab') ?? 'mf') as TabId
  const [tradeSheet, setTradeSheet] = useState<TradeSheetState>(null)
  const [fdSheet, setFdSheet] = useState<FdSheetState>(null)

  const setTab = (t: TabId) => setSearchParams({ tab: t })

  useEffect(() => {
    const action = searchParams.get('action')
    if (!action) return
    if (action === 'buy') {
      setTradeSheet({
        mode: 'buy',
        subtype: tab === 'stocks' ? 'stock' : 'equity_mf',
      })
    } else if (action === 'open-fd') {
      setFdSheet({ mode: 'open' })
    }
    setSearchParams(prev => {
      const next = new URLSearchParams(prev)
      next.delete('action')
      return next
    }, { replace: true })
  }, [searchParams, setSearchParams, tab])

  // All accounts (for allocation bar + per-type filtering)
  const { data: accounts = [] } = useQuery<AccountOut[]>({
    queryKey: queryKeys.accounts.list(),
    queryFn: () => api.get<AccountOut[]>('/accounts'),
  })

  const mfAccounts = accounts.filter(a => a.investment_subtype === 'equity_mf')
  const stockAccounts = accounts.filter(a => a.investment_subtype === 'stock')
  const fdAccounts = accounts.filter(a => a.investment_subtype === 'fd')

  const mfBalance = mfAccounts.reduce((s, a) => s + a.balance, 0)
  const stockBalance = stockAccounts.reduce((s, a) => s + a.balance, 0)
  const fdBalance = fdAccounts.reduce((s, a) => s + a.balance, 0)

  // Portfolio per account — refresh live prices, then load holdings
  const priceableAccountKey = (accs: AccountOut[]) =>
    accs.map(a => `${a.id}:${a.price_source_id ?? ''}`).join(',')

  const { data: mfPortfolios, isLoading: mfLoading } = useQuery<AccountWithPortfolio[]>({
    queryKey: ['portfolio', 'mf', mfAccounts.map(a => a.id), priceableAccountKey(mfAccounts)],
    queryFn: async () => {
      if (mfAccounts.some(a => a.price_source_id)) {
        await refreshAllLivePrices()
      }
      const results = await Promise.all(
        mfAccounts.map(a => api.get<PortfolioItemOut[]>(`/investments/${a.id}/portfolio`))
      )
      return mfAccounts.map((a, i) => ({ account: a, lots: results[i] }))
    },
    enabled: tab === 'mf' && mfAccounts.length > 0,
    staleTime: 5 * 60 * 1000,
  })

  const { data: stockPortfolios, isLoading: stockLoading } = useQuery<AccountWithPortfolio[]>({
    queryKey: ['portfolio', 'stocks', stockAccounts.map(a => a.id), priceableAccountKey(stockAccounts)],
    queryFn: async () => {
      if (stockAccounts.some(a => a.price_source_id)) {
        await refreshAllLivePrices()
      }
      const results = await Promise.all(
        stockAccounts.map(a => api.get<PortfolioItemOut[]>(`/investments/${a.id}/portfolio`))
      )
      return stockAccounts.map((a, i) => ({ account: a, lots: results[i] }))
    },
    enabled: tab === 'stocks' && stockAccounts.length > 0,
    staleTime: 5 * 60 * 1000,
  })

  const { data: fds = [], isLoading: fdsLoading } = useQuery<FdListItemOut[]>({
    queryKey: queryKeys.investments.fds(),
    queryFn: () => api.get<FdListItemOut[]>('/investments/fds'),
    enabled: tab === 'fds',
  })

  const openBuySheet = (subtype: 'equity_mf' | 'stock', account?: AccountOut) => {
    setTradeSheet({ mode: 'buy', subtype, account })
  }

  const openSellSheet = (account: AccountOut, maxUnitsMilli: number, subtype: 'equity_mf' | 'stock') => {
    setTradeSheet({ mode: 'sell', subtype, account, maxUnitsMilli })
  }

  return (
    <div className="max-w-5xl mx-auto px-6 py-6">
      <h1 className="text-2xl font-semibold text-zinc-900 mb-6">Portfolio</h1>

      <AllocationBar mfBalance={mfBalance} stockBalance={stockBalance} fdBalance={fdBalance} />

      {/* Tab strip */}
      <div className="flex gap-6 border-b border-zinc-200 mb-6">
        {TABS.map(t => (
          <button
            key={t.id}
            onClick={() => setTab(t.id)}
            className={`pb-2 text-sm transition-colors border-b-2 -mb-px ${
              tab === t.id
                ? 'border-zinc-900 text-zinc-900 font-medium'
                : 'border-transparent text-zinc-400 hover:text-zinc-600'
            }`}
          >
            {t.label}
          </button>
        ))}
      </div>

      {/* Tab content */}
      {tab === 'mf' && (
        <>
          <div className="flex justify-end mb-4">
            <button
              type="button"
              onClick={() => openBuySheet('equity_mf')}
              className="bg-blue-600 hover:bg-blue-700 text-white text-sm font-medium px-4 py-2 rounded-xl transition-colors"
            >
              Record purchase
            </button>
          </div>
          {mfPortfolios && <LivePriceHint items={mfPortfolios} />}
          <HoldingsTable
            items={mfPortfolios ?? (mfLoading ? [] : mfAccounts.map(a => ({ account: a, lots: [] })))}
            isLoading={mfLoading}
            unitLabel="Units"
            navLabel="Avg NAV"
            onBuy={account => openBuySheet('equity_mf', account)}
            onSell={(account, maxUnitsMilli) => openSellSheet(account, maxUnitsMilli, 'equity_mf')}
          />
        </>
      )}

      {tab === 'stocks' && (
        <>
          <div className="flex justify-end mb-4">
            <button
              type="button"
              onClick={() => openBuySheet('stock')}
              className="bg-blue-600 hover:bg-blue-700 text-white text-sm font-medium px-4 py-2 rounded-xl transition-colors"
            >
              Record purchase
            </button>
          </div>
          {stockPortfolios && <LivePriceHint items={stockPortfolios} />}
          <HoldingsTable
            items={stockPortfolios ?? (stockLoading ? [] : stockAccounts.map(a => ({ account: a, lots: [] })))}
            isLoading={stockLoading}
            unitLabel="Shares"
            navLabel="Avg cost"
            onBuy={account => openBuySheet('stock', account)}
            onSell={(account, maxUnitsMilli) => openSellSheet(account, maxUnitsMilli, 'stock')}
          />
        </>
      )}

      {tab === 'fds' && (
        <>
          <div className="flex justify-end mb-4">
            <button
              type="button"
              onClick={() => setFdSheet({ mode: 'open' })}
              className="bg-blue-600 hover:bg-blue-700 text-white text-sm font-medium px-4 py-2 rounded-xl transition-colors"
            >
              Open fixed deposit
            </button>
          </div>
          <FdTab
            fds={fds}
            isLoading={fdsLoading}
            onMature={fd => setFdSheet({ mode: 'mature', fd })}
          />
        </>
      )}

      <InvestmentTradeSheet
        open={tradeSheet !== null}
        onClose={() => setTradeSheet(null)}
        mode={tradeSheet?.mode ?? 'buy'}
        subtype={tradeSheet?.subtype ?? 'equity_mf'}
        account={tradeSheet?.account}
        maxUnitsMilli={tradeSheet?.maxUnitsMilli}
        onSaved={() => {}}
      />

      <FdSheet
        open={fdSheet !== null}
        onClose={() => setFdSheet(null)}
        mode={fdSheet?.mode ?? 'open'}
        fd={fdSheet?.fd}
        onSaved={() => {}}
      />
    </div>
  )
}
