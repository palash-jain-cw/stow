import { useState, useEffect, useRef } from 'react'
import { useNavigate, Link } from 'react-router-dom'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { CheckCircle2, XCircle, Loader2, Plus, Trash2, Check } from 'lucide-react'
import { api, queryKeys } from '../api/api'

// ── Types ─────────────────────────────────────────────────────────────────────

interface FinancialYear { id: number; start_date: string; end_date: string; status: string }
interface AccountGroup { id: number; name: string; nature: string }
interface AccountOut { id: number; name: string }
interface AiConnectionResult { ok: boolean; model: string | null; latency_ms: number | null; error: string | null }
interface TelegramTestResult { ok: boolean; bot_username: string | null; bot_name: string | null; error: string | null }

// ── FY helpers ────────────────────────────────────────────────────────────────

function fyStartYear(): number {
  const today = new Date()
  return today.getMonth() >= 3 ? today.getFullYear() : today.getFullYear() - 1
}

function fyLabel(startYear: number) {
  return `FY ${startYear}–${String(startYear + 1).slice(2)}`
}

function fyDates(startYear: number) {
  return {
    start_date: `${startYear}-04-01`,
    end_date: `${startYear + 1}-03-31`,
  }
}

function formatDate(iso: string) {
  return new Date(iso).toLocaleDateString('en-IN', { day: 'numeric', month: 'long', year: 'numeric' })
}

// ── Progress dots ─────────────────────────────────────────────────────────────

function ProgressDots({ current, total }: { current: number; total: number }) {
  return (
    <div className="flex items-center justify-center gap-2 mb-8">
      {Array.from({ length: total }, (_, i) => {
        const step = i + 1
        const done = step < current
        const active = step === current
        return (
          <div
            key={step}
            className={`rounded-full transition-all ${
              done ? 'w-2 h-2 bg-zinc-900' :
              active ? 'w-2.5 h-2.5 bg-zinc-900' :
              'w-2 h-2 bg-zinc-200'
            }`}
          />
        )
      })}
    </div>
  )
}

// ── Step wrapper ──────────────────────────────────────────────────────────────

function StepCard({ children }: { children: React.ReactNode }) {
  return (
    <div className="min-h-screen bg-zinc-50 flex items-center justify-center px-4">
      <div className="bg-white rounded-2xl shadow-sm border border-zinc-100 w-full max-w-lg p-8">
        {children}
      </div>
    </div>
  )
}

function PrimaryButton({ onClick, disabled, children }: {
  onClick: () => void; disabled?: boolean; children: React.ReactNode
}) {
  return (
    <button
      onClick={onClick}
      disabled={disabled}
      className="w-full py-2.5 bg-zinc-900 text-white rounded-xl font-medium hover:bg-zinc-700 disabled:opacity-40 transition-colors"
    >
      {children}
    </button>
  )
}

function SkipLink({ onClick, label = 'Skip for now' }: { onClick: () => void; label?: string }) {
  return (
    <button
      onClick={onClick}
      className="w-full text-center text-sm text-zinc-400 hover:text-zinc-600 mt-3"
    >
      {label}
    </button>
  )
}

// ── Step 1: Welcome ───────────────────────────────────────────────────────────

function StepWelcome({ onNext }: { onNext: () => void }) {
  return (
    <StepCard>
      <div className="text-center mb-8">
        <div className="text-3xl font-bold text-zinc-900 mb-2">Stow</div>
        <p className="text-zinc-500 leading-relaxed">
          Double-entry accounting for people who like to know where their money goes.
        </p>
      </div>
      <p className="text-sm text-zinc-600 text-center mb-8">
        Let's get you set up in about 2 minutes.
      </p>
      <PrimaryButton onClick={onNext}>Get started →</PrimaryButton>
    </StepCard>
  )
}

// ── Step 2: Financial Year ────────────────────────────────────────────────────

