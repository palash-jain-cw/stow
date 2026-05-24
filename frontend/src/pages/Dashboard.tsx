import { useState } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { useNavigate, Link } from 'react-router-dom'
import { ChevronDown, Plus, Bell, Clock, Repeat, Receipt } from 'lucide-react'
import { api, queryKeys } from '../api/api'
import { refreshAllLivePrices } from '../api/prices'
import { MonoAmount } from '../components/MonoAmount'
import { TxnBadge, type TxnType } from '../components/TxnBadge'
import { EmptyState } from '../components/EmptyState'
import { TransactionEntrySheet } from '../components/TransactionEntrySheet'
import { txnDisplayFromEntries } from '../components/txnDisplay'

// ── Types ──────────────────────────────────────────────────────────────────

interface FinancialYear {
  id: number
  start_date: string
  end_date: string
  status: string
  net_profit: number | null
}

interface AccountOut {
  id: number
  name: string
  group_id: number
  group_name: string
  nature: string
  is_archived: boolean
  balance: number
  investment_subtype?: string | null
  price_source_id?: string | null
}

interface PortfolioItemOut {
  remaining_units: number
  current_value: number | null
  cost_basis: number
}

interface EntryOut {
  id: number
  account_id: number
  account_name: string
  amount: number
}

interface TransactionOut {
  id: number
  number: string
  type: string
  date: string
  narration: string
  fy_id: number
  entries: EntryOut[]
}

interface FdListItemOut {
  account_id: number
  name: string
  principal: number
  interest_rate: number
  maturity_date: string
  days_to_maturity: number
  status: string
}

interface QueueItemOut {
  id: number
  schedule_id: number
  due_date: string
  status: string
  posted_transaction_id: number | null
}

// ── Helpers ────────────────────────────────────────────────────────────────

function getGreeting(): string {
  const h = new Date().getHours()
  if (h < 12) return 'Good morning'
  if (h < 17) return 'Good afternoon'
  return 'Good evening'
}

function fyLabel(fy: FinancialYear): string {
  const start = new Date(fy.start_date).getFullYear()
  const end = new Date(fy.end_date).getFullYear()
  return `FY ${start}–${String(end).slice(2)}`
}

function formatDate(iso: string): string {
  return new Date(iso).toLocaleDateString('en-IN', { day: 'numeric', month: 'short' })
}

function formatFullDate(iso: string): string {
  return new Date(iso).toLocaleDateString('en-IN', { weekday: 'long', day: 'numeric', month: 'long' })
}

function computeNetWorth(accounts: AccountOut[]): number {
  return accounts
    .filter(a => a.nature === 'asset' || a.nature === 'liability')
    .reduce((sum, a) => sum + a.balance, 0)
}

function applyInvestmentMarketValues(
  accounts: AccountOut[],
  portfolioById: Record<number, PortfolioItemOut[]>,
): AccountOut[] {
  return accounts.map(account => {
    const subtype = account.investment_subtype
    if (subtype !== 'equity_mf' && subtype !== 'stock') return account
    const lots = (portfolioById[account.id] ?? []).filter(l => l.remaining_units > 0)
    if (lots.length === 0) return account
    const hasLive = lots.every(l => l.current_value !== null)
    const balance = hasLive
      ? lots.reduce((sum, l) => sum + (l.current_value ?? 0), 0)
      : lots.reduce((sum, l) => sum + l.cost_basis, 0)
    return { ...account, balance }
  })
}

function computeCash(accounts: AccountOut[]): { amount: number; count: number } {
  const bankAccounts = accounts.filter(
    a => a.group_name === 'Bank Accounts' || a.group_name === 'Cash-in-Hand'
  )
  return {
    amount: bankAccounts.reduce((sum, a) => sum + a.balance, 0),
    count: bankAccounts.length,
  }
}

function computeGstNet(accounts: AccountOut[]): number {
  const output = accounts
    .filter(a => a.name.toLowerCase().includes('output'))
    .reduce((sum, a) => sum - a.balance, 0) // Cr balance is negative → negate
  const input = accounts
    .filter(a => a.name.toLowerCase().includes('input'))
    .reduce((sum, a) => sum + a.balance, 0)
  return output - input
}

// ── Zone header button ─────────────────────────────────────────────────────

