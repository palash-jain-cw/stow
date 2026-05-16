import { useState, useRef } from 'react'
import { useSearchParams, Link } from 'react-router-dom'
import { useQuery, useQueryClient, useMutation } from '@tanstack/react-query'
import { CheckCircle2, XCircle, Loader2, Pencil, Trash2 } from 'lucide-react'
import { api, queryKeys } from '../api/api'
import { MonoAmount } from '../components/MonoAmount'

// ── Types ─────────────────────────────────────────────────────────────────────

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
  investment_subtype: string | null
  balance: number
}

interface ScheduleOut {
  id: number
  template_transaction_id: number
  frequency: string
  day_of_period: number | null
  end_date: string | null
  next_due_date: string
  is_active: boolean
}

interface TransactionOut {
  id: number
  narration: string
  type: string
}

interface RuleOut {
  id: number
  pattern: string
  account_id: number
}

interface AiConfig {
  base_url: string
  model: string
}

interface ConnectionResult {
  ok: boolean
  model: string | null
  latency_ms: number | null
  error: string | null
}

interface PreLockCheck {
  unposted_depreciation: Array<{ account_id: number; account_name: string; amount: number }>
}

// ── Helpers ───────────────────────────────────────────────────────────────────

function fyLabel(fy: FinancialYear) {
  const start = new Date(fy.start_date)
  const end = new Date(fy.end_date)
  return `FY ${start.getFullYear()}–${String(end.getFullYear()).slice(2)}`
}

function formatDate(iso: string) {
  return new Date(iso).toLocaleDateString('en-IN', { day: '2-digit', month: 'short', year: 'numeric' })
}

function rupees(paise: number) {
  return new Intl.NumberFormat('en-IN', {
    style: 'currency', currency: 'INR',
    minimumFractionDigits: 0, maximumFractionDigits: 0,
  }).format(Math.round(paise) / 100)
}

const FREQ_COLORS: Record<string, string> = {
  daily: 'bg-blue-100 text-blue-700',
  weekly: 'bg-violet-100 text-violet-700',
  monthly: 'bg-emerald-100 text-emerald-800',
  yearly: 'bg-amber-100 text-amber-800',
}

// ── Modal wrapper ─────────────────────────────────────────────────────────────

function Modal({ open, onClose, title, children }: {
  open: boolean; onClose: () => void; title: string; children: React.ReactNode
}) {
  if (!open) return null
  return (
    <div
      className="fixed inset-0 bg-black/40 z-50 flex items-center justify-center"
      onClick={e => { if (e.target === e.currentTarget) onClose() }}
    >
      <div className="bg-white rounded-2xl p-6 w-[440px] shadow-xl max-h-[90vh] overflow-y-auto">
        <h2 className="text-base font-semibold text-zinc-900 mb-4">{title}</h2>
        {children}
      </div>
    </div>
  )
}

function ModalActions({ onCancel, onConfirm, confirmLabel, confirmDisabled, danger }: {
  onCancel: () => void; onConfirm: () => void; confirmLabel: string; confirmDisabled?: boolean; danger?: boolean
}) {
  return (
    <div className="flex justify-end gap-2 mt-5">
      <button onClick={onCancel} className="px-3 py-1.5 text-sm text-zinc-600 hover:text-zinc-900">Cancel</button>
      <button
        onClick={onConfirm}
        disabled={confirmDisabled}
        className={`px-4 py-1.5 rounded-lg text-sm font-medium disabled:opacity-40 ${
          danger ? 'bg-red-600 text-white hover:bg-red-700' : 'bg-zinc-900 text-white hover:bg-zinc-700'
        }`}
      >
        {confirmLabel}
      </button>
    </div>
  )
}

// ── Financial Years panel ─────────────────────────────────────────────────────

