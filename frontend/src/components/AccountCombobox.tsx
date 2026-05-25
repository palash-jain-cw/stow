import { useState, useEffect, useRef } from 'react'
import { Plus } from 'lucide-react'
import { Tooltip } from './Tooltip'
import { InlineAccountSheet } from './InlineAccountSheet'
import type { AccountPick } from './AccountSelect'

interface GroupedSection {
  nature: string
  items: AccountPick[]
  startIdx: number
}

function FieldLabel({ children }: { children: React.ReactNode }) {
  return (
    <label className="block text-xs font-semibold text-zinc-500 uppercase tracking-wide mb-2">
      {children}
    </label>
  )
}

function inputCls(error?: boolean) {
  return (
    'w-full px-3.5 py-2.5 text-sm border border-zinc-200 rounded-xl focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent transition bg-white' +
    (error ? ' border-red-400 focus:ring-red-400' : '')
  )
}

export interface AccountComboboxProps {
  label: string
  tooltip: string
  value: number | null
  onChange: (id: number | null) => void
  accounts: AccountPick[]
  error?: string
  initialGroupId?: number
  allowCreate?: boolean
}

export function AccountCombobox({
  label,
  tooltip,
  value,
  onChange,
  accounts,
  error,
  initialGroupId,
  allowCreate = true,
}: AccountComboboxProps) {
  const [query, setQuery] = useState(() => accounts.find(a => a.id === value)?.name ?? '')
  const [open, setOpen] = useState(false)
  const [createOpen, setCreateOpen] = useState(false)
  const [highlightedIdx, setHighlightedIdx] = useState(0)
  const containerRef = useRef<HTMLDivElement>(null)
  const listRef = useRef<HTMLUListElement>(null)

  useEffect(() => {
    const acc = accounts.find(a => a.id === value)
    setQuery(acc?.name ?? '')
  }, [value, accounts])

  useEffect(() => {
    const handler = (e: MouseEvent) => {
      if (containerRef.current && !containerRef.current.contains(e.target as Node)) {
        setOpen(false)
        const acc = accounts.find(a => a.id === value)
        setQuery(acc?.name ?? '')
      }
    }
    document.addEventListener('mousedown', handler)
    return () => document.removeEventListener('mousedown', handler)
  }, [value, accounts])

  const filtered = query.trim() === ''
    ? accounts
    : accounts.filter(a => a.name.toLowerCase().includes(query.trim().toLowerCase()))

  useEffect(() => {
    setHighlightedIdx(0)
  }, [query])

  useEffect(() => {
    if (open && listRef.current) {
      const item = listRef.current.children[highlightedIdx] as HTMLElement | undefined
      item?.scrollIntoView({ block: 'nearest' })
    }
  }, [highlightedIdx, open])

  const selectAccount = (acc: AccountPick) => {
    onChange(acc.id)
    setQuery(acc.name)
    setOpen(false)
  }

  const openCreateSheet = () => {
    setOpen(false)
    const acc = accounts.find(a => a.id === value)
    setQuery(acc?.name ?? '')
    setCreateOpen(true)
  }

  const handleKeyDown = (e: React.KeyboardEvent<HTMLInputElement>) => {
    if (!open) {
      if (e.key === 'ArrowDown' || e.key === 'ArrowUp' || e.key === 'Enter') {
        setOpen(true)
        e.preventDefault()
      }
      return
    }
    if (e.key === 'ArrowDown') {
      e.preventDefault()
      setHighlightedIdx(i => Math.min(i + 1, filtered.length - 1))
    } else if (e.key === 'ArrowUp') {
      e.preventDefault()
      setHighlightedIdx(i => Math.max(i - 1, 0))
    } else if (e.key === 'Enter') {
      e.preventDefault()
      if (filtered[highlightedIdx]) {
        selectAccount(filtered[highlightedIdx])
      }
    } else if (e.key === 'Escape') {
      e.preventDefault()
      setOpen(false)
      const acc = accounts.find(a => a.id === value)
      setQuery(acc?.name ?? '')
    } else if (e.key === 'Tab') {
      setOpen(false)
      const acc = accounts.find(a => a.id === value)
      setQuery(acc?.name ?? '')
    }
  }

  const natures = ['asset', 'liability', 'equity', 'income', 'expense']
  const groups: GroupedSection[] = []
  let idx = 0
  for (const nature of natures) {
    const items = filtered.filter(a => a.nature === nature)
    if (items.length > 0) {
      groups.push({ nature, items, startIdx: idx })
      idx += items.length
    }
  }

  return (
    <>
      <div ref={containerRef} className="relative">
        <div className="flex items-center gap-1.5 mb-2">
          <FieldLabel>{label}</FieldLabel>
          <Tooltip content={tooltip} />
        </div>
        <input
          type="text"
          role="combobox"
          aria-expanded={open}
          aria-autocomplete="list"
          autoComplete="off"
          value={query}
          placeholder="Type to search accounts…"
          onChange={e => {
            setQuery(e.target.value)
            setOpen(true)
            if (e.target.value === '') {
              onChange(null)
            }
          }}
          onFocus={() => setOpen(true)}
          onKeyDown={handleKeyDown}
          className={inputCls(!!error)}
        />
        {error && (
          <p className="mt-1 text-xs text-red-500">{error}</p>
        )}

        {open && (
          <ul
            ref={listRef}
            role="listbox"
            className="absolute z-50 mt-1 w-full bg-white border border-zinc-200 rounded-xl shadow-lg max-h-56 overflow-y-auto"
          >
            {filtered.length === 0 ? (
              <li className="px-3.5 py-2.5 text-sm text-zinc-400">No accounts found</li>
            ) : (
              groups.map(group => (
                <li key={group.nature}>
                  <div className="px-3 pt-2 pb-0.5 text-[10px] font-semibold uppercase tracking-widest text-zinc-400 select-none">
                    {group.nature.charAt(0).toUpperCase() + group.nature.slice(1)}
                  </div>
                  <ul>
                    {group.items.map((acc, relIdx) => {
                      const absIdx = group.startIdx + relIdx
                      const isHighlighted = absIdx === highlightedIdx
                      return (
                        <li
                          key={acc.id}
                          role="option"
                          aria-selected={acc.id === value}
                          onMouseDown={e => {
                            e.preventDefault()
                            selectAccount(acc)
                          }}
                          onMouseEnter={() => setHighlightedIdx(absIdx)}
                          className={`px-3.5 py-2 text-sm cursor-pointer select-none ${
                            isHighlighted
                              ? 'bg-blue-50 text-blue-700'
                              : acc.id === value
                              ? 'bg-zinc-50 text-zinc-900 font-medium'
                              : 'text-zinc-700 hover:bg-zinc-50'
                          }`}
                        >
                          {acc.name}
                        </li>
                      )
                    })}
                  </ul>
                </li>
              ))
            )}
            {allowCreate && (
              <li className="sticky bottom-0 border-t border-zinc-100 bg-white">
                <button
                  type="button"
                  onMouseDown={e => {
                    e.preventDefault()
                    openCreateSheet()
                  }}
                  className="w-full flex items-center gap-2 px-3.5 py-2.5 text-sm text-blue-600 hover:bg-blue-50 transition-colors"
                >
                  <Plus className="w-3.5 h-3.5" />
                  New account…
                </button>
              </li>
            )}
          </ul>
        )}
      </div>

      <InlineAccountSheet
        open={createOpen}
        onClose={() => setCreateOpen(false)}
        initialGroupId={initialGroupId}
        onCreated={accountId => {
          onChange(accountId)
          setCreateOpen(false)
        }}
      />
    </>
  )
}
