import { useState, useEffect } from 'react'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { ChevronDown, HelpCircle } from 'lucide-react'
import { Sheet } from './Sheet'
import { api, queryKeys } from '../api/api'

interface AccountGroup {
  id: number
  name: string
  nature: string
  parent_id: number | null
  sort_order: number
  cash_flow_tag: string | null
}

interface AccountOut {
  id: number
  name: string
  group_id: number
  group_name: string
  nature: string
  is_archived: boolean
  investment_subtype: string | null
  depreciation_rate: number | null
  price_source_id: string | null
  currency: string
  balance: number
}

interface AccountSheetProps {
  open: boolean
  onClose: () => void
  account?: AccountOut
  groups: AccountGroup[]
  activeFyId: number | undefined
  onSaved: () => void
}

const DEP_PRESETS = [
  { label: 'Select preset', rate: '' },
  { label: 'Computer (40%)', rate: '40' },
  { label: 'Furniture (10%)', rate: '10' },
  { label: 'Vehicle (15%)', rate: '15' },
  { label: 'General (15%)', rate: '15' },
  { label: 'Building (10%)', rate: '10' },
]

const INV_SUBTYPES: { value: string; label: string }[] = [
  { value: 'equity_mf', label: 'Equity MF' },
  { value: 'stock', label: 'Stock' },
  { value: 'fd', label: 'FD' },
  { value: 'ppf', label: 'PPF' },
]

const CF_TAGS = ['operating', 'investing', 'financing']

function isFixedGroup(name: string) {
  return name.toLowerCase().includes('fixed')
}

function isInvestmentGroup(name: string) {
  return name.toLowerCase().includes('invest')
}

function Tip({ text }: { text: string }) {
  return (
    <span className="group relative inline-flex cursor-help">
      <HelpCircle className="w-3.5 h-3.5 text-zinc-300" />
      <span className="pointer-events-none absolute bottom-5 left-1/2 -translate-x-1/2 w-48 rounded-lg bg-zinc-900 px-2.5 py-2 text-xs text-white leading-relaxed opacity-0 group-hover:opacity-100 transition-opacity z-50">
        {text}
      </span>
    </span>
  )
}

function FieldLabel({ label, tip }: { label: string; tip?: string }) {
  return (
    <div className="flex items-center gap-1.5 mb-2">
      <label className="text-xs font-semibold text-zinc-500 uppercase tracking-wide">{label}</label>
      {tip && <Tip text={tip} />}
    </div>
  )
}