function FinancialYearsPanel() {
  const qc = useQueryClient()
  const [showNewFy, setShowNewFy] = useState(false)
  const [openingBalancesFy, setOpeningBalancesFy] = useState<FinancialYear | null>(null)
  const [lockFy, setLockFy] = useState<FinancialYear | null>(null)

  const { data: fys = [] } = useQuery<FinancialYear[]>({
    queryKey: queryKeys.financialYears.all(),
    queryFn: () => api.get<FinancialYear[]>('/financial-years'),
  })

  const sortedFys = [...fys].sort((a, b) => b.start_date.localeCompare(a.start_date))
  const activeFy = fys.find(f => f.status === 'active')

  // Suggest next FY start/end
  const lastFy = fys.reduce<FinancialYear | null>((acc, f) =>
    !acc || f.end_date > acc.end_date ? f : acc, null)
  const nextStart = lastFy
    ? new Date(new Date(lastFy.end_date).getTime() + 86400000).toISOString().slice(0, 10)
    : `${new Date().getFullYear()}-04-01`
  const nextEnd = nextStart
    ? `${parseInt(nextStart.slice(0, 4)) + 1}-03-31`
    : `${new Date().getFullYear() + 1}-03-31`

  const createFy = async () => {
    await api.post('/financial-years', { start_date: nextStart, end_date: nextEnd, status: 'open' })
    qc.invalidateQueries({ queryKey: queryKeys.financialYears.all() })
    setShowNewFy(false)
  }

  return (
    <div>
      <div className="flex items-start justify-between mb-4">
        <div>
          <h2 className="text-base font-semibold text-zinc-900">Financial Years</h2>
          <p className="text-sm text-zinc-500 mt-0.5">Each FY runs April 1 – March 31. Locking a year is irreversible.</p>
        </div>
        <button
          onClick={() => setShowNewFy(true)}
          className="px-3 py-1.5 bg-zinc-900 text-white text-sm rounded-lg hover:bg-zinc-700"
        >
          New FY
        </button>
      </div>

      <div className="divide-y divide-zinc-100 border border-zinc-200 rounded-xl overflow-hidden">
        {sortedFys.map(fy => (
          <div key={fy.id} className="flex items-center justify-between px-4 py-3 bg-white">
            <div>
              <div className="flex items-center gap-2">
                <span className="font-medium text-zinc-900 text-sm">{fyLabel(fy)}</span>
                <span className={`text-xs font-medium px-2 py-0.5 rounded-full ${
                  fy.status === 'active' ? 'bg-emerald-100 text-emerald-800' :
                  fy.status === 'locked' ? 'bg-zinc-100 text-zinc-600' :
                  'bg-blue-100 text-blue-700'
                }`}>
                  {fy.status.charAt(0).toUpperCase() + fy.status.slice(1)}
                </span>
              </div>
              <p className="text-xs text-zinc-400 mt-0.5">
                {formatDate(fy.start_date)} – {formatDate(fy.end_date)}
                {fy.net_profit !== null && ` · Net profit ${rupees(fy.net_profit)}`}
              </p>
            </div>
            <div className="flex items-center gap-2">
              {fy.status === 'active' && (
                <>
                  <button
                    onClick={() => setOpeningBalancesFy(fy)}
                    className="px-3 py-1 text-xs border border-zinc-200 rounded-lg text-zinc-600 hover:bg-zinc-50"
                  >
                    Opening balances
                  </button>
                  <button
                    onClick={() => setLockFy(fy)}
                    className="px-3 py-1 text-xs border border-zinc-200 rounded-lg text-zinc-600 hover:bg-zinc-50"
                  >
                    Lock year
                  </button>
                </>
              )}
              {fy.status === 'locked' && (
                <Link
                  to={`/reports?tab=pl&fy=${fy.id}`}
                  className="text-xs text-blue-600 hover:underline"
                >
                  View reports →
                </Link>
              )}
            </div>
          </div>
        ))}
        {fys.length === 0 && (
          <div className="px-4 py-8 text-center text-sm text-zinc-400">No financial years yet.</div>
        )}
      </div>

      <div className="mt-4 p-4 bg-zinc-50 rounded-xl text-xs text-zinc-500 leading-relaxed">
        <strong>Year-end closing.</strong> When you lock a year, net profit is automatically transferred to Reserves &amp; Surplus.
        Depreciation entries should be posted before locking — the system will warn if any fixed assets have unposted depreciation.
      </div>

      {/* New FY modal */}
      <Modal open={showNewFy} onClose={() => setShowNewFy(false)} title="Open new financial year">
        <p className="text-sm text-zinc-600 mb-4">
          This will create <strong>FY {nextStart?.slice(0, 4)}–{nextEnd?.slice(2, 4)}</strong> ({formatDate(nextStart)} – {formatDate(nextEnd)}).
        </p>
        <p className="text-xs text-zinc-400">
          After opening, set opening balances for all accounts from the Financial Years list.
        </p>
        <ModalActions
          onCancel={() => setShowNewFy(false)}
          onConfirm={createFy}
          confirmLabel={`Open FY ${nextStart?.slice(0, 4)}–${nextEnd?.slice(2, 4)}`}
        />
      </Modal>

      {/* Opening balances modal */}
      {openingBalancesFy && (
        <OpeningBalancesModal fy={openingBalancesFy} onClose={() => setOpeningBalancesFy(null)} />
      )}

      {/* Lock year modal */}
      {lockFy && (
        <LockYearModal fy={lockFy} onClose={() => setLockFy(null)} onLocked={() => {
          setLockFy(null)
          qc.invalidateQueries({ queryKey: queryKeys.financialYears.all() })
        }} />
      )}
    </div>
  )
}