function ZoneToggle({
  icon,
  iconBg,
  iconColor,
  label,
  badge,
  meta,
  open,
  onToggle,
}: {
  icon: React.ReactNode
  iconBg: string
  iconColor: string
  label: string
  badge?: number
  meta?: string
  open: boolean
  onToggle: () => void
}) {
  return (
    <button
      onClick={onToggle}
      className="w-full flex items-center justify-between px-5 py-4 text-left hover:bg-zinc-50 transition-colors"
    >
      <div className="flex items-center gap-3">
        <div className={`w-8 h-8 rounded-full ${iconBg} flex items-center justify-center shrink-0`}>
          <span className={iconColor}>{icon}</span>
        </div>
        <div className="flex items-center gap-2">
          <span className="text-sm font-medium text-zinc-800">{label}</span>
          {badge !== undefined && badge > 0 && (
            <span className="text-xs font-semibold bg-amber-100 text-amber-700 px-1.5 py-0.5 rounded-full">
              {badge}
            </span>
          )}
          {meta && <span className="text-xs text-zinc-400">{meta}</span>}
        </div>
      </div>
      <ChevronDown
        className={`w-4 h-4 text-zinc-400 transition-transform duration-250 ${open ? 'rotate-180' : ''}`}
      />
    </button>
  )
}

// ── Zone 1: Entry ──────────────────────────────────────────────────────────

function EntryZone({ onManual }: { onManual: () => void }) {
  return (
    <div className="bg-white rounded-2xl border border-zinc-200 shadow-sm overflow-hidden">
      <div className="px-5 py-4 cursor-pointer" onClick={onManual}>
        <div className="flex items-center gap-3">
          <div className="w-8 h-8 rounded-full bg-blue-50 flex items-center justify-center shrink-0">
            <Plus className="w-4 h-4 text-blue-600" />
          </div>
          <span className="text-zinc-400 text-sm">New transaction…</span>
        </div>
      </div>
      <div className="px-5 pb-4">
        <Link
          to="/portfolio?tab=mf&action=buy"
          className="text-sm text-zinc-500 hover:text-zinc-800 transition-colors"
          onClick={e => e.stopPropagation()}
        >
          Or record an investment →
        </Link>
      </div>
    </div>
  )
}

// ── Zone 2: Needs attention ────────────────────────────────────────────────

function AttentionZone({
  open,
  onToggle,
  fds,
  recurring,
  gstNet,
  onRecordGst,
}: {
  open: boolean
  onToggle: () => void
  fds: FdListItemOut[]
  recurring: QueueItemOut[]
  gstNet: number
  onRecordGst: () => void
}) {
  const navigate = useNavigate()
  const total = fds.length + recurring.length + (gstNet > 0 ? 1 : 0)

  return (
    <div className="bg-white rounded-2xl border border-zinc-200 shadow-sm overflow-hidden">
      <ZoneToggle
        icon={<Bell className="w-4 h-4" />}
        iconBg="bg-amber-50"
        iconColor="text-amber-500"
        label="Needs attention"
        badge={total}
        open={open}
        onToggle={onToggle}
      />
      <div
        className="grid transition-all duration-300 ease-in-out"
        style={{ gridTemplateRows: open ? '1fr' : '0fr' }}
      >
        <div className="overflow-hidden">
          {total === 0 ? (
            <p className="px-5 pb-4 text-sm text-zinc-400">All clear — nothing needs your attention.</p>
          ) : (
            <div className="px-5 pb-4 space-y-2">
              {fds.map(fd => (
                <div
                  key={fd.account_id}
                  className="flex items-center justify-between p-3.5 rounded-xl bg-amber-50 border border-amber-100"
                >
                  <div className="flex items-center gap-3">
                    <Clock className="w-4 h-4 text-amber-500 shrink-0" />
                    <div>
                      <p className="text-sm font-medium text-amber-900">
                        {fd.name} matures in {fd.days_to_maturity} day{fd.days_to_maturity !== 1 ? 's' : ''}
                      </p>
                      <p className="text-xs text-amber-600 font-mono mt-0.5">
                        <MonoAmount amount={fd.principal} colored={false} className="text-amber-600" />
                        {' · due '}{formatDate(fd.maturity_date)}
                      </p>
                    </div>
                  </div>
                  <button
                    onClick={() => navigate('/portfolio')}
                    className="text-xs text-amber-700 font-medium hover:text-amber-900 whitespace-nowrap"
                  >
                    View →
                  </button>
                </div>
              ))}

              {recurring.map(item => (
                <div
                  key={item.id}
                  className="flex items-center justify-between p-3.5 rounded-xl bg-blue-50 border border-blue-100"
                >
                  <div className="flex items-center gap-3">
                    <Repeat className="w-4 h-4 text-blue-500 shrink-0" />
                    <div>
                      <p className="text-sm font-medium text-blue-900">Recurring transaction due today</p>
                      <p className="text-xs text-blue-500 mt-0.5">Due {formatDate(item.due_date)}</p>
                    </div>
                  </div>
                  <button
                    onClick={() => navigate('/transactions')}
                    className="text-xs text-blue-700 font-medium hover:text-blue-900 whitespace-nowrap"
                  >
                    Review →
                  </button>
                </div>
              ))}

              {gstNet > 0 && (
                <div className="flex items-center justify-between p-3.5 rounded-xl bg-violet-50 border border-violet-100">
                  <div className="flex items-center gap-3">
                    <Receipt className="w-4 h-4 text-violet-500 shrink-0" />
                    <div>
                      <p className="text-sm font-medium text-violet-900">GST net payable</p>
                      <p className="text-xs text-violet-500 font-mono mt-0.5">
                        <MonoAmount amount={gstNet} colored={false} className="text-violet-600" />
                      </p>
                    </div>
                  </div>
                  <button
                    onClick={onRecordGst}
                    className="text-xs text-violet-700 font-medium hover:text-violet-900 whitespace-nowrap"
                  >
                    Record it →
                  </button>
                </div>
              )}
            </div>
          )}
        </div>
      </div>
    </div>
  )
}

