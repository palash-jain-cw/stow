import { useState, useRef, useMemo } from 'react'
import { Link } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import {
  UploadCloud, FileText, X, ChevronDown, Check, AlertTriangle,
  CheckCircle2, Zap, Info,
} from 'lucide-react'
import { api, queryKeys } from '../api/api'
import { MonoAmount } from '../components/MonoAmount'

// ── Types ─────────────────────────────────────────────────────────────────────

interface AccountOut {
  id: number
  name: string
  group_name: string
  nature: string
  is_archived: boolean
}

interface FinancialYear {
  id: number
  start_date: string
  end_date: string
  status: string
}

interface BatchOut {
  id: number
  filename: string
  detected_bank: string | null
  statement_from: string | null
  statement_to: string | null
  status: string
  row_count: number
}

interface StagingRowOut {
  id: number
  date: string
  amount: number
  description: string
  suggested_account_id: number | null
  status: string
  narration_override: string | null
  tags: string[] | null
  possible_duplicate: boolean
  matched_transaction_id: number | null
}

interface RowDraft {
  id: number
  date: string
  amount: number
  description: string
  possible_duplicate: boolean
  matched_transaction_id: number | null
  status: 'pending' | 'confirmed' | 'discarded' | 'reconciled'
  accountId: number | null
  originalAccountId: number | null
  narration: string
  tags: string
}

type Filter = 'all' | 'new' | 'dup' | 'matched'
type Step = 1 | 2 | 3 | 'done'

// ── Constants ─────────────────────────────────────────────────────────────────

const PARSE_STEPS = [
  'Reading file…',
  'Extracting text…',
  'Identifying bank & format…',
  'Parsing transactions…',
  'Mapping accounts…',
  'Done',
]

// ── Helpers ───────────────────────────────────────────────────────────────────

function toRowDrafts(rows: StagingRowOut[]): RowDraft[] {
  return rows.map(r => ({
    id: r.id,
    date: r.date,
    amount: r.amount,
    description: r.description,
    possible_duplicate: r.possible_duplicate,
    matched_transaction_id: r.matched_transaction_id,
    status: r.status as RowDraft['status'],
    accountId: r.suggested_account_id,
    originalAccountId: r.suggested_account_id,
    narration: r.narration_override ?? r.description,
    tags: r.tags ? r.tags.join(', ') : '',
  }))
}