// ── Opening Balances modal ────────────────────────────────────────────────────

function OpeningBalancesModal({ fy, onClose }: { fy: FinancialYear; onClose: () => void }) {
  const qc = useQueryClient()

  const { data: accounts = [] } = useQuery<AccountOut[]>({
    queryKey: queryKeys.accounts.list(),
    queryFn: () => api.get<AccountOut[]>('/accounts'),
  })

  const obAccounts = accounts.filter(a => !a.is_archived && ['asset', 'liability', 'equity'].includes(a.nature))

  // Group by group_name
  const groups = obAccounts.reduce<Record<string, AccountOut[]>>((acc, a) => {
    if (!acc[a.group_name]) acc[a.group_name] = []
    acc[a.group_name].push(a)
    return acc
  }, {})

  const [values, setValues] = useState<Record<number, string>>({})

  const setValue = (id: number, v: string) => setValues(prev => ({ ...prev, [id]: v }))

  const paiseFor = (id: number, nature: string) => {
    const v = parseFloat(values[id] ?? '0')
    if (isNaN(v)) return 0
    const raw = Math.round(v * 100)
    return nature === 'liability' || nature === 'equity' ? -raw : raw
  }

  const totalAssets = obAccounts.filter(a => a.nature === 'asset').reduce((s, a) => s + paiseFor(a.id, a.nature), 0)
  const totalLiabilities = obAccounts.filter(a => a.nature === 'liability').reduce((s, a) => s + Math.abs(paiseFor(a.id, a.nature)), 0)
  const totalEquity = obAccounts.filter(a => a.nature === 'equity').reduce((s, a) => s + Math.abs(paiseFor(a.id, a.nature)), 0)
  const diff = totalAssets - totalLiabilities - totalEquity
  const balanced = diff === 0

  const save = async () => {
    const promises = obAccounts
      .filter(a => values[a.id] !== undefined && values[a.id] !== '' && values[a.id] !== '0')
      .map(a => api.put(`/accounts/${a.id}/opening-balance`, { fy_id: fy.id, amount: paiseFor(a.id, a.nature) }))
    await Promise.all(promises)
    qc.invalidateQueries({ queryKey: queryKeys.accounts.list() })
    onClose()
  }

  return (
    <Modal open onClose={onClose} title={`Opening balances — ${fyLabel(fy)}`}>
      <p className="text-xs text-zinc-400 mb-4">
        Balances as at {formatDate(fy.start_date)}.
      </p>

      <div className="space-y-4">
        {Object.entries(groups).map(([groupName, accs]) => (
          <div key={groupName}>
            <p className="text-xs font-semibold text-zinc-500 uppercase tracking-wide mb-1">{groupName}</p>
            <div className="space-y-1">
              {accs.map(a => (
                <div key={a.id} className="flex items-center gap-2">
                  <span className="flex-1 text-sm text-zinc-700">{a.name}</span>
                  <span className="text-xs text-zinc-400">₹</span>
                  <input
                    type="number"
                    className="w-28 text-right border border-zinc-200 rounded-lg px-2 py-1 text-sm font-mono focus:outline-none focus:ring-2 focus:ring-zinc-300"
                    placeholder="0"
                    value={values[a.id] ?? ''}
                    onChange={e => setValue(a.id, e.target.value)}
                  />
                </div>
              ))}
            </div>
          </div>
        ))}
      </div>

      <div className={`mt-4 px-3 py-2 rounded-lg text-sm font-mono ${balanced ? 'bg-emerald-50 text-emerald-700' : 'bg-red-50 text-red-700'}`}>
        Assets − Liabilities − Equity = {rupees(Math.abs(diff))}&nbsp;
        {balanced ? '· Balanced.' : `· Out of balance by ${rupees(Math.abs(diff))}`}
      </div>

      <ModalActions onCancel={onClose} onConfirm={save} confirmLabel="Save balances" />
    </Modal>
  )
}

