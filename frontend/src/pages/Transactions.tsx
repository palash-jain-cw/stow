import { useState, useMemo, useRef, useEffect } from 'react'
import { useSearchParams } from 'react-router-dom'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import {
  Plus,
  Search,
  SlidersHorizontal,
  ChevronDown,
  ChevronRight,
  Trash2,
  Pencil,
  ChevronUp,
  Clock,
  Receipt,
} from 'lucide-react'
import { api, queryKeys } from '../api/api'
import { MonoAmount } from '../components/MonoAmount'
import { TxnBadge } from '../components/TxnBadge'
import { EmptyState } from '../components/EmptyState'
import { TransactionEntrySheet } from '../components/TransactionEntrySheet'

// ── Types ──────────────────────────────────────────────────────────────────

interface EntryOut {
  id: number | null
  account_id: number
  account_name: string
  amount: number
}

interface TransactionOut {
  id: number
  number: string
  type: string
  date: string
  entry_date: string
  narration: string
  fy_id: number
  tags: string[] | null
  attachment_path: string | null
  entries: EntryOut[]
}

interface AuditLogEntry {
  id: number
  transaction_id: number
  edited_at: string
  snapshot: Record<string, unknown>
}

type PeriodKey = 'today' | 'week' | 'month' | 'lastmonth' | 'fy' | 'all'

const TXN_TYPES = ['payment', 'receipt', 'journal', 'contra'] as const

// ── Helpers ────────────────────────────────────────────────────────────────

function isoDate(d: Date) {
  return d.toISOString().slice(0, 10)
}

function startOf(period: PeriodKey): string | null {
  const now = new Date()
  if (period === 'today') return isoDate(now)
  if (period === 'week') {
    const d = new Date(now)
    d.setDate(d.getDate() - d.getDay())
    return isoDate(d)
  }
  if (period === 'month') return isoDate(new Date(now.getFullYear(), now.getMonth(), 1))
  if (period === 'lastmonth') return isoDate(new Date(now.getFullYear(), now.getMonth() - 1, 1))
  if (period === 'fy') {
    const fyStart = now.getMonth() >= 3
      ? new Date(now.getFullYear(), 3, 1)
      : new Date(now.getFullYear() - 1, 3, 1)
    return isoDate(fyStart)
  }
  return null
}

function endOf(period: PeriodKey): string | null {
  const now = new Date()
  if (period === 'lastmonth') {
    return isoDate(new Date(now.getFullYear(), now.getMonth(), 0))
  }
  return null
}

function formatGroupDate(dateStr: string): string {
  const d = new Date(dateStr + 'T00:00:00')
  return d.toLocaleDateString('en-IN', { day: 'numeric', month: 'long', year: 'numeric' })
}

function formatAuditTime(s: string): string {
  return new Date(s).toLocaleString('en-IN', {
    day: 'numeric', month: 'short', year: 'numeric',
    hour: '2-digit', minute: '2-digit',
  })
}

// Primary display amount for a transaction row: the largest absolute debit (positive)
function primaryAmount(txn: TransactionOut): number {
  const debits = txn.entries.filter(e => e.amount > 0)
  if (!debits.length) return Math.abs(txn.entries[0]?.amount ?? 0)
  return Math.max(...debits.map(e => e.amount))
}

// Primary account name: the debit (To) account
function primaryAccount(txn: TransactionOut): string {
  const debit = txn.entries.find(e => e.amount > 0)
  return debit?.account_name ?? txn.entries[0]?.account_name ?? '—'
}

// ── Audit log ─────────────────────────────────────────────────────────────

type Snap = Record<string, unknown>

function snapAmount(snap: Snap): number {
  const entries = snap.entries as Array<{ amount: number }> | undefined
  return entries?.reduce((s, e) => s + Math.max(0, e.amount), 0) ?? 0
}

function diffSnaps(before: Snap, after: Snap | TransactionOut): string[] {
  const changes: string[] = []
  const a = after as Snap
  if (before.narration !== a.narration)
    changes.push(`Narration: "${before.narration}" → "${a.narration}"`)
  if (before.date !== a.date)
    changes.push(`Date: ${before.date} → ${a.date}`)
  const bAmt = snapAmount(before)
  const aAmt = snapAmount(a)
  if (bAmt !== aAmt)
    changes.push(`Amount: ₹${(bAmt / 100).toLocaleString('en-IN')} → ₹${(aAmt / 100).toLocaleString('en-IN')}`)
  if (JSON.stringify(before.tags) !== JSON.stringify(a.tags))
    changes.push(`Tags: ${JSON.stringify(before.tags) ?? 'none'} → ${JSON.stringify(a.tags) ?? 'none'}`)
  return changes
}

