import { useState } from 'react'
import { HelpCircle } from 'lucide-react'

interface TooltipProps {
  content: string
  children?: React.ReactNode
}

export function Tooltip({ content, children }: TooltipProps) {
  const [show, setShow] = useState(false)
  return (
    <span className="relative inline-flex items-center">
      <span
        onMouseEnter={() => setShow(true)}
        onMouseLeave={() => setShow(false)}
        className="cursor-help"
      >
        {children ?? <HelpCircle className="w-3 h-3 text-zinc-400" />}
      </span>
      {show && (
        <span className="absolute bottom-full left-1/2 -translate-x-1/2 mb-1.5 z-50 w-52 bg-zinc-900 text-white text-xs rounded-lg px-3 py-2 shadow-lg pointer-events-none leading-relaxed">
          {content}
        </span>
      )}
    </span>
  )
}