function formatFileSize(bytes: number) {
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 * 1024) return `${Math.round(bytes / 1024)} KB`
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`
}

function formatDate(iso: string) {
  return new Date(iso).toLocaleDateString('en-IN', { day: 'numeric', month: 'short', year: 'numeric' })
}

// ── Step indicator ────────────────────────────────────────────────────────────

function StepIndicator({ current }: { current: Step }) {
  const steps = [{ n: 1, label: 'Upload' }, { n: 2, label: 'Review' }, { n: 3, label: 'Confirm' }]
  return (
    <div className="flex items-center gap-2">
      {steps.map((s, i) => {
        const done = (typeof current === 'number' && current > s.n) || current === 'done'
        const active = current === s.n
        return (
          <div key={s.n} className="flex items-center gap-2">
            {i > 0 && <div className="w-6 h-px bg-zinc-200" />}
            <div className="flex items-center gap-1.5">
              <div className={`w-5 h-5 rounded-full flex items-center justify-center text-xs font-medium transition-colors ${done || active ? 'bg-zinc-900 text-white' : 'bg-zinc-200 text-zinc-400'}`}>
                {done ? <Check className="w-3 h-3" strokeWidth={3} /> : s.n}
              </div>
              <span className={`text-xs ${active ? 'font-medium text-zinc-900' : done ? 'text-zinc-500' : 'text-zinc-400'}`}>{s.label}</span>
            </div>
          </div>
        )
      })}
    </div>
  )
}

// ── Status badge ──────────────────────────────────────────────────────────────

function StatusBadge({ row }: { row: RowDraft }) {
  if (row.status === 'reconciled') return <span className="text-xs px-2 py-0.5 rounded-full font-medium bg-emerald-100 text-emerald-700">Matched</span>
  if (row.status === 'confirmed')  return <span className="text-xs px-2 py-0.5 rounded-full font-medium bg-emerald-50 text-emerald-600">Accepted</span>
  if (row.status === 'discarded')  return <span className="text-xs px-2 py-0.5 rounded-full font-medium bg-zinc-100 text-zinc-500">Ignored</span>
  if (row.possible_duplicate)      return <span className="text-xs px-2 py-0.5 rounded-full font-medium bg-amber-100 text-amber-700">Possible duplicate</span>
  return <span className="text-xs px-2 py-0.5 rounded-full font-medium bg-blue-100 text-blue-700">New</span>
}

// ── Main component ────────────────────────────────────────────────────────────

export default function Import() {
  const { data: accounts = [] } = useQuery<AccountOut[]>({
    queryKey: queryKeys.accounts.list(),
    queryFn: () => api.get('/accounts'),
  })

  const { data: fys = [] } = useQuery<FinancialYear[]>({
    queryKey: queryKeys.financialYears.all(),
    queryFn: () => api.get('/financial-years'),
  })

  const activeFy = fys.find(fy => fy.status === 'active')
  const activeAccounts = accounts.filter(a => !a.is_archived)

  // ── Wizard state ──────────────────────────────────────────────────────────

  const [step, setStep] = useState<Step>(1)
  const [bankAccountId, setBankAccountId] = useState<number | ''>('')
  const [file, setFile] = useState<File | null>(null)
  const [uploading, setUploading] = useState(false)
  const [parseStatusIdx, setParseStatusIdx] = useState(0)
  const [uploadError, setUploadError] = useState<string | null>(null)
  const [batch, setBatch] = useState<BatchOut | null>(null)
  const [rowDrafts, setRowDrafts] = useState<RowDraft[]>([])
  const [filter, setFilter] = useState<Filter>('all')
  const [expandedRowId, setExpandedRowId] = useState<number | null>(null)
  const [posting, setPosting] = useState(false)
  const [postError, setPostError] = useState<string | null>(null)
  const [confirmResult, setConfirmResult] = useState<{ posted: number; reconciled: number; skipped: number } | null>(null)
  const [checkedRules, setCheckedRules] = useState<Set<string>>(new Set())

  const fileInputRef = useRef<HTMLInputElement>(null)
  const dropZoneRef = useRef<HTMLDivElement>(null)
  const parseTimerRef = useRef<ReturnType<typeof setInterval> | null>(null)

  // ── Merchant rule candidates ──────────────────────────────────────────────

  const newRuleCandidates = useMemo(() => {
    const seen = new Map<string, { description: string; accountId: number }>()
    for (const r of rowDrafts) {
      if (r.originalAccountId === null && r.accountId !== null && !seen.has(r.description)) {
        seen.set(r.description, { description: r.description, accountId: r.accountId })
      }
    }
    return [...seen.values()]
  }, [rowDrafts])

  // ── File pick ─────────────────────────────────────────────────────────────

  function pickFile(f: File) {
    if (!f.name.toLowerCase().endsWith('.pdf')) {
      setUploadError('Only PDF files are supported.')
      return
    }
    setFile(f)
    setUploadError(null)
  }

  function handleDragOver(e: React.DragEvent) {
    e.preventDefault()
    dropZoneRef.current?.classList.add('!border-zinc-900')
  }

  function handleDragLeave() {
    dropZoneRef.current?.classList.remove('!border-zinc-900')
  }

  function handleDrop(e: React.DragEvent) {
    e.preventDefault()
    dropZoneRef.current?.classList.remove('!border-zinc-900')
    const f = e.dataTransfer.files[0]
    if (f) pickFile(f)
  }

  // ── Upload / parse ────────────────────────────────────────────────────────

  async function handleParse() {
    if (!file || bankAccountId === '') return
    setUploading(true)
    setParseStatusIdx(0)
    setUploadError(null)

    parseTimerRef.current = setInterval(() => {
      setParseStatusIdx(i => Math.min(i + 1, PARSE_STEPS.length - 2))
    }, 620)

    try {
      const fd = new FormData()
      fd.append('file', file)
      const result = await api.upload<BatchOut>('/imports', fd)

      clearInterval(parseTimerRef.current!)
      setParseStatusIdx(PARSE_STEPS.length - 1)

      const rows = await api.get<StagingRowOut[]>(`/imports/${result.id}/rows`)
      setBatch(result)
      setRowDrafts(toRowDrafts(rows))
      setCheckedRules(new Set(
        rows.filter(r => r.suggested_account_id === null).map(r => r.description)
      ))

      setTimeout(() => { setStep(2); setUploading(false) }, 500)
    } catch (e) {
      clearInterval(parseTimerRef.current!)
      setUploading(false)
      setUploadError(e instanceof Error ? e.message : 'Upload failed')
    }
  }

  // ── Row mutations (optimistic) ────────────────────────────────────────────

  function patchRow(id: number, patch: Partial<RowDraft>) {
    setRowDrafts(prev => prev.map(r => r.id === id ? { ...r, ...patch } : r))
  }

  function updateRowRemote(id: number, body: Record<string, unknown>) {
    if (!batch) return
    api.put(`/imports/${batch.id}/rows/${id}`, body).catch(() => {/* silent — optimistic */})
  }

  function acceptRow(row: RowDraft) {
    if (!row.accountId) return
    patchRow(row.id, { status: 'confirmed' })
    updateRowRemote(row.id, { status: 'confirmed', suggested_account_id: row.accountId })
    setExpandedRowId(null)
  }

  function discardRow(row: RowDraft) {
    patchRow(row.id, { status: 'discarded' })
    updateRowRemote(row.id, { status: 'discarded' })
    setExpandedRowId(null)
  }

  function setRowAccount(row: RowDraft, accountId: number | null) {
    patchRow(row.id, { accountId })
    if (accountId !== null) updateRowRemote(row.id, { suggested_account_id: accountId })
    // Track new rule candidate
    if (row.originalAccountId === null && accountId !== null) {
      setCheckedRules(prev => new Set([...prev, row.description]))
    }
  }

  function setRowNarration(row: RowDraft, narration: string) {
    patchRow(row.id, { narration })
    updateRowRemote(row.id, { narration_override: narration })
  }

  function setRowTags(row: RowDraft, tags: string) {
    patchRow(row.id, { tags })
    updateRowRemote(row.id, { tags: tags.split(',').map(t => t.trim()).filter(Boolean) })
  }

  // ── Derived counts ────────────────────────────────────────────────────────

  const counts = useMemo(() => ({
    all:      rowDrafts.length,
    new:      rowDrafts.filter(r => r.status === 'pending' && !r.possible_duplicate).length,
    dup:      rowDrafts.filter(r => r.possible_duplicate).length,
    matched:  rowDrafts.filter(r => r.status === 'reconciled').length,
    accepted: rowDrafts.filter(r => r.status === 'confirmed').length,
    ignored:  rowDrafts.filter(r => r.status === 'discarded').length,
    pending:  rowDrafts.filter(r => r.status === 'pending').length,
  }), [rowDrafts])

  const filteredRows = useMemo(() => {
    if (filter === 'new')     return rowDrafts.filter(r => r.status === 'pending' && !r.possible_duplicate)
    if (filter === 'dup')     return rowDrafts.filter(r => r.possible_duplicate)
    if (filter === 'matched') return rowDrafts.filter(r => r.status === 'reconciled')
    return rowDrafts
  }, [rowDrafts, filter])

  const confirmCounts = useMemo(() => ({
    posted:    rowDrafts.filter(r => r.status === 'confirmed').length,
    reconciled: rowDrafts.filter(r => r.status === 'reconciled').length,
    skipped:   rowDrafts.filter(r => r.status === 'discarded' || r.status === 'pending').length,
    netInflow: rowDrafts.filter(r => r.status === 'confirmed').reduce((s, r) => s + r.amount, 0),
  }), [rowDrafts])

  // ── Post ──────────────────────────────────────────────────────────────────

  async function handlePost() {
    if (!batch || bankAccountId === '') return
    setPosting(true)
    setPostError(null)
    try {
      for (const candidate of newRuleCandidates) {
        if (checkedRules.has(candidate.description)) {
          await api.post('/merchant-rules', { pattern: candidate.description, account_id: candidate.accountId })
        }
      }
      const result = await api.post<{ posted_count: number }>(
        `/imports/${batch.id}/confirm`,
        { bank_account_id: bankAccountId }
      )
      setConfirmResult({ posted: result.posted_count, reconciled: confirmCounts.reconciled, skipped: confirmCounts.skipped })
      setStep('done')
    } catch (e) {
      setPostError(e instanceof Error ? e.message : 'Failed to post')
    } finally {
      setPosting(false)
    }
  }

  // ── Reset ─────────────────────────────────────────────────────────────────

  function reset() {
    setStep(1); setBankAccountId(''); setFile(null); setUploading(false)
    setParseStatusIdx(0); setUploadError(null); setBatch(null); setRowDrafts([])
    setFilter('all'); setExpandedRowId(null); setConfirmResult(null); setPostError(null)
    setCheckedRules(new Set())
  }

  // ── Render ────────────────────────────────────────────────────────────────

  return (
    <div className="flex flex-col h-full overflow-hidden">

      {/* Header */}
      <header className="h-14 bg-white border-b border-zinc-200 flex items-center px-6 gap-6 shrink-0">
        <span className="text-sm font-medium text-zinc-900">Bank Import</span>
        {step !== 'done' && <StepIndicator current={step} />}
      </header>

      {/* ── Step 1: Upload ── */}
      {step === 1 && (
        <div className="flex-1 overflow-y-auto flex items-start justify-center pt-12 pb-8 px-4">
          <div className="w-full max-w-lg flex flex-col gap-6">

            {/* 1. Bank account selector */}
            <div>
              <label className="block text-xs font-semibold text-zinc-500 uppercase tracking-wide mb-2">
                Statement for account
              </label>
              <select
                value={bankAccountId}
                onChange={e => setBankAccountId(e.target.value === '' ? '' : Number(e.target.value))}
                disabled={uploading}
                className="w-full px-3.5 py-2.5 text-sm border border-zinc-200 rounded-xl focus:outline-none focus:ring-2 focus:ring-blue-500 bg-white disabled:opacity-50"
              >
                <option value="">Select your bank account…</option>
                {activeAccounts.filter(a => a.nature === 'asset').map(a => (
                  <option key={a.id} value={a.id}>{a.name} — {a.group_name}</option>
                ))}
                {activeAccounts.some(a => a.nature !== 'asset') && (
                  <optgroup label="Other accounts">
                    {activeAccounts.filter(a => a.nature !== 'asset').map(a => (
                      <option key={a.id} value={a.id}>{a.name} — {a.group_name}</option>
                    ))}
                  </optgroup>
                )}
              </select>
            </div>

            {/* 2. Drop zone */}
            <div
              ref={dropZoneRef}
              onDragOver={handleDragOver}
              onDragLeave={handleDragLeave}
              onDrop={handleDrop}
              onClick={() => !uploading && fileInputRef.current?.click()}
              className={`border-2 border-dashed rounded-2xl p-10 flex flex-col items-center gap-4 transition-colors select-none ${
                uploading ? 'opacity-60 cursor-not-allowed' : 'cursor-pointer'
              } ${file ? 'border-zinc-900 border-solid' : 'border-zinc-200 hover:border-zinc-400'}`}
            >
              <div className="w-12 h-12 rounded-full bg-zinc-100 flex items-center justify-center">
                <UploadCloud className="w-6 h-6 text-zinc-400" />
              </div>
              <div className="text-center">
                <p className="text-sm font-medium text-zinc-900">Drop your bank statement here</p>
                <p className="text-xs text-zinc-500 mt-1">
                  PDF · Axis Bank, HDFC, Bank of India, AU Small Finance, Union Bank
                </p>
              </div>
              <span className="text-xs font-medium text-zinc-900 underline underline-offset-2">Browse file</span>
              <input
                ref={fileInputRef}
                type="file"
                accept=".pdf"
                className="hidden"
                onChange={e => { const f = e.target.files?.[0]; if (f) pickFile(f) }}
              />
            </div>

            {/* Selected file chip */}
            {file && !uploading && (
              <div className="flex items-center gap-3 px-4 py-3 rounded-xl border border-zinc-200 bg-zinc-50">
                <div className="w-8 h-8 rounded-lg bg-zinc-200 flex items-center justify-center shrink-0">
                  <FileText className="w-4 h-4 text-zinc-600" />
                </div>
                <div className="flex-1 min-w-0">
                  <p className="text-sm font-medium text-zinc-900 truncate">{file.name}</p>
                  <p className="text-xs text-zinc-500">{formatFileSize(file.size)}</p>
                </div>
                <button
                  onClick={e => { e.stopPropagation(); setFile(null) }}
                  className="text-zinc-400 hover:text-zinc-700 transition-colors"
                >
                  <X className="w-4 h-4" />
                </button>
              </div>
            )}

            {/* Parse button */}
            {file && !uploading && (
              <button
                onClick={handleParse}
                disabled={bankAccountId === ''}
                className="w-full py-2.5 rounded-xl bg-zinc-900 text-white text-sm font-medium hover:bg-zinc-700 disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
              >
                Parse statement
              </button>
            )}

            {/* Progress */}
            {uploading && (
              <div className="flex flex-col gap-3">
                <div className="flex items-center gap-3">
                  <div className="w-5 h-5 rounded-full border-2 border-zinc-200 border-t-zinc-900 animate-spin shrink-0" />
                  <p className="text-sm text-zinc-600">{PARSE_STEPS[parseStatusIdx]}</p>
                </div>
                <div className="h-1.5 rounded-full bg-zinc-100 overflow-hidden">
                  <div
                    className="h-full bg-zinc-900 rounded-full transition-all duration-500"
                    style={{ width: `${Math.round((parseStatusIdx / (PARSE_STEPS.length - 1)) * 100)}%` }}
                  />
                </div>
              </div>
            )}

            {uploadError && (
              <p className="text-sm text-red-600 bg-red-50 px-3 py-2 rounded-lg">{uploadError}</p>
            )}
          </div>
        </div>
      )}

      {/* ── Step 2: Review ── */}
      {step === 2 && batch && (
        <div className="flex-1 flex flex-col overflow-hidden">

          {/* Sub-header */}
          <div className="shrink-0 border-b border-zinc-100 px-6 py-3 flex items-center gap-4 flex-wrap bg-white">
            <div className="flex items-center gap-2 text-xs">
              {batch.detected_bank && (
                <span className="font-medium text-zinc-900">{batch.detected_bank}</span>
              )}
              {batch.statement_from && batch.statement_to && (
                <span className="text-zinc-500">
                  {formatDate(batch.statement_from)} – {formatDate(batch.statement_to)}
                </span>
              )}
            </div>
            <div className="flex items-center gap-2 ml-auto">
              {(['all', 'new', 'dup', 'matched'] as Filter[]).map(f => {
                const label = f === 'all' ? `All ${counts.all}` : f === 'new' ? `New ${counts.new}` : f === 'dup' ? `Duplicates ${counts.dup}` : `Matched ${counts.matched}`
                return (
                  <button key={f} onClick={() => setFilter(f)}
                    className={`text-xs px-3 py-1 rounded-full font-medium transition-colors ${filter === f ? 'bg-zinc-900 text-white' : 'bg-zinc-100 text-zinc-600 hover:bg-zinc-200'}`}
                  >
                    {label}
                  </button>
                )
              })}
            </div>
          </div>

          {/* Info banner */}
          <div className="shrink-0 bg-blue-50 border-b border-blue-100 px-6 py-2 flex items-center gap-2">
            <Info className="w-3.5 h-3.5 text-blue-500 shrink-0" />
            <p className="text-xs text-blue-700">Review account mappings below. Rows without a mapped account won't be imported.</p>
          </div>

          {/* Table */}
          <div className="flex-1 overflow-y-auto">
            <table className="w-full text-sm border-collapse">
              <thead className="sticky top-0 bg-white border-b border-zinc-200 z-10">
                <tr className="text-xs text-zinc-500 uppercase tracking-wide">
                  <th className="px-6 py-2.5 text-left font-medium">Date</th>
                  <th className="px-3 py-2.5 text-left font-medium">Description</th>
                  <th className="px-3 py-2.5 text-right font-medium">Amount</th>
                  <th className="px-3 py-2.5 text-left font-medium">Account</th>
                  <th className="px-3 py-2.5 text-left font-medium">Status</th>
                  <th className="pr-6 py-2.5 w-6" />
                </tr>
              </thead>
              <tbody>
                {filteredRows.map(row => {
                  const isExpanded = expandedRowId === row.id
                  return (
                    <>
                      <tr
                        key={row.id}
                        onClick={() => setExpandedRowId(isExpanded ? null : row.id)}
                        className={`border-b border-zinc-100 cursor-pointer transition-colors ${
                          row.status === 'discarded'  ? 'opacity-40' :
                          row.status === 'reconciled' ? 'bg-emerald-50/60' :
                          row.possible_duplicate      ? 'bg-amber-50/50' :
                          isExpanded                  ? 'bg-blue-50/50' :
                          'hover:bg-zinc-50'
                        }`}
                      >
                        <td className="px-6 py-3 font-mono text-xs text-zinc-600 whitespace-nowrap">{formatDate(row.date)}</td>
                        <td className="px-3 py-3 max-w-xs">
                          <p className="text-sm font-medium text-zinc-900 truncate">{row.description}</p>
                        </td>
                        <td className="px-3 py-3 text-right">
                          <MonoAmount amount={row.amount} className="text-sm" />
                        </td>
                        <td className="px-3 py-3" onClick={e => e.stopPropagation()}>
                          {row.status === 'reconciled' ? (
                            <span className="text-xs text-emerald-700 font-medium">Reconciled</span>
                          ) : (
                            <div className="flex items-center gap-1.5">
                              <select
                                value={row.accountId ?? ''}
                                onChange={e => setRowAccount(row, e.target.value === '' ? null : Number(e.target.value))}
                                className="text-xs border border-zinc-200 rounded-lg px-2.5 py-1.5 bg-white focus:outline-none focus:ring-1 focus:ring-zinc-400 max-w-[180px]"
                              >
                                <option value="">— pick account —</option>
                                {activeAccounts.map(a => <option key={a.id} value={a.id}>{a.name}</option>)}
                              </select>
                              {row.originalAccountId !== null && row.accountId === row.originalAccountId && (
                                <Zap className="w-3 h-3 text-zinc-400 shrink-0" title="Applied from merchant rule" />
                              )}
                            </div>
                          )}
                        </td>
                        <td className="px-3 py-3"><StatusBadge row={row} /></td>
                        <td className="pr-6 py-3 text-right">
                          <ChevronDown className={`w-4 h-4 text-zinc-400 transition-transform duration-200 ${isExpanded ? 'rotate-180' : ''}`} />
                        </td>
                      </tr>

                      {isExpanded && (
                        <tr key={`${row.id}-d`} className="border-b border-zinc-100">
                          <td colSpan={6} className="p-0">
                            {row.status === 'reconciled' ? (
                              <div className="px-6 py-3 bg-emerald-50 flex items-center gap-2 text-xs">
                                <CheckCircle2 className="w-3.5 h-3.5 text-emerald-600 shrink-0" />
                                <p className="text-emerald-800">Matched to an existing transaction. This row will be marked reconciled — no new transaction created.</p>
                              </div>
                            ) : row.possible_duplicate ? (
                              <div className="px-6 py-3 bg-amber-50 border-l-2 border-amber-400 flex flex-col gap-3 text-xs">
                                <div className="flex items-start gap-2">
                                  <AlertTriangle className="w-3.5 h-3.5 text-amber-500 shrink-0 mt-0.5" />
                                  <p className="text-amber-800">A transaction with the same amount on a nearby date may already exist.</p>
                                </div>
                                <div className="flex items-center gap-2 ml-5" onClick={e => e.stopPropagation()}>
                                  <button onClick={() => discardRow(row)}
                                    className="px-3 py-1.5 text-xs font-medium text-amber-800 bg-amber-100 border border-amber-300 rounded-lg hover:bg-amber-200 transition-colors">
                                    Skip (it's a duplicate)
                                  </button>
                                  <button onClick={() => acceptRow(row)} disabled={!row.accountId}
                                    className="px-3 py-1.5 text-xs font-medium text-white bg-zinc-900 rounded-lg hover:bg-zinc-700 disabled:opacity-40 transition-colors">
                                    Import anyway
                                  </button>
                                </div>
                              </div>
                            ) : (
                              <div className="px-6 py-3 bg-zinc-50 flex items-start gap-8 text-xs" onClick={e => e.stopPropagation()}>
                                <div>
                                  <p className="text-zinc-500 mb-1">Narration</p>
                                  <input type="text" defaultValue={row.narration} onBlur={e => setRowNarration(row, e.target.value)}
                                    className="border border-zinc-200 rounded-lg px-2.5 py-1.5 text-zinc-900 bg-white focus:outline-none focus:ring-1 focus:ring-zinc-400 w-64" />
                                </div>
                                <div>
                                  <p className="text-zinc-500 mb-1">Tags</p>
                                  <input type="text" defaultValue={row.tags} placeholder="e.g. utilities, home"
                                    onBlur={e => setRowTags(row, e.target.value)}
                                    className="border border-zinc-200 rounded-lg px-2.5 py-1.5 text-zinc-500 bg-white focus:outline-none focus:ring-1 focus:ring-zinc-400 w-40" />
                                </div>
                                <div className="ml-auto flex items-center gap-2 pt-4">
                                  <button onClick={() => discardRow(row)}
                                    className="px-3 py-1.5 text-xs text-zinc-600 border border-zinc-200 rounded-lg hover:bg-zinc-100 transition-colors">
                                    Ignore
                                  </button>
                                  <button onClick={() => acceptRow(row)} disabled={!row.accountId}
                                    className="px-3 py-1.5 text-xs font-medium text-white bg-zinc-900 rounded-lg hover:bg-zinc-700 disabled:opacity-40 transition-colors">
                                    Accept
                                  </button>
                                </div>
                              </div>
                            )}
                          </td>
                        </tr>
                      )}
                    </>
                  )
                })}
              </tbody>
            </table>
          </div>

          {/* Bottom bar */}
          <div className="shrink-0 border-t border-zinc-200 px-6 py-3 flex items-center gap-3 bg-white">
            <span className="text-xs text-zinc-500">
              {counts.accepted} accepted · {counts.ignored} ignored · {counts.pending} pending
            </span>
            <div className="flex-1" />
            <button onClick={() => setStep(1)} className="px-4 py-2 text-sm text-zinc-600 border border-zinc-200 rounded-xl hover:bg-zinc-50 transition-colors">
              Back
            </button>
            <button onClick={() => setStep(3)} className="px-4 py-2 text-sm font-medium text-white bg-zinc-900 rounded-xl hover:bg-zinc-700 transition-colors">
              Review & confirm →
            </button>
          </div>
        </div>
      )}

      {/* ── Step 3: Confirm ── */}
      {step === 3 && (
        <div className="flex-1 overflow-y-auto flex items-start justify-center pt-12 pb-8 px-4">
          <div className="w-full max-w-lg flex flex-col gap-5">
            <div>
              <h2 className="text-base font-semibold text-zinc-900">Ready to post</h2>
              <p className="text-sm text-zinc-500 mt-0.5">Review what's about to be created, then confirm.</p>
            </div>

            {/* Summary card */}
            <div className="rounded-2xl border border-zinc-200 divide-y divide-zinc-100 bg-white">
              <div className="px-5 py-4 flex items-center justify-between">
                <span className="text-sm text-zinc-600">New transactions</span>
                <span className="font-mono text-sm font-medium text-zinc-900">{confirmCounts.posted}</span>
              </div>
              <div className="px-5 py-4 flex items-center justify-between">
                <span className="text-sm text-zinc-600">Matched (reconciled)</span>
                <span className="font-mono text-sm font-medium text-emerald-700">{confirmCounts.reconciled}</span>
              </div>
              <div className="px-5 py-4 flex items-center justify-between">
                <span className="text-sm text-zinc-600">Skipped / ignored</span>
                <span className="font-mono text-sm font-medium text-zinc-400">{confirmCounts.skipped}</span>
              </div>
              <div className="px-5 py-4 flex items-center justify-between bg-zinc-50 rounded-b-2xl">
                <span className="text-sm font-medium text-zinc-900">Net inflow</span>
                <MonoAmount amount={confirmCounts.netInflow} className="text-sm font-semibold" />
              </div>
            </div>

            {/* Merchant rules */}
            {newRuleCandidates.length > 0 && (
              <div className="rounded-xl border border-zinc-200 bg-zinc-50 px-4 py-3.5 flex flex-col gap-2">
                <div className="flex items-center gap-2">
                  <Zap className="w-3.5 h-3.5 text-zinc-500 shrink-0" />
                  <p className="text-xs font-medium text-zinc-700">Save merchant rules for next time?</p>
                </div>
                <div className="flex flex-col gap-1.5 pl-5">
                  {newRuleCandidates.map(candidate => {
                    const account = activeAccounts.find(a => a.id === candidate.accountId)
                    return (
                      <label key={candidate.description} className="flex items-center gap-2 text-xs text-zinc-700 cursor-pointer">
                        <input
                          type="checkbox"
                          checked={checkedRules.has(candidate.description)}
                          onChange={e => setCheckedRules(prev => {
                            const next = new Set(prev)
                            e.target.checked ? next.add(candidate.description) : next.delete(candidate.description)
                            return next
                          })}
                          className="rounded"
                        />
                        Always map <span className="font-medium truncate max-w-[200px]">{candidate.description}</span>
                        {account && <> → {account.name}</>}
                      </label>
                    )
                  })}
                </div>
              </div>
            )}

            {postError && (
              <p className="text-sm text-red-600 bg-red-50 px-3 py-2 rounded-lg">{postError}</p>
            )}

            <div className="flex items-center gap-3">
              <button onClick={() => setStep(2)} className="flex-1 py-2.5 text-sm text-zinc-600 border border-zinc-200 rounded-xl hover:bg-zinc-50 transition-colors">
                ← Back to review
              </button>
              <button onClick={handlePost} disabled={posting || bankAccountId === ''}
                className="flex-1 py-2.5 text-sm font-medium text-white bg-zinc-900 rounded-xl hover:bg-zinc-700 disabled:opacity-40 disabled:cursor-not-allowed transition-colors">
                {posting ? 'Posting…' : `Post ${confirmCounts.posted} transactions`}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* ── Done ── */}
      {step === 'done' && confirmResult && (
        <div className="flex-1 flex items-center justify-center">
          <div className="flex flex-col items-center gap-5 max-w-sm text-center">
            <div className="w-14 h-14 rounded-full bg-emerald-100 flex items-center justify-center">
              <Check className="w-7 h-7 text-emerald-600" />
            </div>
            <div>
              <h2 className="text-base font-semibold text-zinc-900">
                {confirmResult.posted} transaction{confirmResult.posted !== 1 ? 's' : ''} posted
              </h2>
              <p className="text-sm text-zinc-500 mt-1">
                {confirmResult.reconciled > 0 && `${confirmResult.reconciled} reconciled. `}
                {confirmResult.skipped > 0 && `${confirmResult.skipped} skipped.`}
              </p>
            </div>
            <div className="flex gap-3">
              <button onClick={reset} className="px-4 py-2 text-sm text-zinc-600 border border-zinc-200 rounded-xl hover:bg-zinc-50 transition-colors">
                Import another
              </button>
              <Link to="/transactions" className="px-4 py-2 text-sm font-medium text-white bg-zinc-900 rounded-xl hover:bg-zinc-700 transition-colors">
                View transactions
              </Link>
            </div>
          </div>
        </div>
      )}

    </div>
  )
}