function AuditLog({ txnId, txn }: { txnId: number; txn: TransactionOut }) {
  const [open, setOpen] = useState(false)
  const { data: log, isLoading } = useQuery({
    queryKey: ['transactions', txnId, 'audit-log'],
    queryFn: () => api.get<AuditLogEntry[]>(`/transactions/${txnId}/audit-log`),
    enabled: open,
  })

  if (!open) {
    return (
      <button
        onClick={() => setOpen(true)}
        className="flex items-center gap-1.5 text-xs text-zinc-400 hover:text-zinc-600 transition-colors"
      >
        <Clock className="w-3.5 h-3.5" /> View edit history
      </button>
    )
  }

  return (
    <div>
      <button
        onClick={() => setOpen(false)}
        className="flex items-center gap-1.5 text-xs text-zinc-400 hover:text-zinc-600 transition-colors mb-2"
      >
        <Clock className="w-3.5 h-3.5" /> Hide edit history
      </button>
      {isLoading && <p className="text-xs text-zinc-400">Loading…</p>}
      {log && log.length === 0 && (
        <p className="text-xs text-zinc-400">No edits recorded.</p>
      )}
      {log && log.length > 0 && (
        <div className="space-y-2">
          {log.map((entry, i) => {
            const afterSnap: Snap | TransactionOut = log[i + 1] ? log[i + 1].snapshot : txn
            const changes = diffSnaps(entry.snapshot, afterSnap)
            return (
              <div key={entry.id} className="text-xs text-zinc-400">
                <span>Edited {formatAuditTime(entry.edited_at)}</span>
                {changes.length > 0 && (
                  <ul className="mt-1 ml-3 space-y-0.5 text-zinc-500">
                    {changes.map((c, j) => <li key={j}>· {c}</li>)}
                  </ul>
                )}
              </div>
            )
          })}
        </div>
      )}
    </div>
  )
}

// ── Expanded row panel ────────────────────────────────────────────────────

