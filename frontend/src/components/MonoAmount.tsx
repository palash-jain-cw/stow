const fmt = new Intl.NumberFormat('en-IN', {
  style: 'currency',
  currency: 'INR',
  minimumFractionDigits: 2,
})

interface MonoAmountProps {
  /** Amount in paise */
  amount: number
  /** Apply emerald/red colouring based on sign. Default true. */
  colored?: boolean
  className?: string
}

export function MonoAmount({ amount, colored = true, className = '' }: MonoAmountProps) {
  const formatted = fmt.format(amount / 100)
  const colorClass = colored
    ? amount > 0
      ? 'text-emerald-600'
      : amount < 0
        ? 'text-red-600'
        : ''
    : ''
  return (
    <span className={`font-mono font-medium ${colorClass} ${className}`}>
      {formatted}
    </span>
  )
}
