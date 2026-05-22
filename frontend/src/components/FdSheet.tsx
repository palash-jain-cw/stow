import { useEffect, useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { AlertCircle } from 'lucide-react'
import { Sheet } from './Sheet'
import { api, queryKeys } from '../api/api'
import {
  bankAccountsForSelect,
  inputCls,
  resolveActiveFy,
  rupeesToPaise,
  type AccountOption,
} from './investmentHelpers'
import { MonoAmount } from './MonoAmount'

interface FinancialYear {
  id: number
  status: string
}

export interface FdListItem {
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

interface FdMatureOut {
  principal: number
  interest: number
  total: number
}

export interface FdSheetProps {
  open: boolean
  onClose: () => void
  mode: 'open' | 'mature'
  fd?: FdListItem
  onSaved: () => void
}

const COMPOUNDING_OPTIONS = ['simple', 'monthly', 'quarterly', 'yearly'] as const

function FieldLabel({ label, htmlFor }: { label: string; htmlFor?: string }) {
  return (
    <label
      htmlFor={htmlFor}
      className="block text-xs font-semibold text-zinc-500 uppercase tracking-wide mb-2"
    >
      {label}
    </label>
  )
}

export function FdSheet({ open, onClose, mode, fd, onSaved }: FdSheetProps) {
  const qc = useQueryClient()
  const title = mode === 'open' ? 'Open fixed deposit' : 'Mature fixed deposit'
  const submitLabel = mode === 'open' ? 'Open fixed deposit' : 'Mature fixed deposit'

  const [name, setName] = useState('')
  const [principalRupees, setPrincipalRupees] = useState('')
  const [interestRate, setInterestRate] = useState('')
  const [startDate, setStartDate] = useState(() => new Date().toISOString().slice(0, 10))
  const [maturityDate, setMaturityDate] = useState('')
  const [compounding, setCompounding] = useState<string>('quarterly')
  const [fromAccountId, setFromAccountId] = useState<number | ''>('')
  const [toAccountId, setToAccountId] = useState<number | ''>('')
  const [date, setDate] = useState(() => new Date().toISOString().slice(0, 10))
  const [narration, setNarration] = useState('')
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    if (!open) return
    if (mode === 'open') {
      setName('')
      setPrincipalRupees('')
      setInterestRate('')
      setStartDate(new Date().toISOString().slice(0, 10))
      setMaturityDate('')
      setCompounding('quarterly')
      setFromAccountId('')
      setDate(new Date().toISOString().slice(0, 10))
      setNarration('Open fixed deposit')
    } else if (fd) {
      setToAccountId('')
      setDate(fd.maturity_date)
      setNarration(`FD maturity — ${fd.name}`)
    }
    setError(null)
  }, [open, mode, fd])

  const { data: accounts = [] } = useQuery({
    queryKey: queryKeys.accounts.list(),
    queryFn: () => api.get<AccountOption[]>('/accounts'),
    enabled: open,
  })

  const { data: fys = [] } = useQuery({
    queryKey: queryKeys.financialYears.all(),
    queryFn: () => api.get<FinancialYear[]>('/financial-years'),
    enabled: open,
  })

  const activeFy = resolveActiveFy(fys)
  const bankAccounts = bankAccountsForSelect(accounts)

  const maturityPreview = fd ? fd.principal + fd.accrued_interest : 0

  const canSubmitOpen =
    !!activeFy &&
    name.trim() !== '' &&
    rupeesToPaise(principalRupees) > 0 &&
    parseFloat(interestRate) > 0 &&
    startDate !== '' &&
    maturityDate !== '' &&
    fromAccountId !== '' &&
    narration.trim() !== ''

  const canSubmitMature =
    !!activeFy && !!fd && toAccountId !== '' && date !== '' && narration.trim() !== ''

  const saveMutation = useMutation({
    mutationFn: async () => {
      if (!activeFy) throw new Error('No active financial year. Please create one in Settings.')

      if (mode === 'open') {
        return api.post('/investments/fds', {
          name: name.trim(),
          principal: rupeesToPaise(principalRupees),
          interest_rate: Math.round(parseFloat(interestRate) * 100),
          start_date: startDate,
          maturity_date: maturityDate,
          compounding,
          from_account_id: fromAccountId,
          fy_id: activeFy.id,
          date,
          narration: narration.trim(),
        })
      }

      if (!fd) throw new Error('No FD selected.')
      return api.post<FdMatureOut>(`/investments/fds/${fd.account_id}/mature`, {
        to_account_id: toAccountId,
        fy_id: activeFy.id,
        date,
        narration: narration.trim(),
      })
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: queryKeys.accounts.list() })
      qc.invalidateQueries({ queryKey: queryKeys.investments.fds() })
      onSaved()
      onClose()
    },
    onError: (e: Error) => setError(e.message),
  })

  return (
    <Sheet open={open} onClose={onClose} title={title}>
      <div className="space-y-5">
        {!activeFy && (
          <div className="flex items-start gap-2 text-sm text-amber-800 bg-amber-50 border border-amber-200 rounded-xl px-3 py-2">
            <AlertCircle className="w-4 h-4 shrink-0 mt-0.5" />
            <span>No active financial year. Create one in Settings first.</span>
          </div>
        )}

        {mode === 'open' ? (
          <>
            <div>
              <FieldLabel label="FD name" htmlFor="fd-name" />
              <input
                id="fd-name"
                aria-label="FD name"
                value={name}
                onChange={e => setName(e.target.value)}
                className={inputCls}
              />
            </div>
            <div className="grid grid-cols-2 gap-3">
              <div>
                <FieldLabel label="Principal" htmlFor="fd-principal" />
                <div className="relative">
                  <span className="absolute left-3 top-1/2 -translate-y-1/2 text-zinc-400 font-mono text-sm">₹</span>
                  <input
                    id="fd-principal"
                    aria-label="Principal"
                    type="number"
                    min="0"
                    value={principalRupees}
                    onChange={e => setPrincipalRupees(e.target.value)}
                    className={`${inputCls} pl-8 font-mono`}
                  />
                </div>
              </div>
              <div>
                <FieldLabel label="Interest rate" htmlFor="fd-rate" />
                <div className="relative">
                  <input
                    id="fd-rate"
                    aria-label="Interest rate"
                    type="number"
                    min="0"
                    step="0.01"
                    value={interestRate}
                    onChange={e => setInterestRate(e.target.value)}
                    className={`${inputCls} pr-8 font-mono`}
                  />
                  <span className="absolute right-3 top-1/2 -translate-y-1/2 text-zinc-400 text-sm">%</span>
                </div>
              </div>
            </div>
            <div className="grid grid-cols-2 gap-3">
              <div>
                <FieldLabel label="Start date" htmlFor="fd-start" />
                <input
                  id="fd-start"
                  aria-label="Start date"
                  type="date"
                  value={startDate}
                  onChange={e => {
                    setStartDate(e.target.value)
                    if (!date || date === startDate) setDate(e.target.value)
                  }}
                  className={inputCls}
                />
              </div>
              <div>
                <FieldLabel label="Maturity date" htmlFor="fd-maturity" />
                <input
                  id="fd-maturity"
                  aria-label="Maturity date"
                  type="date"
                  value={maturityDate}
                  onChange={e => setMaturityDate(e.target.value)}
                  className={inputCls}
                />
              </div>
            </div>
            <div>
              <FieldLabel label="Compounding" htmlFor="fd-compounding" />
              <select
                id="fd-compounding"
                aria-label="Compounding"
                value={compounding}
                onChange={e => setCompounding(e.target.value)}
                className={inputCls}
              >
                {COMPOUNDING_OPTIONS.map(c => (
                  <option key={c} value={c}>{c.charAt(0).toUpperCase() + c.slice(1)}</option>
                ))}
              </select>
            </div>
            <div>
              <FieldLabel label="Fund from" htmlFor="fd-from" />
              <select
                id="fd-from"
                aria-label="Fund from"
                value={fromAccountId}
                onChange={e => setFromAccountId(e.target.value === '' ? '' : Number(e.target.value))}
                className={inputCls}
              >
                <option value="">Select bank account…</option>
                {bankAccounts.map(a => (
                  <option key={a.id} value={a.id}>{a.name} — {a.group_name}</option>
                ))}
              </select>
            </div>
            <div>
              <FieldLabel label="Transaction date" htmlFor="fd-date" />
              <input
                id="fd-date"
                type="date"
                value={date}
                onChange={e => setDate(e.target.value)}
                className={inputCls}
              />
            </div>
          </>
        ) : (
          fd && (
            <>
              <div>
                <FieldLabel label="Fixed deposit" />
                <p className="text-sm font-medium text-zinc-900">{fd.name}</p>
              </div>
              <dl className="grid grid-cols-2 gap-3 text-sm bg-zinc-50 rounded-xl p-3">
                <div>
                  <dt className="text-zinc-400 text-xs">Principal</dt>
                  <dd className="font-mono"><MonoAmount amount={fd.principal} /></dd>
                </div>
                <div>
                  <dt className="text-zinc-400 text-xs">Accrued interest</dt>
                  <dd className="font-mono"><MonoAmount amount={fd.accrued_interest} /></dd>
                </div>
                <div className="col-span-2">
                  <dt className="text-zinc-400 text-xs">Maturity amount</dt>
                  <dd className="font-mono font-medium"><MonoAmount amount={maturityPreview} /></dd>
                </div>
              </dl>
              <div>
                <FieldLabel label="Receive into" htmlFor="fd-to" />
                <select
                  id="fd-to"
                  aria-label="Receive into"
                  value={toAccountId}
                  onChange={e => setToAccountId(e.target.value === '' ? '' : Number(e.target.value))}
                  className={inputCls}
                >
                  <option value="">Select bank account…</option>
                  {bankAccounts.map(a => (
                    <option key={a.id} value={a.id}>{a.name} — {a.group_name}</option>
                  ))}
                </select>
              </div>
              <div>
                <FieldLabel label="Maturity date" htmlFor="fd-mature-date" />
                <input
                  id="fd-mature-date"
                  type="date"
                  value={date}
                  onChange={e => setDate(e.target.value)}
                  className={inputCls}
                />
              </div>
            </>
          )
        )}

        <div>
          <FieldLabel label="Narration" htmlFor="fd-narration" />
          <textarea
            id="fd-narration"
            aria-label="Narration"
            rows={2}
            value={narration}
            onChange={e => setNarration(e.target.value)}
            className={`${inputCls} resize-none`}
          />
        </div>

        {error && (
          <div className="flex items-start gap-2 text-sm text-red-700 bg-red-50 border border-red-200 rounded-xl px-3 py-2">
            <AlertCircle className="w-4 h-4 shrink-0 mt-0.5" />
            <span>{error}</span>
          </div>
        )}

        <div className="flex items-center justify-between pt-2 border-t border-zinc-100">
          <button
            type="button"
            onClick={onClose}
            className="text-sm text-zinc-400 hover:text-zinc-600 transition-colors"
          >
            Cancel
          </button>
          <button
            type="button"
            onClick={() => saveMutation.mutate()}
            disabled={
              (mode === 'open' ? !canSubmitOpen : !canSubmitMature) || saveMutation.isPending
            }
            className="bg-blue-600 hover:bg-blue-700 disabled:opacity-50 text-white text-sm font-medium px-4 py-2 rounded-lg transition-colors"
          >
            {saveMutation.isPending ? 'Saving…' : submitLabel}
          </button>
        </div>
      </div>
    </Sheet>
  )
}