function ExpandedPanel({
  txn,
  onEdit,
  onDelete,
}: {
  txn: TransactionOut
  onEdit: () => void
  onDelete: () => void
}) {
  return (
    <div className="px-4 pb-4 pt-2 space-y-4">
      {/* Entries table */}
      <div className="rounded-xl border border-zinc-100 overflow-hidden">
        <table className="w-full text-sm">
          <thead className="bg-zinc-50 border-b border-zinc-100">
            <tr>
              <th className="text-left px-3 py-2 text-xs font-medium text-zinc-400">Account</th>
              <th className="text-right px-3 py-2 text-xs font-medium text-zinc-400">Dr</th>
              <th className="text-right px-3 py-2 text-xs font-medium text-zinc-400">Cr</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-zinc-50">
            {txn.entries.map((e, i) => (
              <tr key={i}>
                <td className="px-3 py-2 text-xs text-zinc-700">{e.account_name}</td>
                <td className="px-3 py-2 text-right">
                  {e.amount > 0 ? <MonoAmount amount={e.amount} colored={false} className="text-xs" /> : <span className="text-xs text-zinc-300">—</span>}
                </td>
                <td className="px-3 py-2 text-right">
                  {e.amount < 0 ? <MonoAmount amount={Math.abs(e.amount)} colored={false} className="text-xs" /> : <span className="text-xs text-zinc-300">—</span>}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {/* Tags + number */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2 flex-wrap">
          <span className="text-xs font-mono text-zinc-400">{txn.number}</span>
          {txn.tags?.map(tag => (
            <span key={tag} className="text-xs bg-zinc-100 text-zinc-600 px-2 py-0.5 rounded-full">{tag}</span>
          ))}
        </div>
        <div className="flex items-center gap-2">
          <button
            onClick={onEdit}
            className="flex items-center gap-1.5 text-xs text-zinc-500 hover:text-zinc-700 border border-zinc-200 hover:border-zinc-300 px-2.5 py-1.5 rounded-lg transition-colors"
          >
            <Pencil className="w-3.5 h-3.5" /> Edit
          </button>
          <button
            onClick={onDelete}
            className="flex items-center gap-1.5 text-xs text-red-500 hover:text-red-700 border border-red-100 hover:border-red-200 px-2.5 py-1.5 rounded-lg transition-colors"
          >
            <Trash2 className="w-3.5 h-3.5" /> Delete
          </button>
        </div>
      </div>

      <AuditLog txnId={txn.id} txn={txn} />
    </div>
  )
}

// ── Transaction row ───────────────────────────────────────────────────────

function TxnRow({
  txn,
  expanded,
  onToggle,
  onEdit,
  onDelete,
}: {
  txn: TransactionOut
  expanded: boolean
  onToggle: () => void
  onEdit: () => void
  onDelete: () => void
}) {
  const amount = primaryAmount(txn)
  const account = primaryAccount(txn)

  return (
    <div className="border border-zinc-100 rounded-xl overflow-hidden bg-white">
      <button
        onClick={onToggle}
        className="w-full flex items-center gap-3 px-4 py-3 hover:bg-zinc-50 transition-colors text-left"
      >
        <TxnBadge type={txn.type as 'payment' | 'receipt' | 'journal' | 'contra'} />
        <div className="flex-1 min-w-0">
          <p className="text-sm font-medium text-zinc-800 truncate">{txn.narration}</p>
          <p className="text-xs text-zinc-400 mt-0.5 truncate">{account}</p>
        </div>
        <MonoAmount amount={amount} colored className="text-sm shrink-0" />
        {expanded
          ? <ChevronUp className="w-4 h-4 text-zinc-300 shrink-0" />
          : <ChevronRight className="w-4 h-4 text-zinc-300 shrink-0" />
        }
      </button>

      {/* CSS grid expand */}
      <div
        className="grid transition-all duration-250 ease-in-out"
        style={{ gridTemplateRows: expanded ? '1fr' : '0fr' }}
      >
        <div className="overflow-hidden">
          <div className="border-t border-zinc-100">
            <ExpandedPanel txn={txn} onEdit={onEdit} onDelete={onDelete} />
          </div>
        </div>
      </div>
    </div>
  )
}

// ── Filter bar ────────────────────────────────────────────────────────────

const PERIOD_PILLS: { key: PeriodKey; label: string }[] = [
  { key: 'today', label: 'Today' },
  { key: 'week', label: 'This week' },
  { key: 'month', label: 'This month' },
  { key: 'lastmonth', label: 'Last month' },
  { key: 'fy', label: 'This FY' },
  { key: 'all', label: 'All time' },
]

function FilterBar({
  search,
  onSearch,
  period,
  onPeriod,
  activeTypes,
  onTypes,
  hasFilters,
  onClear,
}: {
  search: string
  onSearch: (s: string) => void
  period: PeriodKey
  onPeriod: (p: PeriodKey) => void
  activeTypes: string[]
  onTypes: (t: string[]) => void
  hasFilters: boolean
  onClear: () => void
}) {
  const [panelOpen, setPanelOpen] = useState(false)
  const ref = useRef<HTMLDivElement>(null)

  useEffect(() => {
    function handler(e: MouseEvent) {
      if (ref.current && !ref.current.contains(e.target as Node)) setPanelOpen(false)
    }
    document.addEventListener('mousedown', handler)
    return () => document.removeEventListener('mousedown', handler)
  }, [])

  const toggleType = (t: string) =>
    onTypes(activeTypes.includes(t) ? activeTypes.filter(x => x !== t) : [...activeTypes, t])

  return (
    <div className="space-y-3">
      <div className="flex items-center gap-3 flex-wrap">
        {/* Search */}
        <div className="relative flex-1 min-w-48">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-zinc-400" />
          <input
            value={search}
            onChange={e => onSearch(e.target.value)}
            placeholder="Search transactions…"
            className="w-full pl-9 pr-4 py-2 text-sm border border-zinc-200 rounded-xl focus:outline-none focus:ring-2 focus:ring-blue-500 bg-white"
          />
        </div>

        {/* Period pills */}
        <div className="flex gap-1.5 flex-wrap">
          {PERIOD_PILLS.map(p => (
            <button
              key={p.key}
              onClick={() => onPeriod(p.key)}
              className={`text-xs px-3 py-1.5 rounded-lg border transition-all ${
                period === p.key
                  ? 'bg-zinc-900 text-white border-zinc-900'
                  : 'border-zinc-200 text-zinc-500 hover:border-zinc-300'
              }`}
            >
              {p.label}
            </button>
          ))}
        </div>

        {/* Clear all filters */}
        {hasFilters && (
          <button
            onClick={onClear}
            className="text-xs px-3 py-1.5 rounded-lg border border-zinc-200 text-zinc-500 hover:border-zinc-300 hover:text-zinc-700 transition-all"
          >
            Clear all
          </button>
        )}

        {/* Filters button */}
        <div ref={ref} className="relative">
          <button
            onClick={() => setPanelOpen(o => !o)}
            className={`flex items-center gap-1.5 text-xs px-3 py-1.5 rounded-lg border transition-all ${
              activeTypes.length > 0
                ? 'bg-blue-50 text-blue-700 border-blue-200'
                : 'border-zinc-200 text-zinc-500 hover:border-zinc-300'
            }`}
          >
            <SlidersHorizontal className="w-3.5 h-3.5" />
            Filters
            {activeTypes.length > 0 && (
              <span className="bg-blue-600 text-white text-xs rounded-full w-4 h-4 flex items-center justify-center font-medium">
                {activeTypes.length}
              </span>
            )}
            <ChevronDown className={`w-3.5 h-3.5 transition-transform ${panelOpen ? 'rotate-180' : ''}`} />
          </button>

          {panelOpen && (
            <div className="absolute right-0 top-full mt-1.5 bg-white border border-zinc-200 rounded-xl shadow-lg z-10 p-3 min-w-44">
              <p className="text-xs font-semibold text-zinc-400 uppercase tracking-wide mb-2">Type</p>
              <div className="space-y-1.5">
                {TXN_TYPES.map(t => (
                  <label key={t} className="flex items-center gap-2 text-sm cursor-pointer">
                    <input
                      type="checkbox"
                      checked={activeTypes.includes(t)}
                      onChange={() => toggleType(t)}
                      className="rounded border-zinc-300"
                    />
                    <span className="capitalize text-zinc-700">{t}</span>
                  </label>
                ))}
              </div>
              {activeTypes.length > 0 && (
                <button
                  onClick={() => onTypes([])}
                  className="mt-2 text-xs text-zinc-400 hover:text-zinc-600 transition-colors"
                >
                  Clear filters
                </button>
              )}
            </div>
          )}
        </div>
      </div>
    </div>
  )
}

// ── Delete confirmation ───────────────────────────────────────────────────

function DeleteConfirm({
  txn,
  onCancel,
  onConfirm,
  loading,
}: {
  txn: TransactionOut
  onCancel: () => void
  onConfirm: () => void
  loading: boolean
}) {
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40">
      <div className="bg-white rounded-2xl shadow-xl p-6 max-w-sm w-full mx-4">
        <h3 className="text-base font-semibold text-zinc-900 mb-1">Delete transaction?</h3>
        <p className="text-sm text-zinc-500 mb-4">
          <span className="font-mono text-zinc-700">{txn.number}</span> — {txn.narration}
          <br />This cannot be undone.
        </p>
        <div className="flex gap-2 justify-end">
          <button
            onClick={onCancel}
            className="text-sm px-3 py-2 rounded-lg border border-zinc-200 hover:border-zinc-300 text-zinc-500 transition-colors"
          >
            Cancel
          </button>
          <button
            onClick={onConfirm}
            disabled={loading}
            className="text-sm px-3 py-2 rounded-lg bg-red-600 hover:bg-red-700 text-white font-medium transition-colors disabled:opacity-50"
          >
            {loading ? 'Deleting…' : 'Delete'}
          </button>
        </div>
      </div>
    </div>
  )
}

// ── Main page ─────────────────────────────────────────────────────────────

export default function Transactions() {
  const qc = useQueryClient()
  const [searchParams, setSearchParams] = useSearchParams()

  const [sheetOpen, setSheetOpen] = useState(false)
  const [editTxn, setEditTxn] = useState<TransactionOut | undefined>()
  const [expandedId, setExpandedId] = useState<number | null>(null)
  const [deleteTarget, setDeleteTarget] = useState<TransactionOut | null>(null)

  // Auto-open new transaction sheet when navigated here with ?new=1
  useEffect(() => {
    if (searchParams.get('new') === '1') {
      setSheetOpen(true)
      setSearchParams(prev => { const n = new URLSearchParams(prev); n.delete('new'); return n }, { replace: true })
    }
  }, [searchParams, setSearchParams])

  // Filter state persisted in URL
  const search = searchParams.get('q') ?? ''
  const period = (searchParams.get('period') ?? 'all') as PeriodKey
  const activeTypes = searchParams.get('types')?.split(',').filter(Boolean) ?? []

  const setSearch = (s: string) =>
    setSearchParams(prev => { const n = new URLSearchParams(prev); s ? n.set('q', s) : n.delete('q'); return n }, { replace: true })
  const setPeriod = (p: PeriodKey) =>
    setSearchParams(prev => { const n = new URLSearchParams(prev); p !== 'all' ? n.set('period', p) : n.delete('period'); return n }, { replace: true })
  const setActiveTypes = (types: string[]) =>
    setSearchParams(prev => { const n = new URLSearchParams(prev); types.length ? n.set('types', types.join(',')) : n.delete('types'); return n }, { replace: true })
  const clearFilters = () =>
    setSearchParams(prev => { const n = new URLSearchParams(prev); ['q', 'period', 'types'].forEach(k => n.delete(k)); return n }, { replace: true })

  const { data: txns = [], isLoading } = useQuery({
    queryKey: queryKeys.transactions.list(),
    queryFn: () => api.get<TransactionOut[]>('/transactions'),
  })

  const deleteMutation = useMutation({
    mutationFn: (id: number) => api.delete<void>(`/transactions/${id}`),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: queryKeys.transactions.list() })
      qc.invalidateQueries({ queryKey: queryKeys.accounts.list() })
      setDeleteTarget(null)
      if (expandedId === deleteTarget?.id) setExpandedId(null)
    },
  })

  // Client-side filtering
  const filtered = useMemo(() => {
    const start = startOf(period)
    const end = endOf(period)
    return txns.filter(txn => {
      if (search && !txn.narration.toLowerCase().includes(search.toLowerCase())) return false
      if (activeTypes.length && !activeTypes.includes(txn.type)) return false
      if (start && txn.date < start) return false
      if (end && txn.date > end) return false
      return true
    })
  }, [txns, search, period, activeTypes])

  // Group by date descending; within each date, newest transaction first
  const grouped = useMemo(() => {
    const sorted = [...filtered].sort((a, b) => {
      const d = b.date.localeCompare(a.date)
      return d !== 0 ? d : b.id - a.id
    })
    const map = new Map<string, TransactionOut[]>()
    for (const txn of sorted) {
      const list = map.get(txn.date) ?? []
      list.push(txn)
      map.set(txn.date, list)
    }
    return Array.from(map.entries())
  }, [filtered])

  const hasFilters = search || activeTypes.length > 0 || period !== 'all'

  function openNew() {
    setEditTxn(undefined)
    setSheetOpen(true)
  }

  function openEdit(txn: TransactionOut) {
    setEditTxn(txn)
    setSheetOpen(true)
  }

  function toggle(id: number) {
    setExpandedId(cur => cur === id ? null : id)
  }

  return (
    <div className="max-w-7xl mx-auto px-6 py-6">
      {/* Header */}
      <div className="flex items-center justify-between mb-6">
        <h1 className="text-2xl font-semibold text-zinc-900">Transactions</h1>
        <button
          onClick={openNew}
          className="flex items-center gap-2 bg-blue-600 hover:bg-blue-700 text-white text-sm font-medium px-4 py-2.5 rounded-xl transition-colors"
        >
          <Plus className="w-4 h-4" /> New Transaction
        </button>
      </div>

      {/* Filters */}
      <div className="mb-6">
        <FilterBar
          search={search}
          onSearch={setSearch}
          period={period}
          onPeriod={setPeriod}
          activeTypes={activeTypes}
          onTypes={setActiveTypes}
          hasFilters={hasFilters}
          onClear={clearFilters}
        />
      </div>

      {/* Content */}
      {isLoading ? (
        <div className="text-sm text-zinc-400 py-12 text-center">Loading…</div>
      ) : txns.length === 0 ? (
        <EmptyState
          icon={Receipt}
          heading="Your ledger is patiently waiting."
          subtext="Record your first transaction to get started."
        />
      ) : filtered.length === 0 ? (
        <EmptyState
          icon={Search}
          heading="Nothing matches — try adjusting your filters."
          subtext="Clear your search or change the period to see more."
        />
      ) : (
        <div className="space-y-8">
          {grouped.map(([date, group]) => (
            <div key={date}>
              <h2 className="text-xs font-semibold text-zinc-400 uppercase tracking-wider mb-3">
                {formatGroupDate(date)}
              </h2>
              <div className="space-y-2">
                {group.map(txn => (
                  <TxnRow
                    key={txn.id}
                    txn={txn}
                    expanded={expandedId === txn.id}
                    onToggle={() => toggle(txn.id)}
                    onEdit={() => openEdit(txn)}
                    onDelete={() => setDeleteTarget(txn)}
                  />
                ))}
              </div>
            </div>
          ))}
        </div>
      )}

      {/* Entry sheet */}
      <TransactionEntrySheet
        open={sheetOpen}
        onClose={() => setSheetOpen(false)}
        editTxn={editTxn}
        onSaved={() => {
          qc.invalidateQueries({ queryKey: queryKeys.transactions.list() })
        }}
      />

      {/* Delete confirmation */}
      {deleteTarget && (
        <DeleteConfirm
          txn={deleteTarget}
          onCancel={() => setDeleteTarget(null)}
          onConfirm={() => deleteMutation.mutate(deleteTarget.id)}
          loading={deleteMutation.isPending}
        />
      )}
    </div>
  )
}