// ── Zone 3: Recent activity ────────────────────────────────────────────────

function RecentZone({
  open,
  onToggle,
  transactions,
}: {
  open: boolean
  onToggle: () => void
  transactions: TransactionOut[]
}) {
  const navigate = useNavigate()
  const latest = transactions[0]

  const meta = latest
    ? `last added ${formatDate(latest.date)} · ${transactions.length} total`
    : undefined

  return (
    <div className="bg-white rounded-2xl border border-zinc-200 shadow-sm overflow-hidden">
      <ZoneToggle
        icon={<Clock className="w-4 h-4" />}
        iconBg="bg-zinc-100"
        iconColor="text-zinc-500"
        label="Recent activity"
        meta={meta}
        open={open}
        onToggle={onToggle}
      />
      <div
        className="grid transition-all duration-300 ease-in-out"
        style={{ gridTemplateRows: open ? '1fr' : '0fr' }}
      >
        <div className="overflow-hidden">
          {transactions.length === 0 ? (
            <div className="px-5 pb-6">
              <EmptyState
                icon={Clock}
                heading="Your ledger is patiently waiting."
                subtext="Add your first transaction to see it here."
              />
            </div>
          ) : (
            <>
              <div className="divide-y divide-zinc-50">
                {transactions.slice(0, 10).map(txn => {
                  const { amount: displayAmt, colored } = txnDisplayFromEntries(txn.type, txn.entries)
                  return (
                    <div
                      key={txn.id}
                      onClick={() => navigate('/transactions')}
                      className="flex items-center justify-between px-5 py-3 hover:bg-zinc-50 cursor-pointer transition-colors"
                    >
                      <div className="flex items-center gap-3 min-w-0">
                        <span className="text-xs text-zinc-400 w-12 shrink-0">{formatDate(txn.date)}</span>
                        <div className="min-w-0">
                          <p className="text-sm text-zinc-800 truncate">{txn.narration}</p>
                          <p className="text-xs text-zinc-400 truncate">
                            {txn.entries.find((e: EntryOut) => e.amount > 0)?.account_name ?? txn.entries[0]?.account_name ?? '—'}
                          </p>
                        </div>
                      </div>
                      <div className="flex items-center gap-3 shrink-0 ml-3">
                        <TxnBadge type={txn.type as TxnType} />
                        <MonoAmount
                          amount={displayAmt}
                          colored={colored}
                          className="text-sm w-24 text-right"
                        />
                      </div>
                    </div>
                  )
                })}
              </div>
              <div className="px-5 py-3 border-t border-zinc-100">
                <button
                  onClick={() => navigate('/transactions')}
                  className="text-xs text-blue-600 hover:text-blue-700"
                >
                  See all transactions →
                </button>
              </div>
            </>
          )}
        </div>
      </div>
    </div>
  )
}


// ── Dashboard ──────────────────────────────────────────────────────────────

