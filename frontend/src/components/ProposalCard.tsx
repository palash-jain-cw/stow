import { useState } from 'react'
import { Check, X, Pencil, ArrowRight } from 'lucide-react'

// ── Types ──────────────────────────────────────────────────────────────────

export interface Proposal {
  type: string
  date: string
  amount_paise: number
  narration?: string
  from_account_id: number
  from_account_name: string
  to_account_id: number
  to_account_name: string
  fy_id: number
}

interface ProposalCardProps {
  proposal: Proposal
  display: string       // human-readable text from orchestrator (minus the PROPOSAL: line)
  onAction: (action: string) => void
  disabled?: boolean
}

// ── Helpers ────────────────────────────────────────────────────────────────

const TYPE_LABELS: Record<string, string> = {
  payment: 'Payment',
  receipt: 'Receipt',
  journal: 'Journal',
  contra: 'Contra',
}

function formatAmount(paise: number): string {
  const rupees = paise / 100
  return '₹' + rupees.toLocaleString('en-IN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}

function formatDate(iso: string): string {
  return new Date(iso).toLocaleDateString('en-IN', { day: 'numeric', month: 'short', year: 'numeric' })
}

// ── ProposalCard ───────────────────────────────────────────────────────────

export function ProposalCard({ proposal, display, onAction, disabled = false }: ProposalCardProps) {
  const [acted, setAct] = useState<string | null>(null)

  function handleAction(action: string) {
    if (acted || disabled) return
    setAct(action)
    onAction(action)
  }

  return (
    <div className="max-w-[85%] rounded-2xl rounded-bl-sm border border-zinc-200 bg-white overflow-hidden shadow-sm text-sm">
      {/* Header strip */}
      <div className="px-3 py-2 bg-zinc-50 border-b border-zinc-100">
        <span className="text-xs font-semibold text-zinc-500 uppercase tracking-wide">
          Proposed transaction
        </span>
      </div>

      {/* Fields */}
      <div className="px-3 py-2.5 space-y-1.5">
        <Row label="Type" value={TYPE_LABELS[proposal.type] ?? proposal.type} />
        <Row label="Amount" value={formatAmount(proposal.amount_paise)} mono />
        <Row label="Date" value={formatDate(proposal.date)} />
        <div className="flex items-center gap-1 text-xs text-zinc-700">
          <span className="text-zinc-400 w-14 shrink-0">Route</span>
          <span className="font-medium truncate">{proposal.from_account_name}</span>
          <ArrowRight className="w-3 h-3 text-zinc-400 shrink-0" />
          <span className="font-medium truncate">{proposal.to_account_name}</span>
        </div>
        {proposal.narration && (
          <Row label="Note" value={proposal.narration} />
        )}
      </div>

      {/* Human-readable context (orchestrator text below the proposal line) */}
      {display && (
        <div className="px-3 pb-2 text-xs text-zinc-500 leading-relaxed whitespace-pre-wrap">
          {display}
        </div>
      )}

      {/* Actions */}
      <div className="flex border-t border-zinc-100">
        <ActionButton
          label="Confirm"
          icon={<Check className="w-3.5 h-3.5" />}
          onClick={() => handleAction('confirm')}
          active={acted === 'confirm'}
          disabled={!!acted || disabled}
          variant="confirm"
        />
        <ActionButton
          label="Edit"
          icon={<Pencil className="w-3.5 h-3.5" />}
          onClick={() => handleAction('edit')}
          active={acted === 'edit'}
          disabled={!!acted || disabled}
          variant="edit"
        />
        <ActionButton
          label="Decline"
          icon={<X className="w-3.5 h-3.5" />}
          onClick={() => handleAction('decline')}
          active={acted === 'decline'}
          disabled={!!acted || disabled}
          variant="decline"
        />
      </div>
    </div>
  )
}

// ── Sub-components ─────────────────────────────────────────────────────────

function Row({ label, value, mono }: { label: string; value: string; mono?: boolean }) {
  return (
    <div className="flex items-baseline gap-2 text-xs">
      <span className="text-zinc-400 w-14 shrink-0">{label}</span>
      <span className={`text-zinc-800 font-medium ${mono ? 'font-mono' : ''}`}>{value}</span>
    </div>
  )
}

type Variant = 'confirm' | 'edit' | 'decline'

const VARIANT_STYLES: Record<Variant, { base: string; active: string }> = {
  confirm: {
    base: 'text-emerald-600 hover:bg-emerald-50',
    active: 'bg-emerald-50 text-emerald-700',
  },
  edit: {
    base: 'text-zinc-500 hover:bg-zinc-50',
    active: 'bg-zinc-100 text-zinc-700',
  },
  decline: {
    base: 'text-red-500 hover:bg-red-50',
    active: 'bg-red-50 text-red-600',
  },
}

function ActionButton({
  label,
  icon,
  onClick,
  active,
  disabled,
  variant,
}: {
  label: string
  icon: React.ReactNode
  onClick: () => void
  active: boolean
  disabled: boolean
  variant: Variant
}) {
  const styles = VARIANT_STYLES[variant]
  return (
    <button
      onClick={onClick}
      disabled={disabled}
      className={`flex-1 flex items-center justify-center gap-1.5 py-2 text-xs font-medium transition-colors
        border-r last:border-r-0 border-zinc-100
        disabled:opacity-40 disabled:cursor-default
        ${active ? styles.active : styles.base}`}
    >
      {icon}
      {label}
    </button>
  )
}
