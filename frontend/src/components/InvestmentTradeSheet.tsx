import { useEffect, useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { AlertCircle } from 'lucide-react'
import { Sheet } from './Sheet'
import { AccountSelect } from './AccountSelect'
import { findAccountGroupId } from './InlineAccountSheet'
import { api, queryKeys } from '../api/api'
import { refreshLivePrice } from '../api/prices'
import {
  bankAccountsForSelect,
  formatRupees,
  inputCls,
  investmentAccountsForSelect,
  resolveActiveFy,
  rupeesPerUnitToPaise,
  totalPaise,
  unitsToMilliunits,
  type AccountOption,
} from './investmentHelpers'
import { formatFyLabel, resolveFyForDate } from './fyHelpers'

interface FinancialYear {
  id: number
  status: string
  start_date: string
  end_date: string
}

interface CapitalGainEntryOut {
  gain: number
  gain_type: string
}

export interface InvestmentTradeSheetProps {
  open: boolean
  onClose: () => void
  mode: 'buy' | 'sell'
  subtype: 'equity_mf' | 'stock'
  account?: AccountOption
  maxUnitsMilli?: number
  onSaved: () => void
}

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

export function InvestmentTradeSheet({
  open,
  onClose,
  mode,
  subtype,
  account,
  maxUnitsMilli,
  onSaved,
}: InvestmentTradeSheetProps) {
  const qc = useQueryClient()
  const priceLabel = subtype === 'stock' ? 'Price per share' : 'NAV per unit'
  const title = mode === 'buy' ? 'Record purchase' : 'Record sale'
  const submitLabel = mode === 'buy' ? 'Record purchase' : 'Record sale'

  const [investmentAccountId, setInvestmentAccountId] = useState<number | ''>('')
  const [bankAccountId, setBankAccountId] = useState<number | ''>('')
  const [date, setDate] = useState(() => new Date().toISOString().slice(0, 10))
  const [units, setUnits] = useState('')
  const [priceRupees, setPriceRupees] = useState('')
  const [narration, setNarration] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [success, setSuccess] = useState<string | null>(null)

  useEffect(() => {
    if (!open) return
    setInvestmentAccountId(account?.id ?? '')
    setBankAccountId('')
    setDate(new Date().toISOString().slice(0, 10))
    setUnits('')
    setPriceRupees('')
    setNarration(mode === 'buy' ? '' : 'Partial redemption')
    setError(null)
    setSuccess(null)
  }, [open, account, mode])

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

  const { data: accountGroups = [] } = useQuery<{ id: number; name: string }[]>({
    queryKey: queryKeys.accountGroups.all(),
    queryFn: () => api.get('/account-groups'),
    enabled: open,
  })

  const activeFy = resolveActiveFy(fys)
  const resolvedFy = resolveFyForDate(fys, date)
  const investmentAccounts = investmentAccountsForSelect(accounts, subtype)
  const bankAccounts = bankAccountsForSelect(accounts)
  const bankGroupId = findAccountGroupId(accountGroups, 'Bank Accounts')
  const investmentGroupId = findAccountGroupId(accountGroups, 'Investments')

  const unitsMilli = unitsToMilliunits(units)
  const pricePaise = rupeesPerUnitToPaise(priceRupees)
  const previewTotal = unitsMilli > 0 && pricePaise > 0 ? totalPaise(unitsMilli, pricePaise) : 0
  const maxUnitsDisplay = maxUnitsMilli != null ? maxUnitsMilli / 1000 : null

  const canSubmit =
    investmentAccountId !== '' &&
    bankAccountId !== '' &&
    unitsMilli > 0 &&
    pricePaise > 0 &&
    (mode === 'buy' || maxUnitsMilli == null || unitsMilli <= maxUnitsMilli)

  const saveMutation = useMutation({
    mutationFn: async () => {
      if (investmentAccountId === '' || bankAccountId === '') {
        throw new Error('Please select all accounts.')
      }
      if (mode === 'sell' && maxUnitsMilli != null && unitsMilli > maxUnitsMilli) {
        throw new Error(`Cannot sell more than ${maxUnitsMilli / 1000} units.`)
      }

      const body: Record<string, unknown> = {
        date,
        units: unitsMilli,
        bank_account_id: bankAccountId,
        narration: narration.trim(),
        ...(mode === 'buy'
          ? { cost_per_unit: pricePaise }
          : { price_per_unit: pricePaise }),
      }
      if (resolvedFy) body.fy_id = resolvedFy.id

      if (mode === 'buy') {
        const result = await api.post(`/investments/${investmentAccountId}/buy`, body)
        const invAccount = accounts.find(a => a.id === investmentAccountId)
        if (invAccount?.price_source_id) {
          await refreshLivePrice(Number(investmentAccountId))
        }
        return result
      }
      return api.post<CapitalGainEntryOut[]>(`/investments/${investmentAccountId}/sell`, body)
    },
    onSuccess: (data) => {
      qc.invalidateQueries({ queryKey: queryKeys.accounts.list() })
      qc.invalidateQueries({ queryKey: ['portfolio'] })
      if (mode === 'sell' && Array.isArray(data)) {
        const stcg = data.filter(e => e.gain_type === 'stcg').reduce((s, e) => s + Math.max(0, e.gain), 0)
        const ltcg = data.filter(e => e.gain_type === 'ltcg').reduce((s, e) => s + Math.max(0, e.gain), 0)
        const parts = []
        if (stcg > 0) parts.push(`STCG ${formatRupees(stcg)}`)
        if (ltcg > 0) parts.push(`LTCG ${formatRupees(ltcg)}`)
        if (parts.length) setSuccess(`Sale recorded. ${parts.join(', ')}`)
      }
      onSaved()
      onClose()
    },
    onError: (e: Error) => setError(e.message),
  })

  return (
    <Sheet open={open} onClose={onClose} title={title}>
      <div className="space-y-5">
        {resolvedFy ? (
          resolvedFy.id !== activeFy?.id && (
            <div className="flex items-start gap-2 text-sm text-blue-800 bg-blue-50 border border-blue-200 rounded-xl px-3 py-2">
              <AlertCircle className="w-4 h-4 shrink-0 mt-0.5" />
              <span>Posting to FY {formatFyLabel(resolvedFy)} (from transaction date)</span>
            </div>
          )
        ) : (
          <div className="flex items-start gap-2 text-sm text-amber-800 bg-amber-50 border border-amber-200 rounded-xl px-3 py-2">
            <AlertCircle className="w-4 h-4 shrink-0 mt-0.5" />
            <span>No FY covers this date — a new year will be created when you save.</span>
          </div>
        )}

        {mode === 'sell' && maxUnitsDisplay != null && (
          <p className="text-sm text-zinc-600">
            Available: <span className="font-mono font-medium">{maxUnitsDisplay.toLocaleString('en-IN', { maximumFractionDigits: 3 })}</span> units
          </p>
        )}

        <div>
          <FieldLabel label="Investment account" htmlFor="inv-account" />
          <AccountSelect
            id="inv-account"
            ariaLabel="Investment account"
            value={investmentAccountId}
            onChange={id => setInvestmentAccountId(id ?? '')}
            accounts={investmentAccounts}
            placeholder="Select fund or stock…"
            disabled={mode === 'sell' && !!account}
            initialGroupId={investmentGroupId}
            className={inputCls}
          />
        </div>

        <div>
          <FieldLabel
            label={mode === 'buy' ? 'Pay from' : 'Receive into'}
            htmlFor="bank-account"
          />
          <AccountSelect
            id="bank-account"
            ariaLabel={mode === 'buy' ? 'Pay from' : 'Receive into'}
            value={bankAccountId}
            onChange={id => setBankAccountId(id ?? '')}
            accounts={bankAccounts}
            placeholder="Select bank account…"
            showGroupName
            initialGroupId={bankGroupId}
            className={inputCls}
          />
        </div>

        <div>
          <FieldLabel label="Date" htmlFor="trade-date" />
          <input
            id="trade-date"
            type="date"
            value={date}
            onChange={e => setDate(e.target.value)}
            className={inputCls}
          />
        </div>

        <div className="grid grid-cols-2 gap-3">
          <div>
            <FieldLabel label="Units" htmlFor="trade-units" />
            <input
              id="trade-units"
              aria-label="Units"
              type="number"
              min="0"
              step="0.001"
              value={units}
              onChange={e => setUnits(e.target.value)}
              className={`${inputCls} font-mono`}
            />
          </div>
          <div>
            <FieldLabel label={priceLabel} htmlFor="trade-price" />
            <div className="relative">
              <span className="absolute left-3 top-1/2 -translate-y-1/2 text-zinc-400 font-mono text-sm">₹</span>
              <input
                id="trade-price"
                aria-label={priceLabel}
                type="number"
                min="0"
                step="0.01"
                value={priceRupees}
                onChange={e => setPriceRupees(e.target.value)}
                className={`${inputCls} pl-8 font-mono`}
              />
            </div>
          </div>
        </div>

        {previewTotal > 0 && (
          <p className="text-sm text-zinc-600">
            Total: <span className="font-mono font-medium text-zinc-900">{formatRupees(previewTotal)}</span>
          </p>
        )}

        <div>
          <FieldLabel label="Narration (optional)" htmlFor="trade-narration" />
          <textarea
            id="trade-narration"
            aria-label="Narration (optional)"
            rows={2}
            value={narration}
            onChange={e => setNarration(e.target.value)}
            placeholder="e.g. SIP purchase"
            className={`${inputCls} resize-none`}
          />
        </div>

        {error && (
          <div className="flex items-start gap-2 text-sm text-red-700 bg-red-50 border border-red-200 rounded-xl px-3 py-2">
            <AlertCircle className="w-4 h-4 shrink-0 mt-0.5" />
            <span>{error}</span>
          </div>
        )}

        {success && (
          <p className="text-sm text-emerald-700 bg-emerald-50 border border-emerald-200 rounded-xl px-3 py-2">
            {success}
          </p>
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
            disabled={!canSubmit || saveMutation.isPending}
            className="bg-blue-600 hover:bg-blue-700 disabled:opacity-50 text-white text-sm font-medium px-4 py-2 rounded-lg transition-colors"
          >
            {saveMutation.isPending ? 'Saving…' : submitLabel}
          </button>
        </div>
      </div>
    </Sheet>
  )
}