function StepFinancialYear({ onNext }: { onNext: (fyId: number, startDate: string, label: string) => void }) {
  const defaultYear = fyStartYear()
  const [selectedYear, setSelectedYear] = useState(defaultYear)
  const [saving, setSaving] = useState(false)

  const yearOptions = [defaultYear, defaultYear - 1, defaultYear - 2]

  const handleContinue = async () => {
    setSaving(true)
    try {
      const { start_date, end_date } = fyDates(selectedYear)
      const fy = await api.post<FinancialYear>('/financial-years', { start_date, end_date, status: 'active' })
      onNext(fy.id, fy.start_date, fyLabel(selectedYear))
    } finally {
      setSaving(false)
    }
  }

  return (
    <StepCard>
      <ProgressDots current={2} total={7} />
      <h1 className="text-xl font-semibold text-zinc-900 mb-1">Which financial year are you starting with?</h1>
      <p className="text-sm text-zinc-500 mb-6">
        This sets the period for all your reports. You can open additional years later in Settings.
      </p>

      <div className="space-y-2 mb-6">
        {yearOptions.map(year => {
          const { start_date, end_date } = fyDates(year)
          const selected = year === selectedYear
          return (
            <button
              key={year}
              onClick={() => setSelectedYear(year)}
              className={`w-full text-left px-4 py-3 rounded-xl border-2 transition-colors ${
                selected ? 'border-zinc-900 bg-zinc-50' : 'border-zinc-100 hover:border-zinc-200'
              }`}
            >
              <div className="flex items-center justify-between">
                <div>
                  <span className="font-medium text-zinc-900">{fyLabel(year)}</span>
                  {year === defaultYear && (
                    <span className="ml-2 text-xs bg-emerald-100 text-emerald-700 px-1.5 py-0.5 rounded-full">Current</span>
                  )}
                  <p className="text-xs text-zinc-400 mt-0.5">
                    {formatDate(start_date)} – {formatDate(end_date)}
                  </p>
                </div>
                {selected && <Check size={16} className="text-zinc-900 shrink-0" />}
              </div>
            </button>
          )
        })}
      </div>

      <PrimaryButton onClick={handleContinue} disabled={saving}>
        {saving ? 'Creating…' : 'Continue'}
      </PrimaryButton>
    </StepCard>
  )
}

// ── Step 3: Bank Accounts ─────────────────────────────────────────────────────