// ── Lock Year modal ───────────────────────────────────────────────────────────

function LockYearModal({ fy, onClose, onLocked }: {
  fy: FinancialYear; onClose: () => void; onLocked: () => void
}) {
  const { data: check } = useQuery<PreLockCheck>({
    queryKey: ['pre-lock-check', fy.id],
    queryFn: () => api.get<PreLockCheck>(`/financial-years/${fy.id}/pre-lock-check`),
  })

  const lock = async () => {
    await api.post(`/financial-years/${fy.id}/lock`, {})
    onLocked()
  }

  const hasWarnings = (check?.unposted_depreciation?.length ?? 0) > 0

  return (
    <Modal open onClose={onClose} title={`Lock ${fyLabel(fy)}?`}>
      <p className="text-sm text-zinc-600 mb-3">
        <strong>This cannot be undone.</strong> Locking will: mark all transactions as read-only and prevent further entries in this year.
      </p>

      {hasWarnings && (
        <div className="bg-amber-50 border border-amber-200 rounded-lg p-3 mb-3 text-sm text-amber-800">
          <p className="font-medium mb-1">Unposted depreciation:</p>
          <ul className="space-y-0.5 text-xs">
            {check!.unposted_depreciation.map(d => (
              <li key={d.account_id}>{d.account_name} — <MonoAmount paise={d.amount} /></li>
            ))}
          </ul>
          <p className="text-xs mt-2 text-amber-700">Post these depreciation Journal entries before locking.</p>
        </div>
      )}

      <ModalActions
        onCancel={onClose}
        onConfirm={lock}
        confirmLabel="Lock year"
        danger
      />
    </Modal>
  )
}

// ── Recurring panel ───────────────────────────────────────────────────────────

