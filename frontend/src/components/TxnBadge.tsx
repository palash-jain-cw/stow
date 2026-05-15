export type TxnType = 'payment' | 'receipt' | 'journal' | 'contra'

const config: Record<TxnType, { label: string; className: string }> = {
  payment: { label: 'PAY', className: 'bg-red-100 text-red-700' },
  receipt: { label: 'REC', className: 'bg-emerald-100 text-emerald-700' },
  journal: { label: 'JNL', className: 'bg-blue-100 text-blue-700' },
  contra:  { label: 'CTR', className: 'bg-zinc-100 text-zinc-700' },
}

export function TxnBadge({ type }: { type: TxnType }) {
  const { label, className } = config[type]
  return (
    <span className={`inline-flex items-center px-2 py-0.5 rounded text-xs font-medium font-mono ${className}`}>
      {label}
    </span>
  )
}