export default function Dashboard() {
  const qc = useQueryClient()
  const [openZone, setOpenZone] = useState<'attention' | 'recent' | null>(null)
  const [sheetOpen, setSheetOpen] = useState(false)

  const toggle = (zone: 'attention' | 'recent') =>
    setOpenZone(prev => (prev === zone ? null : zone))

  // Queries
  const { data: fys = [] } = useQuery({
    queryKey: queryKeys.financialYears.all(),
    queryFn: () => api.get<FinancialYear[]>('/financial-years'),
  })
  const activeFy = fys.find(fy => fy.status === 'active')

  const { data: positionAccounts = [] } = useQuery({
    queryKey: queryKeys.accounts.list('position'),
    queryFn: () => api.get<AccountOut[]>('/accounts?scope=position'),
    staleTime: 30_000,
  })

  const investmentAccounts = positionAccounts.filter(
    a => a.investment_subtype === 'equity_mf' || a.investment_subtype === 'stock',
  )

  const { data: portfolioById = {} } = useQuery({
    queryKey: ['dashboard', 'portfolios', investmentAccounts.map(a => a.id)],
    queryFn: async () => {
      if (investmentAccounts.some(a => a.price_source_id)) {
        await refreshAllLivePrices()
      }
      const pairs = await Promise.all(
        investmentAccounts.map(async account => {
          const lots = await api.get<PortfolioItemOut[]>(`/investments/${account.id}/portfolio`)
          return [account.id, lots] as const
        }),
      )
      return Object.fromEntries(pairs) as Record<number, PortfolioItemOut[]>
    },
    enabled: investmentAccounts.length > 0,
    staleTime: 30_000,
  })

  const netWorthAccounts = applyInvestmentMarketValues(positionAccounts, portfolioById)

  const { data: transactions = [] } = useQuery({
    queryKey: queryKeys.transactions.list(),
    queryFn: () => api.get<TransactionOut[]>('/transactions'),
  })

  const { data: recurringDue = [] } = useQuery({
    queryKey: queryKeys.recurring.dueToday(),
    queryFn: () => api.get<QueueItemOut[]>('/recurring/due-today'),
  })

  const { data: fdsMaturing = [] } = useQuery({
    queryKey: ['investments', 'fds', 'maturing'],
    queryFn: () => api.get<FdListItemOut[]>('/investments/fds/maturing-soon?days=30'),
  })

  // Computed
  const netWorth = computeNetWorth(netWorthAccounts)
  const { amount: cashAmount, count: bankCount } = computeCash(netWorthAccounts)
  const gstNet = computeGstNet(netWorthAccounts)

  const recentTxns = [...transactions]
    .sort((a, b) => b.date.localeCompare(a.date))

  return (
    <div className="max-w-2xl mx-auto px-6 py-10 space-y-3">
      {/* Header */}
      <div className="flex items-center justify-between mb-8">
        <div>
          <h1 className="text-xl font-semibold text-zinc-900">{getGreeting()}</h1>
          <p className="text-sm text-zinc-400 mt-0.5">
            {formatFullDate(new Date().toISOString())}
            {activeFy && (
              <>
                {' · '}
                <span className="font-mono text-xs bg-blue-50 text-blue-600 px-1.5 py-0.5 rounded">
                  {fyLabel(activeFy)}
                </span>
              </>
            )}
          </p>
        </div>
      </div>

      {/* Zone 1 — New transaction */}
      <EntryZone onManual={() => setSheetOpen(true)} />

      {/* Zone 2 — Needs attention */}
      <AttentionZone
        open={openZone === 'attention'}
        onToggle={() => toggle('attention')}
        fds={fdsMaturing}
        recurring={recurringDue}
        gstNet={gstNet}
        onRecordGst={() => setOpenZone('entry')}
      />

      {/* Zone 3 — Recent activity */}
      <RecentZone
        open={openZone === 'recent'}
        onToggle={() => toggle('recent')}
        transactions={recentTxns}
      />

      {/* Footer */}
      <div className="flex items-center justify-between px-2 pt-4">
        <div>
          <p className="text-xs text-zinc-400">Net worth</p>
          <MonoAmount amount={netWorth} colored={false} className="text-lg font-bold text-zinc-900" />
          <p className="text-[10px] text-zinc-400 mt-0.5">All-time position · investments at market value</p>
        </div>
        <div className="text-right">
          <p className="text-xs text-zinc-400">
            Cash across {bankCount} account{bankCount !== 1 ? 's' : ''}
          </p>
          <MonoAmount amount={cashAmount} colored={false} className="text-lg font-bold text-zinc-900" />
        </div>
      </div>

      {/* Transaction entry sheet */}
      <TransactionEntrySheet
        open={sheetOpen}
        onClose={() => setSheetOpen(false)}
        onSaved={() => {
          qc.invalidateQueries({ queryKey: queryKeys.transactions.list() })
          qc.invalidateQueries({ queryKey: queryKeys.accounts.list() })
          qc.invalidateQueries({ queryKey: queryKeys.accounts.list('position') })
          qc.invalidateQueries({ queryKey: ['dashboard', 'portfolios'] })
        }}
      />
    </div>
  )
}
