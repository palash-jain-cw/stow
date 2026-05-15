import type { LucideIcon } from 'lucide-react'

interface EmptyStateProps {
  icon: LucideIcon
  heading: string
  subtext: string
}

export function EmptyState({ icon: Icon, heading, subtext }: EmptyStateProps) {
  return (
    <div className="flex flex-col items-center justify-center py-16 text-center">
      <div className="w-12 h-12 rounded-xl bg-zinc-100 flex items-center justify-center mb-4">
        <Icon className="w-6 h-6 text-zinc-400" />
      </div>
      <p className="text-sm font-medium text-zinc-700">{heading}</p>
      <p className="text-sm text-zinc-400 mt-1 max-w-xs">{subtext}</p>
    </div>
  )
}