function RecurringPanel() {
  const qc = useQueryClient()
  const [editSchedule, setEditSchedule] = useState<ScheduleOut | null>(null)
  const [stopSchedule, setStopSchedule] = useState<{ id: number; narration: string } | null>(null)
  const [editFreq, setEditFreq] = useState('')
  const [editEndDate, setEditEndDate] = useState('')

  const { data: schedules = [] } = useQuery<ScheduleOut[]>({
    queryKey: queryKeys.recurring.schedules(),
    queryFn: () => api.get<ScheduleOut[]>('/recurring/schedules'),
  })

  // Fetch all template transactions in parallel
  const { data: txnMap = {} } = useQuery<Record<number, TransactionOut>>({
    queryKey: ['recurring-transactions', schedules.map(s => s.template_transaction_id)],
    queryFn: async () => {
      const ids = [...new Set(schedules.map(s => s.template_transaction_id))]
      const txns = await Promise.all(ids.map(id => api.get<TransactionOut>(`/transactions/${id}`)))
      return Object.fromEntries(ids.map((id, i) => [id, txns[i]]))
    },
    enabled: schedules.length > 0,
  })

  const openEdit = (s: ScheduleOut) => {
    setEditSchedule(s)
    setEditFreq(s.frequency)
    setEditEndDate(s.end_date ?? '')
  }

  const saveEdit = async () => {
    if (!editSchedule) return
    await api.put(`/recurring/schedules/${editSchedule.id}`, {
      template_transaction_id: editSchedule.template_transaction_id,
      frequency: editFreq,
      day_of_period: editSchedule.day_of_period,
      first_due_date: editSchedule.next_due_date,
      end_date: editEndDate || null,
    })
    qc.invalidateQueries({ queryKey: queryKeys.recurring.schedules() })
    setEditSchedule(null)
  }

  const confirmStop = async () => {
    if (!stopSchedule) return
    await api.delete(`/recurring/schedules/${stopSchedule.id}`)
    qc.invalidateQueries({ queryKey: queryKeys.recurring.schedules() })
    setStopSchedule(null)
  }

  return (
    <div>
      <div className="mb-4">
        <h2 className="text-base font-semibold text-zinc-900">Recurring Transactions</h2>
        <p className="text-sm text-zinc-500 mt-0.5">
          Schedules that generate a transaction for review on each due date.
        </p>
      </div>

      <div className="border border-zinc-200 rounded-xl overflow-hidden">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-zinc-200 bg-zinc-50">
              <th className="text-left px-4 py-2 font-medium text-zinc-500">Narration</th>
              <th className="text-left px-4 py-2 font-medium text-zinc-500">Frequency</th>
              <th className="text-left px-4 py-2 font-medium text-zinc-500">Next due</th>
              <th className="text-left px-4 py-2 font-medium text-zinc-500">Until</th>
              <th className="w-20" />
            </tr>
          </thead>
          <tbody className="divide-y divide-zinc-100">
            {schedules.map(s => (
              <tr key={s.id} className="bg-white">
                <td className="px-4 py-3 text-zinc-900">
                  {txnMap[s.template_transaction_id]?.narration ?? `Schedule #${s.id}`}
                </td>
                <td className="px-4 py-3">
                  <span className={`text-xs font-medium px-2 py-0.5 rounded-full ${FREQ_COLORS[s.frequency] ?? 'bg-zinc-100 text-zinc-600'}`}>
                    {s.frequency.charAt(0).toUpperCase() + s.frequency.slice(1)}
                  </span>
                </td>
                <td className="px-4 py-3 text-zinc-600">{formatDate(s.next_due_date)}</td>
                <td className="px-4 py-3 text-zinc-500">{s.end_date ? formatDate(s.end_date) : 'No end'}</td>
                <td className="px-4 py-3">
                  <div className="flex gap-2 justify-end">
                    <button onClick={() => openEdit(s)} className="text-zinc-400 hover:text-zinc-700">
                      <Pencil size={15} />
                    </button>
                    <button
                      onClick={() => setStopSchedule({
                        id: s.id,
                        narration: txnMap[s.template_transaction_id]?.narration ?? `Schedule #${s.id}`,
                      })}
                      className="text-zinc-400 hover:text-red-500"
                    >
                      <Trash2 size={15} />
                    </button>
                  </div>
                </td>
              </tr>
            ))}
            {schedules.length === 0 && (
              <tr>
                <td colSpan={5} className="px-4 py-8 text-center text-sm text-zinc-400">
                  No recurring schedules.
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>

      <p className="text-xs text-zinc-400 mt-3">
        Recurring transactions are created from the transaction entry sheet. Edit a schedule here to change its frequency or end date.
      </p>

      {/* Edit modal */}
      <Modal open={!!editSchedule} onClose={() => setEditSchedule(null)} title="Edit schedule">
        <div className="space-y-3">
          <div>
            <label className="block text-xs font-medium text-zinc-600 mb-1">Frequency</label>
            <select
              className="w-full border border-zinc-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-zinc-300"
              value={editFreq}
              onChange={e => setEditFreq(e.target.value)}
            >
              {['daily', 'weekly', 'monthly', 'yearly'].map(f => (
                <option key={f} value={f}>{f.charAt(0).toUpperCase() + f.slice(1)}</option>
              ))}
            </select>
          </div>
          <div>
            <label className="block text-xs font-medium text-zinc-600 mb-1">End date (optional)</label>
            <input
              type="date"
              className="w-full border border-zinc-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-zinc-300"
              value={editEndDate}
              onChange={e => setEditEndDate(e.target.value)}
            />
          </div>
        </div>
        <ModalActions onCancel={() => setEditSchedule(null)} onConfirm={saveEdit} confirmLabel="Save" />
      </Modal>

      {/* Stop modal */}
      <Modal open={!!stopSchedule} onClose={() => setStopSchedule(null)} title="Stop recurring?">
        <p className="text-sm text-zinc-600">
          Stop <strong>{stopSchedule?.narration}</strong>? Past transactions are kept; no new ones will be created.
        </p>
        <ModalActions
          onCancel={() => setStopSchedule(null)}
          onConfirm={confirmStop}
          confirmLabel="Stop schedule"
          danger
        />
      </Modal>
    </div>
  )
}

// ── Merchant Rules panel ──────────────────────────────────────────────────────

function MerchantRulesPanel() {
  const qc = useQueryClient()
  const [editingId, setEditingId] = useState<number | null>(null)
  const [editPattern, setEditPattern] = useState('')
  const [editAccountId, setEditAccountId] = useState<number | ''>('')
  const [undoToast, setUndoToast] = useState<{ rule: RuleOut; timer: ReturnType<typeof setTimeout> } | null>(null)

  const { data: rules = [] } = useQuery<RuleOut[]>({
    queryKey: queryKeys.merchantRules.all(),
    queryFn: () => api.get<RuleOut[]>('/merchant-rules'),
  })

  const { data: accounts = [] } = useQuery<AccountOut[]>({
    queryKey: queryKeys.accounts.list(),
    queryFn: () => api.get<AccountOut[]>('/accounts'),
  })

  const accountMap = Object.fromEntries(accounts.map(a => [a.id, a]))

  const startEdit = (rule: RuleOut) => {
    setEditingId(rule.id)
    setEditPattern(rule.pattern)
    setEditAccountId(rule.account_id)
  }

  const saveEdit = async () => {
    if (!editingId || editAccountId === '') return
    await api.put<RuleOut>(`/merchant-rules/${editingId}`, { pattern: editPattern, account_id: editAccountId })
    qc.invalidateQueries({ queryKey: queryKeys.merchantRules.all() })
    setEditingId(null)
  }

  const deleteRule = (rule: RuleOut) => {
    if (undoToast) {
      clearTimeout(undoToast.timer)
      // previous deletion already happened, just clear toast
    }
    const timer = setTimeout(async () => {
      setUndoToast(null)
      qc.invalidateQueries({ queryKey: queryKeys.merchantRules.all() })
    }, 3000)
    setUndoToast({ rule, timer })
    // Optimistic removal from cache
    qc.setQueryData<RuleOut[]>(queryKeys.merchantRules.all(), prev => prev?.filter(r => r.id !== rule.id) ?? [])
    api.delete(`/merchant-rules/${rule.id}`).catch(() => {
      qc.invalidateQueries({ queryKey: queryKeys.merchantRules.all() })
    })
  }

  const undoDelete = async () => {
    if (!undoToast) return
    clearTimeout(undoToast.timer)
    setUndoToast(null)
    await api.post<RuleOut>('/merchant-rules', { pattern: undoToast.rule.pattern, account_id: undoToast.rule.account_id })
    qc.invalidateQueries({ queryKey: queryKeys.merchantRules.all() })
  }

  return (
    <div>
      <div className="mb-4">
        <h2 className="text-base font-semibold text-zinc-900">Merchant Rules</h2>
        <p className="text-sm text-zinc-500 mt-0.5">Saved mappings applied automatically during bank import before AI suggestions.</p>
      </div>

      <div className="border border-zinc-200 rounded-xl overflow-hidden">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-zinc-200 bg-zinc-50">
              <th className="text-left px-4 py-2 font-medium text-zinc-500">Merchant pattern</th>
              <th className="text-left px-4 py-2 font-medium text-zinc-500">Maps to account</th>
              <th className="text-left px-4 py-2 font-medium text-zinc-500">Type</th>
              <th className="w-20" />
            </tr>
          </thead>
          <tbody className="divide-y divide-zinc-100">
            {rules.map(rule => (
              editingId === rule.id ? (
                <tr key={rule.id} className="bg-zinc-50">
                  <td className="px-4 py-2">
                    <input
                      className="w-full border border-zinc-200 rounded-lg px-2 py-1 text-sm font-mono focus:outline-none focus:ring-2 focus:ring-zinc-300"
                      value={editPattern}
                      onChange={e => setEditPattern(e.target.value)}
                    />
                  </td>
                  <td className="px-4 py-2" colSpan={2}>
                    <select
                      className="w-full border border-zinc-200 rounded-lg px-2 py-1 text-sm focus:outline-none focus:ring-2 focus:ring-zinc-300"
                      value={editAccountId}
                      onChange={e => setEditAccountId(Number(e.target.value))}
                    >
                      <option value="">— pick account —</option>
                      {accounts.filter(a => !a.is_archived).map(a => (
                        <option key={a.id} value={a.id}>{a.name}</option>
                      ))}
                    </select>
                  </td>
                  <td className="px-4 py-2">
                    <div className="flex gap-1 justify-end">
                      <button onClick={saveEdit} className="text-xs bg-zinc-900 text-white px-2 py-1 rounded-lg">Save</button>
                      <button onClick={() => setEditingId(null)} className="text-xs text-zinc-500 px-2 py-1">Cancel</button>
                    </div>
                  </td>
                </tr>
              ) : (
                <tr key={rule.id} className="bg-white hover:bg-zinc-50 transition-colors">
                  <td className="px-4 py-3 font-mono text-sm text-zinc-800">{rule.pattern}</td>
                  <td className="px-4 py-3 text-zinc-700">{accountMap[rule.account_id]?.name ?? `#${rule.account_id}`}</td>
                  <td className="px-4 py-3 text-zinc-500 text-xs capitalize">{accountMap[rule.account_id]?.nature ?? '—'}</td>
                  <td className="px-4 py-3">
                    <div className="flex gap-2 justify-end">
                      <button onClick={() => startEdit(rule)} className="text-zinc-400 hover:text-zinc-700">
                        <Pencil size={15} />
                      </button>
                      <button onClick={() => deleteRule(rule)} className="text-zinc-400 hover:text-red-500">
                        <Trash2 size={15} />
                      </button>
                    </div>
                  </td>
                </tr>
              )
            ))}
            {rules.length === 0 && (
              <tr>
                <td colSpan={4} className="px-4 py-8 text-center text-sm text-zinc-400">No merchant rules yet.</td>
              </tr>
            )}
          </tbody>
        </table>
      </div>

      <p className="text-xs text-zinc-400 mt-3">
        Rules are matched case-insensitively. Use <code className="font-mono bg-zinc-100 px-1 rounded">*</code> as a wildcard.
      </p>

      {/* Undo toast */}
      {undoToast && (
        <div className="fixed bottom-6 left-1/2 -translate-x-1/2 bg-zinc-900 text-white text-sm px-4 py-2 rounded-xl flex items-center gap-3 shadow-lg z-50">
          <span>Rule deleted</span>
          <button onClick={undoDelete} className="text-blue-400 hover:text-blue-300 font-medium">Undo</button>
        </div>
      )}
    </div>
  )
}

// ── AI / LLM panel ────────────────────────────────────────────────────────────

type ConnStatus = 'idle' | 'loading' | 'ok' | 'fail'

function AiPanel() {
  const qc = useQueryClient()
  const { data: config } = useQuery<AiConfig>({
    queryKey: queryKeys.ai.config(),
    queryFn: () => api.get<AiConfig>('/ai/config'),
  })

  const [baseUrl, setBaseUrl] = useState('')
  const [model, setModel] = useState('')
  const [apiKey, setApiKey] = useState('')
  const [connStatus, setConnStatus] = useState<ConnStatus>('idle')
  const [connMsg, setConnMsg] = useState('Not tested')
  const [saveLabel, setSaveLabel] = useState('Save')

  // Populate form when config loads
  const populated = useRef(false)
  if (config && !populated.current) {
    setBaseUrl(config.base_url)
    setModel(config.model)
    populated.current = true
    // api_key is write-only — backend doesn't return it, leave blank for user to re-enter if needed
  }

  const testConnection = async () => {
    setConnStatus('loading')
    setConnMsg('Testing…')
    try {
      const result = await api.post<ConnectionResult>('/ai/test-connection', {})
      if (result.ok) {
        setConnStatus('ok')
        setConnMsg(`Connected · ${result.model ?? model} · ${result.latency_ms}ms`)
      } else {
        setConnStatus('fail')
        setConnMsg(result.error ?? 'Connection failed')
      }
    } catch (e: unknown) {
      setConnStatus('fail')
      setConnMsg(e instanceof Error ? e.message : 'Connection failed')
    }
  }

  const save = async () => {
    await api.post('/ai/config', { base_url: baseUrl, model, api_key: apiKey })
    qc.invalidateQueries({ queryKey: queryKeys.ai.config() })
    setSaveLabel('Saved')
    setTimeout(() => setSaveLabel('Save'), 1800)
  }

  return (
    <div className="max-w-md">
      <div className="mb-5">
        <h2 className="text-base font-semibold text-zinc-900">AI / LLM</h2>
        <p className="text-sm text-zinc-500 mt-0.5">
          Local OpenAI-compatible inference server for NL entry and bank import parsing. No data leaves your machine.
        </p>
      </div>

      <div className="space-y-4">
        <div>
          <label className="block text-xs font-medium text-zinc-600 mb-1">
            Server URL <code className="ml-1 font-mono text-zinc-400 text-[10px]">STOW_LLM_BASE_URL</code>
          </label>
          <input
            type="url"
            className="w-full border border-zinc-200 rounded-lg px-3 py-2 text-sm font-mono focus:outline-none focus:ring-2 focus:ring-zinc-300"
            placeholder="http://localhost:11434/v1"
            value={baseUrl}
            onChange={e => setBaseUrl(e.target.value)}
          />
          <p className="text-xs text-zinc-400 mt-1">
            Ollama default is <code className="font-mono">http://localhost:11434/v1</code> · oMLX default is <code className="font-mono">http://localhost:10240/v1</code>
          </p>
        </div>

        <div>
          <label className="block text-xs font-medium text-zinc-600 mb-1">
            Model name <code className="ml-1 font-mono text-zinc-400 text-[10px]">STOW_LLM_MODEL</code>
          </label>
          <input
            type="text"
            className="w-full border border-zinc-200 rounded-lg px-3 py-2 text-sm font-mono focus:outline-none focus:ring-2 focus:ring-zinc-300"
            placeholder="qwen3:30b"
            value={model}
            onChange={e => setModel(e.target.value)}
          />
          <p className="text-xs text-zinc-400 mt-1">Must support function calling. Qwen3, Llama 3.1+, Mistral v0.3+ all work.</p>
        </div>

        <div>
          <label className="block text-xs font-medium text-zinc-600 mb-1">
            API key <span className="text-zinc-400 font-normal">(optional — leave blank for Ollama)</span>
          </label>
          <input
            type="password"
            className="w-full border border-zinc-200 rounded-lg px-3 py-2 text-sm font-mono focus:outline-none focus:ring-2 focus:ring-zinc-300"
            placeholder="sk-..."
            value={apiKey}
            onChange={e => setApiKey(e.target.value)}
          />
        </div>

        <div className="flex items-center gap-4">
          <button
            onClick={testConnection}
            disabled={connStatus === 'loading'}
            className="px-3 py-1.5 border border-zinc-200 rounded-lg text-sm text-zinc-600 hover:bg-zinc-50 disabled:opacity-50"
          >
            Test connection
          </button>
          <div className="flex items-center gap-1.5 text-xs">
            {connStatus === 'loading' && <Loader2 size={13} className="animate-spin text-zinc-400" />}
            {connStatus === 'ok' && <CheckCircle2 size={13} className="text-emerald-600" />}
            {connStatus === 'fail' && <XCircle size={13} className="text-red-500" />}
            <span className={
              connStatus === 'ok' ? 'text-emerald-600' :
              connStatus === 'fail' ? 'text-red-500' : 'text-zinc-400'
            }>{connMsg}</span>
          </div>
        </div>

        <button
          onClick={save}
          className="px-4 py-1.5 bg-zinc-900 text-white rounded-lg text-sm hover:bg-zinc-700"
        >
          {saveLabel}
        </button>
      </div>

      <div className="mt-6 p-4 bg-zinc-50 rounded-xl text-xs text-zinc-500 space-y-1">
        <p className="font-medium text-zinc-700 mb-2">Used for</p>
        <p>· Natural language transaction entry (dashboard)</p>
        <p>· Bank statement parsing (PDF text extraction → structured rows)</p>
        <p>· Account mapping suggestions during import</p>
        <p className="mt-2 text-zinc-400">Settings are stored in <code className="font-mono">~/.stow/config</code> and can also be set as environment variables.</p>
      </div>
    </div>
  )
}

// ── Main component ────────────────────────────────────────────────────────────

const PANELS = [
  { id: 'fy', label: 'Financial Years' },
  { id: 'recurring', label: 'Recurring' },
  { id: 'rules', label: 'Merchant Rules' },
  { id: 'ai', label: 'AI / LLM' },
] as const

type PanelId = typeof PANELS[number]['id']

export default function Settings() {
  const [searchParams, setSearchParams] = useSearchParams()
  const panel = (searchParams.get('panel') ?? 'fy') as PanelId

  const setPanel = (p: PanelId) => setSearchParams({ panel: p })

  return (
    <div className="flex h-full overflow-hidden">
      {/* Left nav */}
      <nav className="w-48 border-r border-zinc-200 bg-white shrink-0 p-3">
        <p className="text-xs font-semibold text-zinc-400 uppercase tracking-wide px-2 mb-2">Settings</p>
        <ul className="space-y-0.5">
          {PANELS.map(p => (
            <li key={p.id}>
              <button
                onClick={() => setPanel(p.id)}
                className={`w-full text-left px-3 py-2 rounded-lg text-sm transition-colors ${
                  panel === p.id
                    ? 'bg-zinc-100 text-zinc-900 font-medium'
                    : 'text-zinc-500 hover:bg-zinc-50 hover:text-zinc-700'
                }`}
              >
                {p.label}
              </button>
            </li>
          ))}
        </ul>
      </nav>

      {/* Content */}
      <main className="flex-1 overflow-y-auto p-8">
        {panel === 'fy' && <FinancialYearsPanel />}
        {panel === 'recurring' && <RecurringPanel />}
        {panel === 'rules' && <MerchantRulesPanel />}
        {panel === 'ai' && <AiPanel />}
      </main>
    </div>
  )
}