function StepBankAccounts({ onNext, onSkip }: {
  onNext: (accounts: Array<{ id: number; name: string }>) => void
  onSkip: () => void
}) {
  const [bankNames, setBankNames] = useState<string[]>([''])
  const [addCash, setAddCash] = useState(false)
  const [saving, setSaving] = useState(false)

  const { data: groups = [] } = useQuery<AccountGroup[]>({
    queryKey: queryKeys.accountGroups.all(),
    queryFn: () => api.get<AccountGroup[]>('/account-groups'),
  })

  const updateName = (i: number, v: string) =>
    setBankNames(prev => prev.map((n, j) => j === i ? v : n))

  const addRow = () => setBankNames(prev => [...prev, ''])

  const removeRow = (i: number) =>
    setBankNames(prev => prev.filter((_, j) => j !== i))

  const [dupError, setDupError] = useState('')

  const handleContinue = async () => {
    const bankGroup = groups.find(g => g.name === 'Bank Accounts')
    const cashGroup = groups.find(g => g.name === 'Cash-in-Hand')
    if (!bankGroup) return

    const trimmed = bankNames.map(n => n.trim()).filter(Boolean)
    const dupes = trimmed.filter((n, i) => trimmed.findIndex(m => m.toLowerCase() === n.toLowerCase()) !== i)
    if (dupes.length) { setDupError(`Duplicate name: "${dupes[0]}"`); return }
    setDupError('')

    setSaving(true)
    try {
      const toCreate: Array<{ name: string; group_id: number }> = [
        ...bankNames.filter(n => n.trim()).map(name => ({ name: name.trim(), group_id: bankGroup.id })),
        ...(addCash && cashGroup ? [{ name: 'Cash in Hand', group_id: cashGroup.id }] : []),
      ]

      const created = await Promise.all(
        toCreate.map(a => api.post<AccountOut>('/accounts', { name: a.name, group_id: a.group_id }))
      )

      onNext(created.map(a => ({ id: a.id, name: a.name })))
    } finally {
      setSaving(false)
    }
  }

  const hasAny = bankNames.some(n => n.trim()) || addCash

  return (
    <StepCard>
      <ProgressDots current={3} total={7} />
      <h1 className="text-xl font-semibold text-zinc-900 mb-1">Add your bank accounts</h1>
      <p className="text-sm text-zinc-500 mb-6">
        Add the accounts you use day-to-day. You can always add more in Accounts.
      </p>

      <div className="space-y-2 mb-3">
        {bankNames.map((name, i) => (
          <div key={i} className="flex items-center gap-2">
            <input
              type="text"
              className="flex-1 border border-zinc-200 rounded-xl px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-zinc-300"
              placeholder="e.g. HDFC Bank, Axis Bank"
              value={name}
              onChange={e => updateName(i, e.target.value)}
              autoFocus={i === 0}
            />
            {bankNames.length > 1 && (
              <button onClick={() => removeRow(i)} className="text-zinc-300 hover:text-zinc-500">
                <Trash2 size={15} />
              </button>
            )}
          </div>
        ))}
      </div>

      <button
        onClick={addRow}
        className="flex items-center gap-1 text-sm text-zinc-500 hover:text-zinc-700 mb-5"
      >
        <Plus size={14} /> Add another account
      </button>

      <label className="flex items-center gap-2 mb-6 cursor-pointer">
        <input
          type="checkbox"
          className="rounded"
          checked={addCash}
          onChange={e => setAddCash(e.target.checked)}
        />
        <span className="text-sm text-zinc-600">I also keep cash (add a Cash-in-Hand account)</span>
      </label>

      {dupError && <p className="text-xs text-red-500 mb-2">{dupError}</p>}
      <PrimaryButton onClick={handleContinue} disabled={!hasAny || saving}>
        {saving ? 'Creating accounts…' : 'Continue'}
      </PrimaryButton>
      <SkipLink onClick={onSkip} />
    </StepCard>
  )
}

// ── Step 4: Opening Balances ──────────────────────────────────────────────────

function StepOpeningBalances({ accounts, fyId, fyStartDate, onNext, onSkip }: {
  accounts: Array<{ id: number; name: string }>
  fyId: number
  fyStartDate: string
  onNext: () => void
  onSkip: () => void
}) {
  const [values, setValues] = useState<Record<number, string>>({})
  const [saving, setSaving] = useState(false)

  const setValue = (id: number, v: string) => setValues(prev => ({ ...prev, [id]: v }))

  const handleSave = async () => {
    setSaving(true)
    try {
      const toSave = accounts.filter(a => {
        const v = parseFloat(values[a.id] ?? '0')
        return !isNaN(v) && v !== 0
      })
      await Promise.all(
        toSave.map(a => api.put(`/accounts/${a.id}/opening-balance`, {
          fy_id: fyId,
          amount: Math.round(parseFloat(values[a.id]) * 100),
        }))
      )
      onNext()
    } finally {
      setSaving(false)
    }
  }

  return (
    <StepCard>
      <ProgressDots current={4} total={7} />
      <h1 className="text-xl font-semibold text-zinc-900 mb-1">What are the current balances?</h1>
      <p className="text-sm text-zinc-500 mb-6">
        Balances as at {formatDate(fyStartDate)}. Leave blank if an account is empty.
      </p>

      <div className="space-y-3 mb-6">
        {accounts.map(a => (
          <div key={a.id} className="flex items-center gap-3">
            <span className="flex-1 text-sm text-zinc-700">{a.name}</span>
            <div className="flex items-center gap-1 border border-zinc-200 rounded-xl px-3 py-2 focus-within:ring-2 focus-within:ring-zinc-300">
              <span className="text-zinc-400 text-sm">₹</span>
              <input
                type="number"
                className="w-28 text-right text-sm font-mono focus:outline-none"
                placeholder="0"
                value={values[a.id] ?? ''}
                onChange={e => setValue(a.id, e.target.value)}
              />
            </div>
          </div>
        ))}
      </div>

      <PrimaryButton onClick={handleSave} disabled={saving}>
        {saving ? 'Saving…' : 'Continue'}
      </PrimaryButton>
      <SkipLink onClick={onSkip} />
    </StepCard>
  )
}