export function AccountSheet({ open, onClose, account, groups, activeFyId, onSaved }: AccountSheetProps) {
  const qc = useQueryClient()
  const isEdit = !!account

  const [name, setName] = useState('')
  const [groupId, setGroupId] = useState<number | ''>('')
  const [cfTag, setCfTag] = useState('')
  const [depRate, setDepRate] = useState('')
  const [invSubtype, setInvSubtype] = useState('')
  const [obRupees, setObRupees] = useState('')
  const [moreOpen, setMoreOpen] = useState(false)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    if (!open) return
    if (account) {
      setName(account.name)
      setGroupId(account.group_id)
      setCfTag('')
      setDepRate(account.depreciation_rate != null ? String(account.depreciation_rate) : '')
      setInvSubtype(account.investment_subtype ?? '')
      setObRupees('')
      setMoreOpen(false)
    } else {
      setName('')
      setGroupId('')
      setCfTag('')
      setDepRate('')
      setInvSubtype('')
      setObRupees('')
      setMoreOpen(false)
    }
    setError(null)
  }, [open, account])

  const selectedGroup = groups.find(g => g.id === groupId)
  const showDep = selectedGroup ? isFixedGroup(selectedGroup.name) : false
  const showInv = selectedGroup ? isInvestmentGroup(selectedGroup.name) : false

  function handleGroupChange(id: number | '') {
    setGroupId(id)
    if (id === '') return
    const g = groups.find(gr => gr.id === id)
    if (!g) return
    setCfTag(g.cash_flow_tag ?? '')
    if (isFixedGroup(g.name) || isInvestmentGroup(g.name)) setMoreOpen(true)
  }

  const saveMutation = useMutation({
    mutationFn: async () => {
      if (!name.trim()) throw new Error('Name is required')
      if (groupId === '') throw new Error('Group is required')

      const payload = {
        name: name.trim(),
        group_id: groupId,
        ...(depRate !== '' ? { depreciation_rate: parseFloat(depRate) } : { depreciation_rate: null }),
        investment_subtype: invSubtype || null,
        price_source_id: null,
        currency: account?.currency ?? 'INR',
        is_archived: account?.is_archived ?? false,
      }

      let savedId: number
      if (isEdit) {
        const res = await api.put<{ id: number }>(`/accounts/${account!.id}`, payload)
        savedId = res.id
      } else {
        const res = await api.post<{ id: number }>('/accounts', payload)
        savedId = res.id
      }

      if (obRupees !== '' && activeFyId != null) {
        const paise = Math.round(parseFloat(obRupees) * 100)
        if (!isNaN(paise)) {
          await api.put(`/accounts/${savedId}/opening-balance`, { fy_id: activeFyId, amount: paise })
        }
      }
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: queryKeys.accounts.list() })
      onSaved()
      onClose()
    },
    onError: (e: Error) => setError(e.message),
  })

  // Group options — sort by sort_order, optgroup by nature
  const natures = ['asset', 'liability', 'equity', 'income', 'expense']
  const NATURE_LABEL: Record<string, string> = {
    asset: 'Assets', liability: 'Liabilities', equity: 'Equity',
    income: 'Income', expense: 'Expenses',
  }

  return (
    <Sheet open={open} onClose={onClose} title={isEdit ? 'Edit Account' : 'New Account'}>
      <div className="flex flex-col gap-5">
        {error && (
          <p className="text-sm text-red-600 bg-red-50 px-3 py-2 rounded-lg">{error}</p>
        )}

        {/* Name */}
        <div>
          <FieldLabel label="Name" />
          <input
            type="text"
            value={name}
            onChange={e => setName(e.target.value)}
            placeholder="e.g. HDFC Bank, Electricity Expense"
            className="w-full px-3.5 py-2.5 text-sm border border-zinc-200 rounded-xl focus:outline-none focus:ring-2 focus:ring-blue-500 transition"
          />
        </div>

        {/* Group */}
        <div>
          <FieldLabel
            label="Group"
            tip="Groups organise accounts into categories like Bank Accounts, Expenses, Income etc. This determines how the account appears in reports."
          />
          <select
            value={groupId}
            onChange={e => handleGroupChange(e.target.value === '' ? '' : Number(e.target.value))}
            className="w-full px-3.5 py-2.5 text-sm border border-zinc-200 rounded-xl focus:outline-none focus:ring-2 focus:ring-blue-500 bg-white cursor-pointer"
          >
            <option value="">Select a group</option>
            {natures.map(nature => {
              const natGroups = groups.filter(g => g.nature === nature).sort((a, b) => a.sort_order - b.sort_order)
              if (!natGroups.length) return null
              return (
                <optgroup key={nature} label={NATURE_LABEL[nature]}>
                  {natGroups.map(g => (
                    <option key={g.id} value={g.id}>{g.name}</option>
                  ))}
                </optgroup>
              )
            })}
          </select>
        </div>

        {/* More details toggle */}
        <button
          type="button"
          onClick={() => setMoreOpen(v => !v)}
          className="flex items-center gap-1.5 text-sm text-zinc-500 hover:text-zinc-700 transition-colors"
        >
          <ChevronDown
            className={`w-4 h-4 transition-transform duration-200 ${moreOpen ? 'rotate-180' : ''}`}
          />
          {moreOpen ? 'Less details' : 'More details'}
        </button>

        {moreOpen && (
          <div className="space-y-5">
            {/* Cash flow tag */}
            <div>
              <FieldLabel
                label="Cash flow tag"
                tip="Used to classify cash movements in the Cash Flow Statement. Only change if you know what you're doing."
              />
              <select
                value={cfTag}
                onChange={e => setCfTag(e.target.value)}
                className="w-full px-3.5 py-2.5 text-sm border border-zinc-200 rounded-xl focus:outline-none focus:ring-2 focus:ring-blue-500 bg-white cursor-pointer"
              >
                <option value="">None</option>
                {CF_TAGS.map(t => (
                  <option key={t} value={t}>{t.charAt(0).toUpperCase() + t.slice(1)}</option>
                ))}
              </select>
            </div>

            {/* Depreciation rate (fixed assets) */}
            {showDep && (
              <div>
                <FieldLabel
                  label="Depreciation rate"
                  tip="The WDV rate per Income Tax Act. Common: Computers 40%, Furniture 10%, Vehicles 15%."
                />
                <div className="flex gap-2">
                  <div className="relative flex-1">
                    <input
                      type="number"
                      min="0"
                      max="100"
                      step="0.5"
                      value={depRate}
                      onChange={e => setDepRate(e.target.value)}
                      placeholder="40"
                      className="w-full px-3.5 pr-8 py-2.5 text-sm border border-zinc-200 rounded-xl focus:outline-none focus:ring-2 focus:ring-blue-500 transition"
                    />
                    <span className="absolute right-3.5 top-1/2 -translate-y-1/2 text-zinc-400 text-sm">%</span>
                  </div>
                  <select
                    value=""
                    onChange={e => { if (e.target.value) setDepRate(e.target.value) }}
                    className="px-3 py-2.5 text-sm border border-zinc-200 rounded-xl bg-white focus:outline-none focus:ring-2 focus:ring-blue-500 cursor-pointer"
                  >
                    {DEP_PRESETS.map(p => (
                      <option key={p.label} value={p.rate}>{p.label}</option>
                    ))}
                  </select>
                </div>
              </div>
            )}

            {/* Investment subtype */}
            {showInv && (
              <div>
                <FieldLabel
                  label="Investment type"
                  tip="Equity MFs and Stocks track purchase lots for capital gains. FDs track interest income. PPF tracks contributions."
                />
                <div className="flex gap-2 flex-wrap">
                  {INV_SUBTYPES.map(({ value, label }) => (
                    <button
                      key={value}
                      type="button"
                      onClick={() => setInvSubtype(value)}
                      className={`text-xs font-medium px-3 py-1.5 rounded-lg border transition-all ${
                        invSubtype === value
                          ? 'bg-zinc-900 text-white border-zinc-900'
                          : 'text-zinc-600 border-zinc-200 hover:border-zinc-300'
                      }`}
                    >
                      {label}
                    </button>
                  ))}
                </div>
              </div>
            )}

            {/* Opening balance */}
            <div>
              <FieldLabel
                label="Opening balance"
                tip="The balance this account had at the start of the active financial year. Leave blank for new accounts."
              />
              <div className="relative">
                <span className="absolute left-3.5 top-1/2 -translate-y-1/2 text-zinc-400 font-mono text-sm">₹</span>
                <input
                  type="number"
                  min="0"
                  step="0.01"
                  value={obRupees}
                  onChange={e => setObRupees(e.target.value)}
                  placeholder="0"
                  className="w-full pl-8 pr-4 py-2.5 font-mono text-sm border border-zinc-200 rounded-xl focus:outline-none focus:ring-2 focus:ring-blue-500 transition"
                />
              </div>
            </div>
          </div>
        )}

        {/* Footer */}
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
            disabled={saveMutation.isPending}
            className="flex items-center gap-2 bg-blue-600 hover:bg-blue-700 disabled:opacity-50 text-white text-sm font-medium px-4 py-2 rounded-lg transition-colors"
          >
            {saveMutation.isPending ? 'Saving…' : 'Save'}
          </button>
        </div>
      </div>
    </Sheet>
  )
}
