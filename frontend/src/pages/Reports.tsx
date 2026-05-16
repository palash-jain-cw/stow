import { useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { ChevronDown, CheckCircle2, AlertCircle, Download } from 'lucide-react'
import { api, queryKeys } from '../api/api'
import { MonoAmount } from '../components/MonoAmount'

// ── Types ─────────────────────────────────────────────────────────────────────

interface FinancialYear { id: number; start_date: string; end_date: string; status: string }

interface PLAccount { account_id: number; account_name: string; amount: number }
interface PLGroup { group_name: string; nature: string; accounts: PLAccount[]; subtotal: number }
interface PLReport {
  fy_start_date: string; fy_end_date: string
  income_groups: PLGroup[]; expense_groups: PLGroup[]
  total_income: number; total_expenses: number; net_profit: number
}

interface BSAccount { account_id: number; account_name: string; amount: number }
interface BSSection { group_name: string; nature: string; accounts: BSAccount[]; subtotal: number }
interface BSReport {
  as_of_date: string
  asset_sections: BSSection[]; liability_sections: BSSection[]; equity_sections: BSSection[]
  total_assets: number; total_liabilities_and_equity: number
}

interface TBRow {
  account_name: string; group_name: string
  debit: number; credit: number
}
interface TBReport {
  fy_start_date: string; fy_end_date: string
  rows: TBRow[]; total_debit: number; total_credit: number
}

interface CFItem { label: string; amount: number }
interface CFSection { tag: string; items: CFItem[]; subtotal: number }
interface CFReport {
  fy_start_date: string; fy_end_date: string
  net_profit: number; sections: CFSection[]
  net_change_in_cash: number; opening_cash: number; closing_cash: number
}

interface AccountOut {
  id: number; name: string; nature: string; is_archived: boolean
  investment_subtype: string | null
}

interface CGEntry {
  id: number; units_sold: number; sale_date: string
  sale_price_per_unit: number; gain: number; gain_type: string
}
interface CGSummary { entries: CGEntry[]; total_stcg: number; total_ltcg: number; total_loss: number }

interface TaxRule {
  id: number; asset_type: string; holding_threshold_days: number
  stcg_rate_bps: number; ltcg_rate_bps: number; ltcg_exemption_paise: number
  effective_from: string
}

type Tab = 'pl' | 'bs' | 'tb' | 'cf' | 'cg'

// ── Constants ─────────────────────────────────────────────────────────────────

const BASE = import.meta.env.VITE_API_BASE_URL ?? 'http://localhost:8000'

const TAB_LABELS: Record<Tab, string> = {
  pl: 'P&L', bs: 'Balance Sheet', tb: 'Trial Balance', cf: 'Cash Flow', cg: 'Capital Gains',
}

const PDF_REPORT_TYPE: Partial<Record<Tab, string>> = {
  pl: 'profit-loss', bs: 'balance-sheet', tb: 'trial-balance', cf: 'cash-flow',
}

// ── Helpers ───────────────────────────────────────────────────────────────────

function fmtDate(iso: string) {
  return new Date(iso).toLocaleDateString('en-IN', { day: 'numeric', month: 'long', year: 'numeric' })
}

function fmtDateShort(iso: string) {
  return new Date(iso).toLocaleDateString('en-IN', { day: 'numeric', month: 'short', year: 'numeric' })
}

const fmtRupees = new Intl.NumberFormat('en-IN', { style: 'currency', currency: 'INR', minimumFractionDigits: 0 })
function rupees(paise: number) { return fmtRupees.format(Math.abs(paise) / 100) }

// ── Shared sub-components ──────────────────────────────────────────────────────

function SectionHeader({ label }: { label: string }) {
  return (
    <tr className="bg-zinc-50">
      <td colSpan={10} className="px-3 py-2 text-xs font-semibold text-zinc-500 uppercase tracking-wider">{label}</td>
    </tr>
  )
}

function TotalRow({ label, amount, grand = false, colored = false }: { label: string; amount: number; grand?: boolean; colored?: boolean }) {
  const borderClass = grand ? 'border-t-2 border-b-2 border-zinc-900 bg-zinc-100' : 'border-t border-zinc-300'
  const amountColor = colored ? (amount >= 0 ? 'text-emerald-700' : 'text-red-600') : 'text-zinc-900'
  return (
    <tr className={borderClass}>
      <td className="px-3 py-2.5 font-semibold text-zinc-900">{label}</td>
      <td className={`px-3 py-2.5 text-right font-mono font-semibold ${amountColor}`}>
        {amount < 0 ? `(${rupees(amount)})` : rupees(amount)}
      </td>
    </tr>
  )
}

function BalanceCheck({ ok, okText, failText }: { ok: boolean; okText: string; failText: string }) {
  return (
    <div className={`mt-4 flex items-center gap-2 text-xs rounded-xl px-4 py-2.5 border ${ok ? 'text-emerald-700 bg-emerald-50 border-emerald-200' : 'text-red-700 bg-red-50 border-red-200'}`}>
      {ok ? <CheckCircle2 className="w-3.5 h-3.5 shrink-0" /> : <AlertCircle className="w-3.5 h-3.5 shrink-0" />}
      {ok ? okText : failText}
    </div>
  )
}

function LoadingRows({ cols = 2 }: { cols?: number }) {
  return (
    <>
      {[...Array(5)].map((_, i) => (
        <tr key={i} className="border-b border-zinc-100 animate-pulse">
          {[...Array(cols)].map((_, j) => (
            <td key={j} className="px-3 py-3">
              <div className="h-3 bg-zinc-100 rounded" style={{ width: j === 0 ? '60%' : '40%' }} />
            </td>
          ))}
        </tr>
      ))}
    </>
  )
}

function NoData() {
  return <p className="text-sm text-zinc-400 text-center py-12">No data for this period.</p>
}

// ── Collapsible group row ──────────────────────────────────────────────────────

function PLGroupBlock({
  group, collapsed, onToggle,
}: { group: PLGroup; collapsed: boolean; onToggle: () => void }) {
  return (
    <>
      <tr className="cursor-pointer hover:bg-zinc-50" onClick={onToggle}>
        <td className="px-3 py-2 pl-5">
          <span className="flex items-center gap-1.5 font-medium text-zinc-800">
            <ChevronDown className={`w-3.5 h-3.5 text-zinc-400 transition-transform duration-200 ${collapsed ? '-rotate-90' : ''}`} />
            {group.group_name}
          </span>
        </td>
        <td className="px-3 py-2 text-right font-mono font-medium text-zinc-900">{rupees(group.subtotal)}</td>
      </tr>
      {!collapsed && group.accounts.map(a => (
        <tr key={a.account_id} className="hover:bg-zinc-50">
          <td className="px-3 py-1.5 pl-12 text-zinc-600">{a.account_name}</td>
          <td className="px-3 py-1.5 text-right font-mono text-zinc-700">
            {Math.abs(a.amount) === 0 ? '—' : new Intl.NumberFormat('en-IN').format(Math.abs(a.amount) / 100)}
          </td>
        </tr>
      ))}
    </>
  )
}

function BSGroupBlock({
  section, collapsed, onToggle, indent = true,
}: { section: BSSection; collapsed: boolean; onToggle: () => void; indent?: boolean }) {
  return (
    <>
      <tr className="cursor-pointer hover:bg-zinc-50" onClick={onToggle}>
        <td className={`px-3 py-2 ${indent ? 'pl-3' : 'pl-3'}`}>
          <span className="flex items-center gap-1.5 font-medium text-zinc-800">
            <ChevronDown className={`w-3.5 h-3.5 text-zinc-400 transition-transform duration-200 ${collapsed ? '-rotate-90' : ''}`} />
            {section.group_name}
          </span>
        </td>
        <td className="px-3 py-2 text-right font-mono font-medium text-zinc-900">{rupees(section.subtotal)}</td>
      </tr>
      {!collapsed && section.accounts.map((a, i) => (
        <tr key={i} className="hover:bg-zinc-50">
          <td className={`px-3 py-1.5 pl-10 ${a.amount < 0 ? 'text-zinc-400 italic' : 'text-zinc-600'}`}>{a.account_name}</td>
          <td className={`px-3 py-1.5 text-right font-mono ${a.amount < 0 ? 'text-zinc-400' : 'text-zinc-700'}`}>
            {a.amount < 0 ? `(${new Intl.NumberFormat('en-IN').format(Math.abs(a.amount) / 100)})` : new Intl.NumberFormat('en-IN').format(Math.abs(a.amount) / 100)}
          </td>
        </tr>
      ))}
    </>
  )
}

// ── Main component ────────────────────────────────────────────────────────────

export default function Reports() {
  const [searchParams, setSearchParams] = useSearchParams()
  const tab = (searchParams.get('tab') as Tab) ?? 'pl'
  const [collapsed, setCollapsed] = useState<Set<string>>(new Set())

  function setTab(t: Tab) { setSearchParams({ tab: t }) }
  function toggleGroup(key: string) {
    setCollapsed(prev => {
      const next = new Set(prev)
      next.has(key) ? next.delete(key) : next.add(key)
      return next
    })
  }

  // ── Queries ──────────────────────────────────────────────────────────────────

  const { data: fys = [] } = useQuery<FinancialYear[]>({
    queryKey: queryKeys.financialYears.all(),
    queryFn: () => api.get('/financial-years'),
  })

  const activeFy = fys.find(f => f.status === 'active')
  const [fyId, setFyId] = useState<number | null>(null)
  const resolvedFyId = fyId ?? activeFy?.id ?? null

  const { data: pl, isLoading: plLoading } = useQuery<PLReport>({
    queryKey: queryKeys.reports.profitLoss(String(resolvedFyId)),
    queryFn: () => api.get(`/reports/profit-loss?fy_id=${resolvedFyId}`),
    enabled: tab === 'pl' && resolvedFyId != null,
  })

  const { data: bs, isLoading: bsLoading } = useQuery<BSReport>({
    queryKey: queryKeys.reports.balanceSheet(String(resolvedFyId)),
    queryFn: () => api.get(`/reports/balance-sheet?fy_id=${resolvedFyId}`),
    enabled: tab === 'bs' && resolvedFyId != null,
  })

  const { data: tb, isLoading: tbLoading } = useQuery<TBReport>({
    queryKey: queryKeys.reports.trialBalance(String(resolvedFyId)),
    queryFn: () => api.get(`/reports/trial-balance?fy_id=${resolvedFyId}`),
    enabled: tab === 'tb' && resolvedFyId != null,
  })

  const { data: cf, isLoading: cfLoading } = useQuery<CFReport>({
    queryKey: queryKeys.reports.cashFlow(String(resolvedFyId)),
    queryFn: () => api.get(`/reports/cash-flow?fy_id=${resolvedFyId}`),
    enabled: tab === 'cf' && resolvedFyId != null,
  })

  const { data: accounts = [] } = useQuery<AccountOut[]>({
    queryKey: queryKeys.accounts.list(),
    queryFn: () => api.get('/accounts'),
    enabled: tab === 'cg',
  })

  const investmentAccounts = accounts.filter(a => a.investment_subtype && !a.is_archived)

  const { data: taxRules = [] } = useQuery<TaxRule[]>({
    queryKey: ['tax-rules'],
    queryFn: () => api.get('/tax-rules'),
    enabled: tab === 'cg',
  })

  const cgQueries = useQuery<{ accountId: number; accountName: string; summary: CGSummary }[]>({
    queryKey: ['capital-gains', resolvedFyId, investmentAccounts.map(a => a.id)],
    queryFn: async () => {
      const results = await Promise.all(
        investmentAccounts.map(async a => ({
          accountId: a.id,
          accountName: a.name,
          summary: await api.get<CGSummary>(`/investments/${a.id}/capital-gains?fy_id=${resolvedFyId}`),
        }))
      )
      return results
    },
    enabled: tab === 'cg' && resolvedFyId != null && investmentAccounts.length > 0,
  })

  // Aggregate capital gains
  const allCGEntries = (cgQueries.data ?? []).flatMap(({ accountName, summary }) =>
    summary.entries.map(e => ({ ...e, accountName }))
  )
  const stcgEntries = allCGEntries.filter(e => e.gain_type === 'stcg')
  const ltcgEntries = allCGEntries.filter(e => e.gain_type === 'ltcg')
  const totalSTCG = stcgEntries.reduce((s, e) => s + e.gain, 0)
  const totalLTCG = ltcgEntries.reduce((s, e) => s + e.gain, 0)

  const equityTaxRule = taxRules.find(r => r.asset_type === 'equity')
  const ltcgExemption = equityTaxRule?.ltcg_exemption_paise ?? 12500000 // ₹1.25L

  // ── PDF export ────────────────────────────────────────────────────────────────

  function exportPdf() {
    const reportType = PDF_REPORT_TYPE[tab]
    if (!reportType || !resolvedFyId) return
    window.open(`${BASE}/reports/${reportType}?fy_id=${resolvedFyId}&format=pdf`, '_blank')
  }

  const canExportPdf = PDF_REPORT_TYPE[tab] != null && resolvedFyId != null

  // ── Render ────────────────────────────────────────────────────────────────────

  const selectedFy = fys.find(f => f.id === resolvedFyId)

  return (
    <div className="flex flex-col h-full overflow-hidden">

      {/* Header */}
      <header className="h-14 bg-white border-b border-zinc-200 flex items-center px-6 gap-4 shrink-0">
        <span className="text-sm font-medium text-zinc-900">Reports</span>
        <div className="flex-1" />
        <div className="flex items-center gap-2">
          <span className="text-xs text-zinc-500">Period</span>
          <select
            value={resolvedFyId ?? ''}
            onChange={e => setFyId(e.target.value ? Number(e.target.value) : null)}
            className="text-xs font-medium border border-zinc-200 rounded-lg px-3 py-1.5 bg-white text-zinc-900 focus:outline-none focus:ring-1 focus:ring-zinc-400"
          >
            {fys.map(fy => (
              <option key={fy.id} value={fy.id}>
                {new Date(fy.start_date).getFullYear()}–{String(new Date(fy.end_date).getFullYear()).slice(2)} ({new Date(fy.start_date).toLocaleDateString('en-IN', { month: 'short', year: 'numeric' })} – {new Date(fy.end_date).toLocaleDateString('en-IN', { month: 'short', year: 'numeric' })})
              </option>
            ))}
          </select>
        </div>
        <button
          onClick={exportPdf}
          disabled={!canExportPdf}
          className="flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium text-zinc-700 border border-zinc-200 rounded-lg hover:bg-zinc-50 disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
        >
          <Download className="w-3.5 h-3.5" />
          Export PDF
        </button>
      </header>

      {/* Tab strip */}
      <div className="shrink-0 border-b border-zinc-200 px-6 flex gap-0 bg-white">
        {(Object.keys(TAB_LABELS) as Tab[]).map(t => (
          <button
            key={t}
            onClick={() => setTab(t)}
            className={`text-sm px-4 py-3 border-b-2 transition-all ${
              tab === t
                ? 'border-zinc-900 text-zinc-900 font-medium'
                : 'border-transparent text-zinc-500 hover:text-zinc-700'
            }`}
          >
            {TAB_LABELS[t]}
          </button>
        ))}
      </div>

      {/* Report body */}
      <div className="flex-1 overflow-y-auto px-6 py-6">
        {!resolvedFyId ? (
          <p className="text-sm text-zinc-400 text-center py-12">No financial year found. Set one up in Settings.</p>
        ) : (
          <>
            {/* ── P&L ── */}
            {tab === 'pl' && (
              <div className="max-w-2xl mx-auto">
                <div className="mb-5">
                  <h2 className="text-base font-semibold text-zinc-900">Profit & Loss Statement</h2>
                  {selectedFy && <p className="text-xs text-zinc-500 mt-0.5">For the period {fmtDate(selectedFy.start_date)} – {fmtDate(selectedFy.end_date)}</p>}
                </div>
                <table className="w-full text-sm border-collapse">
                  <tbody>
                    <SectionHeader label="Income" />
                    {plLoading ? <LoadingRows /> : pl?.income_groups.length === 0 ? (
                      <tr><td colSpan={2} className="px-3 py-4 text-sm text-zinc-400 italic pl-5">No income accounts</td></tr>
                    ) : pl?.income_groups.map(g => (
                      <PLGroupBlock key={g.group_name} group={g} collapsed={collapsed.has(`pl-${g.group_name}`)} onToggle={() => toggleGroup(`pl-${g.group_name}`)} />
                    ))}
                    {pl && <TotalRow label="Total Income" amount={pl.total_income} />}

                    <SectionHeader label="Expenses" />
                    {plLoading ? <LoadingRows /> : pl?.expense_groups.map(g => (
                      <PLGroupBlock key={g.group_name} group={g} collapsed={collapsed.has(`pl-${g.group_name}`)} onToggle={() => toggleGroup(`pl-${g.group_name}`)} />
                    ))}
                    {pl && <TotalRow label="Total Expenses" amount={pl.total_expenses} />}
                    {pl && <TotalRow label="Net Profit" amount={pl.net_profit} grand colored />}
                  </tbody>
                </table>
              </div>
            )}

            {/* ── Balance Sheet ── */}
            {tab === 'bs' && (
              <div className="max-w-4xl mx-auto">
                <div className="mb-5">
                  <h2 className="text-base font-semibold text-zinc-900">Balance Sheet</h2>
                  {selectedFy && <p className="text-xs text-zinc-500 mt-0.5">As at {fmtDate(selectedFy.end_date)}</p>}
                </div>
                {bsLoading ? <div className="animate-pulse h-64 bg-zinc-100 rounded-xl" /> : bs && (
                  <>
                    <div className="grid grid-cols-2 gap-8">
                      {/* Liabilities + Equity */}
                      <div>
                        <table className="w-full text-sm border-collapse">
                          <thead><tr className="bg-zinc-50"><th colSpan={2} className="px-3 py-2 text-xs font-semibold text-zinc-500 uppercase tracking-wider text-left">Liabilities & Equity</th></tr></thead>
                          <tbody>
                            {[...bs.liability_sections, ...bs.equity_sections].map(s => (
                              <BSGroupBlock key={s.group_name} section={s} collapsed={collapsed.has(`bs-l-${s.group_name}`)} onToggle={() => toggleGroup(`bs-l-${s.group_name}`)} />
                            ))}
                          </tbody>
                          <tfoot>
                            <tr className="border-t border-zinc-300">
                              <td className="px-3 py-2.5 font-semibold text-zinc-900">Total Liabilities</td>
                              <td className="px-3 py-2.5 text-right font-mono font-semibold text-zinc-900">{rupees(bs.total_liabilities_and_equity)}</td>
                            </tr>
                          </tfoot>
                        </table>
                      </div>
                      {/* Assets */}
                      <div>
                        <table className="w-full text-sm border-collapse">
                          <thead><tr className="bg-zinc-50"><th colSpan={2} className="px-3 py-2 text-xs font-semibold text-zinc-500 uppercase tracking-wider text-left">Assets</th></tr></thead>
                          <tbody>
                            {bs.asset_sections.map(s => (
                              <BSGroupBlock key={s.group_name} section={s} collapsed={collapsed.has(`bs-a-${s.group_name}`)} onToggle={() => toggleGroup(`bs-a-${s.group_name}`)} />
                            ))}
                          </tbody>
                          <tfoot>
                            <tr className="border-t border-zinc-300">
                              <td className="px-3 py-2.5 font-semibold text-zinc-900">Total Assets</td>
                              <td className="px-3 py-2.5 text-right font-mono font-semibold text-zinc-900">{rupees(bs.total_assets)}</td>
                            </tr>
                          </tfoot>
                        </table>
                      </div>
                    </div>
                    <BalanceCheck
                      ok={bs.total_assets === bs.total_liabilities_and_equity}
                      okText="Assets = Liabilities + Equity · Balance sheet is balanced."
                      failText={`Balance sheet is out of balance by ${rupees(Math.abs(bs.total_assets - bs.total_liabilities_and_equity))}.`}
                    />
                  </>
                )}
              </div>
            )}

            {/* ── Trial Balance ── */}
            {tab === 'tb' && (
              <div className="max-w-2xl mx-auto">
                <div className="mb-5">
                  <h2 className="text-base font-semibold text-zinc-900">Trial Balance</h2>
                  {selectedFy && <p className="text-xs text-zinc-500 mt-0.5">As at {fmtDate(selectedFy.end_date)}</p>}
                </div>
                <table className="w-full text-sm border-collapse">
                  <thead>
                    <tr className="bg-zinc-50 text-xs text-zinc-500 uppercase tracking-wider">
                      <th className="px-3 py-2.5 text-left font-medium">Account</th>
                      <th className="px-3 py-2.5 text-left font-medium text-zinc-400">Group</th>
                      <th className="px-3 py-2.5 text-right font-medium">Debit</th>
                      <th className="px-3 py-2.5 text-right font-medium">Credit</th>
                    </tr>
                  </thead>
                  <tbody>
                    {tbLoading ? <LoadingRows cols={4} /> : tb?.rows.map((r, i) => (
                      <tr key={i} className="border-b border-zinc-100 hover:bg-zinc-50">
                        <td className="px-3 py-2 text-zinc-700">{r.account_name}</td>
                        <td className="px-3 py-2 text-xs text-zinc-400">{r.group_name}</td>
                        <td className="px-3 py-2 text-right font-mono text-zinc-700">{r.debit > 0 ? new Intl.NumberFormat('en-IN').format(r.debit / 100) : <span className="text-zinc-300">—</span>}</td>
                        <td className="px-3 py-2 text-right font-mono text-zinc-700">{r.credit > 0 ? new Intl.NumberFormat('en-IN').format(r.credit / 100) : <span className="text-zinc-300">—</span>}</td>
                      </tr>
                    ))}
                  </tbody>
                  {tb && (
                    <tfoot>
                      <tr className="border-t-2 border-b-2 border-zinc-900 bg-zinc-100">
                        <td colSpan={2} className="px-3 py-2.5 font-semibold text-zinc-900">Total</td>
                        <td className="px-3 py-2.5 text-right font-mono font-semibold">{rupees(tb.total_debit)}</td>
                        <td className="px-3 py-2.5 text-right font-mono font-semibold">{rupees(tb.total_credit)}</td>
                      </tr>
                      <tr>
                        <td colSpan={4} className="px-3 pt-2 pb-1">
                          <BalanceCheck
                            ok={tb.total_debit === tb.total_credit}
                            okText="Debits = Credits · Books are balanced."
                            failText={`Imbalance of ${rupees(Math.abs(tb.total_debit - tb.total_credit))}.`}
                          />
                        </td>
                      </tr>
                    </tfoot>
                  )}
                </table>
              </div>
            )}

            {/* ── Cash Flow ── */}
            {tab === 'cf' && (
              <div className="max-w-2xl mx-auto">
                <div className="mb-5">
                  <h2 className="text-base font-semibold text-zinc-900">Cash Flow Statement</h2>
                  {selectedFy && <p className="text-xs text-zinc-500 mt-0.5">For the period {fmtDate(selectedFy.start_date)} – {fmtDate(selectedFy.end_date)}</p>}
                </div>
                {cfLoading ? <div className="animate-pulse h-64 bg-zinc-100 rounded-xl" /> : cf && (
                  <table className="w-full text-sm border-collapse">
                    <tbody>
                      {cf.sections.map(section => (
                        <>
                          <tr key={`h-${section.tag}`} className="bg-zinc-50">
                            <td colSpan={2} className="px-3 py-2 text-xs font-semibold text-zinc-500 uppercase tracking-wider capitalize">
                              {section.tag} Activities
                            </td>
                          </tr>
                          {section.items.length === 0 ? (
                            <tr key={`empty-${section.tag}`} className="border-b border-zinc-100">
                              <td className="px-3 py-2 pl-5 text-zinc-400 italic">No activity</td>
                              <td className="px-3 py-2 text-right font-mono text-zinc-400">—</td>
                            </tr>
                          ) : section.items.map((item, i) => (
                            <tr key={i} className="border-b border-zinc-100 hover:bg-zinc-50">
                              <td className="px-3 py-2 pl-5 text-zinc-600">{item.label}</td>
                              <td className={`px-3 py-2 text-right font-mono ${item.amount < 0 ? 'text-red-600' : 'text-zinc-900'}`}>
                                {item.amount < 0 ? `(${rupees(item.amount)})` : rupees(item.amount)}
                              </td>
                            </tr>
                          ))}
                          <tr key={`s-${section.tag}`} className="border-t border-zinc-300">
                            <td className="px-3 py-2.5 pl-5 font-medium text-zinc-900">
                              Cash from {section.tag.charAt(0).toUpperCase() + section.tag.slice(1)}
                            </td>
                            <td className={`px-3 py-2.5 text-right font-mono font-medium ${section.subtotal < 0 ? 'text-red-600' : 'text-zinc-900'}`}>
                              {section.subtotal < 0 ? `(${rupees(section.subtotal)})` : rupees(section.subtotal)}
                            </td>
                          </tr>
                        </>
                      ))}
                      <tr className="border-t-2 border-b-2 border-zinc-900 bg-zinc-100">
                        <td className="px-3 py-3 font-semibold text-zinc-900">Net Change in Cash</td>
                        <td className={`px-3 py-3 text-right font-mono font-semibold ${cf.net_change_in_cash < 0 ? 'text-red-600' : 'text-emerald-700'}`}>
                          {cf.net_change_in_cash < 0 ? `(${rupees(cf.net_change_in_cash)})` : rupees(cf.net_change_in_cash)}
                        </td>
                      </tr>
                      <tr className="border-b border-zinc-100 hover:bg-zinc-50">
                        <td className="px-3 py-2 pl-5 text-zinc-600">Opening Cash & Bank Balance</td>
                        <td className="px-3 py-2 text-right font-mono text-zinc-700">{rupees(cf.opening_cash)}</td>
                      </tr>
                      <tr className="border-t border-zinc-300">
                        <td className="px-3 py-2.5 font-semibold text-zinc-900">Closing Cash & Bank Balance</td>
                        <td className="px-3 py-2.5 text-right font-mono font-semibold text-zinc-900">{rupees(cf.closing_cash)}</td>
                      </tr>
                    </tbody>
                  </table>
                )}
              </div>
            )}

            {/* ── Capital Gains ── */}
            {tab === 'cg' && (
              <div className="max-w-3xl mx-auto">
                <div className="mb-5 flex items-start justify-between">
                  <div>
                    <h2 className="text-base font-semibold text-zinc-900">Capital Gains Report</h2>
                    {selectedFy && <p className="text-xs text-zinc-500 mt-0.5">FY {new Date(selectedFy.start_date).getFullYear()}–{String(new Date(selectedFy.end_date).getFullYear()).slice(2)} · For ITR Schedule CG</p>}
                  </div>
                  {allCGEntries.length > 0 && (
                    <div className="flex flex-col items-end gap-1">
                      <div className="flex items-center gap-4 text-xs">
                        <span className="text-zinc-500">Total STCG <span className="font-mono font-medium text-amber-700">{rupees(totalSTCG)}</span></span>
                        <span className="text-zinc-500">Total LTCG <span className="font-mono font-medium text-emerald-700">{rupees(totalLTCG)}</span></span>
                      </div>
                      <div className="text-xs text-zinc-400">
                        LTCG exemption used: {rupees(totalLTCG)} of {rupees(ltcgExemption)}
                      </div>
                    </div>
                  )}
                </div>

                {investmentAccounts.length === 0 ? (
                  <NoData />
                ) : cgQueries.isLoading ? (
                  <div className="animate-pulse h-32 bg-zinc-100 rounded-xl" />
                ) : (
                  <>
                    {/* STCG */}
                    <div className="mb-6">
                      <div className="flex items-center gap-2 mb-3">
                        <span className="text-xs font-semibold text-amber-700 uppercase tracking-wider">Short-Term Capital Gains (STCG)</span>
                        <span className="text-xs text-zinc-400">held &lt; 12 months · taxed at 20%</span>
                      </div>
                      {stcgEntries.length === 0 ? (
                        <p className="text-sm text-zinc-400 italic py-3">No short-term gains this period.</p>
                      ) : (
                        <table className="w-full text-sm border-collapse">
                          <thead>
                            <tr className="bg-zinc-50 text-xs text-zinc-500 uppercase tracking-wider">
                              <th className="px-3 py-2.5 text-left font-medium">Instrument</th>
                              <th className="px-3 py-2.5 text-right font-medium">Units sold</th>
                              <th className="px-3 py-2.5 text-right font-medium">Sale date</th>
                              <th className="px-3 py-2.5 text-right font-medium">Sale price/unit</th>
                              <th className="px-3 py-2.5 text-right font-medium">Gain / Loss</th>
                            </tr>
                          </thead>
                          <tbody>
                            {stcgEntries.map(e => (
                              <tr key={e.id} className="border-b border-zinc-100 hover:bg-zinc-50">
                                <td className="px-3 py-2.5 font-medium text-zinc-900">{e.accountName}</td>
                                <td className="px-3 py-2.5 text-right font-mono text-zinc-700">{e.units_sold}</td>
                                <td className="px-3 py-2.5 text-right font-mono text-xs text-zinc-500">{fmtDateShort(e.sale_date)}</td>
                                <td className="px-3 py-2.5 text-right font-mono text-zinc-700">{rupees(e.sale_price_per_unit)}</td>
                                <td className={`px-3 py-2.5 text-right font-mono font-medium ${e.gain > 0 ? 'text-emerald-700' : e.gain < 0 ? 'text-red-600' : 'text-zinc-400'}`}>
                                  {e.gain > 0 ? `+${rupees(e.gain)}` : e.gain < 0 ? `(${rupees(e.gain)})` : '—'}
                                </td>
                              </tr>
                            ))}
                          </tbody>
                          <tfoot>
                            <tr className="border-t border-zinc-300">
                              <td colSpan={4} className="px-3 py-2.5 font-semibold text-zinc-900">Total STCG</td>
                              <td className="px-3 py-2.5 text-right font-mono font-semibold text-amber-700">{rupees(totalSTCG)}</td>
                            </tr>
                          </tfoot>
                        </table>
                      )}
                    </div>

                    {/* LTCG */}
                    <div>
                      <div className="flex items-center gap-2 mb-3">
                        <span className="text-xs font-semibold text-emerald-700 uppercase tracking-wider">Long-Term Capital Gains (LTCG)</span>
                        <span className="text-xs text-zinc-400">held ≥ 12 months · 12.5% above ₹1.25L exemption</span>
                      </div>
                      {ltcgEntries.length === 0 ? (
                        <p className="text-sm text-zinc-400 italic py-3">No long-term gains this period.</p>
                      ) : (
                        <>
                          <table className="w-full text-sm border-collapse">
                            <thead>
                              <tr className="bg-zinc-50 text-xs text-zinc-500 uppercase tracking-wider">
                                <th className="px-3 py-2.5 text-left font-medium">Instrument</th>
                                <th className="px-3 py-2.5 text-right font-medium">Units sold</th>
                                <th className="px-3 py-2.5 text-right font-medium">Sale date</th>
                                <th className="px-3 py-2.5 text-right font-medium">Sale price/unit</th>
                                <th className="px-3 py-2.5 text-right font-medium">Gain / Loss</th>
                              </tr>
                            </thead>
                            <tbody>
                              {ltcgEntries.map(e => (
                                <tr key={e.id} className="border-b border-zinc-100 hover:bg-zinc-50">
                                  <td className="px-3 py-2.5 font-medium text-zinc-900">{e.accountName}</td>
                                  <td className="px-3 py-2.5 text-right font-mono text-zinc-700">{e.units_sold}</td>
                                  <td className="px-3 py-2.5 text-right font-mono text-xs text-zinc-500">{fmtDateShort(e.sale_date)}</td>
                                  <td className="px-3 py-2.5 text-right font-mono text-zinc-700">{rupees(e.sale_price_per_unit)}</td>
                                  <td className={`px-3 py-2.5 text-right font-mono font-medium ${e.gain > 0 ? 'text-emerald-700' : e.gain < 0 ? 'text-red-600' : 'text-zinc-400'}`}>
                                    {e.gain > 0 ? `+${rupees(e.gain)}` : e.gain < 0 ? `(${rupees(e.gain)})` : '—'}
                                  </td>
                                </tr>
                              ))}
                            </tbody>
                            <tfoot>
                              <tr className="border-t border-zinc-300">
                                <td colSpan={4} className="px-3 py-2.5 font-semibold text-zinc-900">Total LTCG</td>
                                <td className="px-3 py-2.5 text-right font-mono font-semibold text-emerald-700">{rupees(totalLTCG)}</td>
                              </tr>
                            </tfoot>
                          </table>
                          <div className="mt-3 text-xs text-zinc-500 bg-zinc-50 rounded-xl px-4 py-3 border border-zinc-200">
                            {totalLTCG <= ltcgExemption
                              ? <>{rupees(totalLTCG)} LTCG is within the {rupees(ltcgExemption)} annual exemption. <span className="font-medium text-zinc-700">Tax payable on LTCG: ₹0.</span></>
                              : <>Taxable LTCG: <span className="font-medium text-zinc-700">{rupees(totalLTCG - ltcgExemption)}</span> (after {rupees(ltcgExemption)} exemption). Tax @ 12.5%: <span className="font-medium text-zinc-700">{rupees((totalLTCG - ltcgExemption) * 0.125)}</span>.</>
                            }
                          </div>
                        </>
                      )}
                    </div>
                  </>
                )}
              </div>
            )}
          </>
        )}
      </div>
    </div>
  )
}