// ── Step 5: AI / LLM ─────────────────────────────────────────────────────────

type ConnStatus = 'idle' | 'loading' | 'ok' | 'fail'

function StepAi({ onNext, onSkip }: { onNext: (model: string) => void; onSkip: () => void }) {
  const [baseUrl, setBaseUrl] = useState('http://localhost:8001/v1')
  const [model, setModel] = useState('Qwen3.6-35B-A3B-MLX-VL-oQ4-FP16')
  const [apiKey, setApiKey] = useState('omlx')
  const [connStatus, setConnStatus] = useState<ConnStatus>('idle')
  const [connMsg, setConnMsg] = useState('Not tested')
  const [saving, setSaving] = useState(false)

  const testConnection = async () => {
    setConnStatus('loading')
    setConnMsg('Testing…')
    try {
      const result = await api.post<AiConnectionResult>('/ai/test-connection', { base_url: baseUrl, model, api_key: apiKey })
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

  const handleSave = async () => {
    setSaving(true)
    try {
      await api.post('/ai/config', { base_url: baseUrl, model, api_key: apiKey })
      onNext(model)
    } finally {
      setSaving(false)
    }
  }

  return (
    <StepCard>
      <ProgressDots current={5} total={7} />
      <h1 className="text-xl font-semibold text-zinc-900 mb-1">Connect an AI model</h1>
      <p className="text-sm text-zinc-500 mb-1">
        Stow uses a local OpenAI-compatible server for natural language transaction entry and smart account suggestions during bank import.
      </p>
      <p className="text-xs text-zinc-400 mb-6">Nothing leaves your machine.</p>

      <div className="space-y-4 mb-5">
        <div>
          <label className="block text-xs font-medium text-zinc-600 mb-1">
            Server URL <code className="ml-1 font-mono text-zinc-400 text-[10px]">STOW_LLM_BASE_URL</code>
          </label>
          <input
            type="url"
            className="w-full border border-zinc-200 rounded-xl px-3 py-2 text-sm font-mono focus:outline-none focus:ring-2 focus:ring-zinc-300"
            value={baseUrl}
            onChange={e => setBaseUrl(e.target.value)}
          />
          <p className="text-xs text-zinc-400 mt-1">
            oMLX: <code className="font-mono">http://localhost:8001/v1</code> · Ollama: <code className="font-mono">http://localhost:11434/v1</code>
          </p>
        </div>
        <div>
          <label className="block text-xs font-medium text-zinc-600 mb-1">
            Model name <code className="ml-1 font-mono text-zinc-400 text-[10px]">STOW_LLM_MODEL</code>
          </label>
          <input
            type="text"
            className="w-full border border-zinc-200 rounded-xl px-3 py-2 text-sm font-mono focus:outline-none focus:ring-2 focus:ring-zinc-300"
            value={model}
            onChange={e => setModel(e.target.value)}
          />
          <p className="text-xs text-zinc-400 mt-1">Must support function calling. Qwen3, Llama 3.1+, Mistral v0.3+ all work.</p>
        </div>
        <div>
          <label className="block text-xs font-medium text-zinc-600 mb-1">
            API key <span className="text-zinc-400 font-normal">(oMLX uses <code className="font-mono">omlx</code>)</span>
          </label>
          <input
            type="password"
            className="w-full border border-zinc-200 rounded-xl px-3 py-2 text-sm font-mono focus:outline-none focus:ring-2 focus:ring-zinc-300"
            placeholder="sk-..."
            value={apiKey}
            onChange={e => setApiKey(e.target.value)}
          />
        </div>

        <div className="flex items-center gap-3">
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
      </div>

      <PrimaryButton onClick={handleSave} disabled={saving}>
        {saving ? 'Saving…' : 'Save & continue'}
      </PrimaryButton>
      <SkipLink onClick={onSkip} label="Skip — I'll set this up later" />
    </StepCard>
  )
}

// ── Step 6: Telegram ──────────────────────────────────────────────────────────

function StepTelegram({ onNext, onSkip }: { onNext: (botUsername: string | null) => void; onSkip: () => void }) {
  const [botToken, setBotToken] = useState('')
  const [connStatus, setConnStatus] = useState<ConnStatus>('idle')
  const [connMsg, setConnMsg] = useState('Not tested')
  const [saving, setSaving] = useState(false)

  const testConnection = async () => {
    setConnStatus('loading')
    setConnMsg('Testing…')
    try {
      const result = await api.post<TelegramTestResult>('/telegram/test-connection', { bot_token: botToken })
      if (result.ok) {
        setConnStatus('ok')
        const label = result.bot_username ? `@${result.bot_username}` : result.bot_name ?? 'Bot'
        setConnMsg(`Connected · ${label}`)
      } else {
        setConnStatus('fail')
        setConnMsg(result.error ?? 'Connection failed')
      }
    } catch (e: unknown) {
      setConnStatus('fail')
      setConnMsg(e instanceof Error ? e.message : 'Connection failed')
    }
  }

  const handleSave = async () => {
    setSaving(true)
    try {
      const saved = await api.post<{ bot_username: string | null }>('/telegram/config', { bot_token: botToken })
      onNext(saved.bot_username)
    } finally {
      setSaving(false)
    }
  }

  return (
    <StepCard>
      <ProgressDots current={6} total={7} />
      <h1 className="text-xl font-semibold text-zinc-900 mb-1">Connect Telegram</h1>
      <p className="text-sm text-zinc-500 mb-1">
        Log transactions, check balances, and import bank statements from Telegram chat.
      </p>
      <p className="text-xs text-zinc-400 mb-6">Optional — you can set this up later in Settings.</p>

      <div className="space-y-4 mb-5">
        <div>
          <label className="block text-xs font-medium text-zinc-600 mb-1">
            Bot token <code className="ml-1 font-mono text-zinc-400 text-[10px]">TELEGRAM_BOT_TOKEN</code>
          </label>
          <input
            type="password"
            className="w-full border border-zinc-200 rounded-xl px-3 py-2 text-sm font-mono focus:outline-none focus:ring-2 focus:ring-zinc-300"
            placeholder="123456789:ABCdef..."
            value={botToken}
            onChange={e => setBotToken(e.target.value)}
          />
          <p className="text-xs text-zinc-400 mt-1">
            Create a bot with <span className="font-medium">@BotFather</span>, then paste the token here.
          </p>
        </div>

        <div className="flex items-center gap-3">
          <button
            onClick={testConnection}
            disabled={connStatus === 'loading' || !botToken.trim()}
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
      </div>

      <PrimaryButton onClick={handleSave} disabled={saving || !botToken.trim()}>
        {saving ? 'Saving…' : 'Save & continue'}
      </PrimaryButton>
      <SkipLink onClick={onSkip} label="Skip — I'll set this up later" />
    </StepCard>
  )
}

// ── Step 7: Done ──────────────────────────────────────────────────────────────

function StepDone({ fyLabel: fy, accountCount, llmModel, telegramBot, onFinish }: {
  fyLabel: string; accountCount: number; llmModel: string | null; telegramBot: string | null
  onFinish: (dest: '/' | '/transactions') => void
}) {
  return (
    <StepCard>
      <div className="text-center">
        <div className="flex justify-center mb-4">
          <CheckCircle2 size={48} className="text-emerald-500" />
        </div>
        <h1 className="text-2xl font-semibold text-zinc-900 mb-2">You're all set!</h1>
        <div className="text-sm text-zinc-500 space-y-1 mb-8">
          <p>Financial year: <span className="text-zinc-700 font-medium">{fy}</span></p>
          <p>
            Accounts added:{' '}
            <span className="text-zinc-700 font-medium">
              {accountCount > 0 ? accountCount : 'None yet'}
            </span>
          </p>
          {llmModel && (
            <p>AI connected: <span className="text-zinc-700 font-medium">{llmModel}</span></p>
          )}
          {telegramBot && (
            <p>Telegram: <span className="text-zinc-700 font-medium">@{telegramBot}</span></p>
          )}
        </div>

        <div className="space-y-2">
          <button
            onClick={() => onFinish('/')}
            className="block w-full py-2.5 bg-zinc-900 text-white rounded-xl font-medium hover:bg-zinc-700 transition-colors text-center"
          >
            Go to dashboard
          </button>
          <button
            onClick={() => onFinish('/transactions?new=1')}
            className="block w-full py-2.5 border border-zinc-200 text-zinc-700 rounded-xl font-medium hover:bg-zinc-50 transition-colors text-center text-sm"
          >
            Enter first transaction
          </button>
        </div>
      </div>
    </StepCard>
  )
}

// ── Main component ────────────────────────────────────────────────────────────

export default function Onboarding() {
  const navigate = useNavigate()
  const qc = useQueryClient()

  const { data: fys, isSuccess } = useQuery<FinancialYear[]>({
    queryKey: queryKeys.financialYears.all(),
    queryFn: () => api.get<FinancialYear[]>('/financial-years'),
    staleTime: 0,
  })

  // Reverse guard — only fires on initial load, not after we create the FY mid-wizard
  const guardChecked = useRef(false)
  useEffect(() => {
    if (isSuccess && !guardChecked.current) {
      guardChecked.current = true
      if (fys.length > 0) navigate('/', { replace: true })
    }
  }, [isSuccess, fys, navigate])

  const [step, setStep] = useState<1 | 2 | 3 | 4 | 5 | 6 | 7>(1)
  const [fyId, setFyId] = useState<number | null>(null)
  const [fyStartDate, setFyStartDate] = useState('')
  const [fyLabelStr, setFyLabelStr] = useState('')
  const [createdAccounts, setCreatedAccounts] = useState<Array<{ id: number; name: string }>>([])
  const [llmModel, setLlmModel] = useState<string | null>(null)
  const [telegramBot, setTelegramBot] = useState<string | null>(null)

  const afterFy = (id: number, startDate: string, label: string) => {
    // Don't invalidate here — that would trigger the reverse guard and skip steps 3-6.
    // We invalidate at the very end in onFinish.
    setFyId(id)
    setFyStartDate(startDate)
    setFyLabelStr(label)
    setStep(3)
  }

  const afterAccounts = (accounts: Array<{ id: number; name: string }>) => {
    setCreatedAccounts(accounts)
    setStep(accounts.length > 0 ? 4 : 5)
  }

  const skipAccounts = () => setStep(5)

  const afterBalances = () => setStep(5)
  const skipBalances = () => setStep(5)

  const afterAi = (model: string) => {
    setLlmModel(model)
    setStep(6)
  }

  const skipAi = () => setStep(6)

  const afterTelegram = (botUsername: string | null) => {
    setTelegramBot(botUsername)
    setStep(7)
  }

  const skipTelegram = () => setStep(7)

  // Await invalidation before navigating so RequireSetup sees the new FY in cache
  const onFinish = async (dest: string) => {
    await qc.invalidateQueries({ queryKey: queryKeys.financialYears.all() })
    navigate(dest, { replace: true })
  }

  if (step === 1) return <StepWelcome onNext={() => setStep(2)} />

  if (step === 2) return <StepFinancialYear onNext={afterFy} />

  if (step === 3) return (
    <StepBankAccounts onNext={afterAccounts} onSkip={skipAccounts} />
  )

  if (step === 4 && fyId !== null) return (
    <StepOpeningBalances
      accounts={createdAccounts}
      fyId={fyId}
      fyStartDate={fyStartDate}
      onNext={afterBalances}
      onSkip={skipBalances}
    />
  )

  if (step === 5) return <StepAi onNext={afterAi} onSkip={skipAi} />

  if (step === 6) return <StepTelegram onNext={afterTelegram} onSkip={skipTelegram} />

  return (
    <StepDone
      fyLabel={fyLabelStr}
      accountCount={createdAccounts.length}
      llmModel={llmModel}
      telegramBot={telegramBot}
      onFinish={onFinish}
    />
  )
}
