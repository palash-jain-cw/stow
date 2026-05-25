import { memo, useEffect, useState, type KeyboardEvent } from 'react'
import { AlertTriangle, CheckCircle2 } from 'lucide-react'
import { MonoAmount } from './MonoAmount'
import { AccountSelect, type AccountPick } from './AccountSelect'

export interface ImportRowDraft {
  id: number
  date: string
  amount: number
  description: string
  possible_duplicate: boolean
  status: 'pending' | 'confirmed' | 'discarded' | 'reconciled'
  accountId: number | null
  narration: string
  tags: string
}

export type ImportRowField = 'include' | 'account' | 'narration' | 'tags'

const inputCls =
  'w-full min-w-0 px-2 py-1.5 text-xs border border-zinc-200 rounded-lg bg-white focus:outline-none focus:ring-1 focus:ring-zinc-400'

function formatDate(iso: string) {
  return new Date(iso).toLocaleDateString('en-IN', { day: 'numeric', month: 'short', year: 'numeric' })
}

function rowIsIncluded(row: ImportRowDraft): boolean {
  return row.status === 'confirmed' || row.status === 'reconciled' ||
    (row.status === 'pending' && row.accountId !== null)
}

function ImportCheckbox({
  row,
  onChange,
  inputRef,
  onFocus,
  onKeyDown,
}: {
  row: ImportRowDraft
  onChange: (included: boolean) => void
  inputRef?: (el: HTMLInputElement | null) => void
  onFocus?: () => void
  onKeyDown?: (e: KeyboardEvent<HTMLInputElement>) => void
}) {
  if (row.status === 'reconciled') {
    return (
      <span title="Already matched to an existing transaction">
        <CheckCircle2 className="w-4 h-4 text-emerald-600" />
      </span>
    )
  }
  const included = rowIsIncluded(row)
  return (
    <input
      ref={inputRef}
      type="checkbox"
      checked={included}
      onChange={e => onChange(e.target.checked)}
      onFocus={onFocus}
      onKeyDown={onKeyDown}
      aria-label={`Include ${row.description}`}
      className="rounded border-zinc-300 focus:ring-2 focus:ring-zinc-400 focus:ring-offset-1"
      title={included ? 'Include in import (Space to toggle)' : 'Skip this row (Space to toggle)'}
    />
  )
}

export interface ImportReviewRowProps {
  row: ImportRowDraft
  accounts: AccountPick[]
  isFocusedRow: boolean
  setRowRef: (el: HTMLTableRowElement | null) => void
  registerFieldRef: (field: ImportRowField, el: HTMLElement | null) => void
  onIncludedChange: (rowId: number, included: boolean) => void
  onAccountChange: (rowId: number, accountId: number | null) => void
  onNarrationCommit: (rowId: number, narration: string) => void
  onTagsCommit: (rowId: number, tags: string) => void
  onFocusField: (rowId: number, field: ImportRowField) => void
  onFieldKeyDown: (e: KeyboardEvent, row: ImportRowDraft, field: ImportRowField) => void
}

export const ImportReviewRow = memo(function ImportReviewRow({
  row,
  accounts,
  isFocusedRow,
  setRowRef,
  registerFieldRef,
  onIncludedChange,
  onAccountChange,
  onNarrationCommit,
  onTagsCommit,
  onFocusField,
  onFieldKeyDown,
}: ImportReviewRowProps) {
  const included = rowIsIncluded(row)
  const dimmed = row.status === 'discarded'
  const [narration, setNarration] = useState(row.narration)
  const [tags, setTags] = useState(row.tags)

  useEffect(() => {
    setNarration(row.narration)
    setTags(row.tags)
  }, [row.id, row.narration, row.tags])

  return (
    <tr
      ref={setRowRef}
      className={`border-b border-zinc-100 align-top ${
        row.status === 'reconciled' ? 'bg-emerald-50/50' :
        row.possible_duplicate && included ? 'bg-amber-50/40' :
        dimmed ? 'opacity-45' :
        isFocusedRow ? 'bg-blue-50/60 ring-1 ring-inset ring-blue-200' :
        'hover:bg-zinc-50/80'
      }`}
    >
      <td className="px-3 py-2">
        <ImportCheckbox
          row={row}
          onChange={v => onIncludedChange(row.id, v)}
          inputRef={el => registerFieldRef('include', el)}
          onFocus={() => onFocusField(row.id, 'include')}
          onKeyDown={e => onFieldKeyDown(e, row, 'include')}
        />
      </td>
      <td className="px-2 py-2 font-mono text-xs text-zinc-600 whitespace-nowrap">
        {formatDate(row.date)}
      </td>
      <td className="px-2 py-2 text-right whitespace-nowrap">
        <MonoAmount amount={row.amount} className="text-sm" />
      </td>
      <td className="px-2 py-2">
        <div className="flex flex-col gap-0.5 min-w-0">
          <p className="text-sm font-medium text-zinc-900 truncate" title={row.description}>
            {row.description}
          </p>
          {row.possible_duplicate && row.status !== 'reconciled' && (
            <span className="inline-flex items-center gap-1 text-[10px] text-amber-700">
              <AlertTriangle className="w-3 h-3 shrink-0" />
              Possible duplicate
            </span>
          )}
          {row.status === 'reconciled' && (
            <span className="inline-flex items-center gap-1 text-[10px] text-emerald-700">
              <CheckCircle2 className="w-3 h-3 shrink-0" />
              Matches existing transaction
            </span>
          )}
        </div>
      </td>
      <td className="px-2 py-2">
        {row.status === 'reconciled' ? (
          <span className="text-xs text-emerald-700 font-medium">Reconciled</span>
        ) : (
          <AccountSelect
            value={row.accountId}
            onChange={id => onAccountChange(row.id, id)}
            accounts={accounts}
            placeholder="Pick account"
            size="sm"
            className="w-full min-w-[140px] disabled:opacity-50"
            disabled={dimmed}
            ariaLabel={`Account for ${row.description}`}
            selectRef={el => registerFieldRef('account', el)}
            onFocus={() => onFocusField(row.id, 'account')}
            onKeyDown={e => onFieldKeyDown(e, row, 'account')}
          />
        )}
      </td>
      <td className="px-2 py-2">
        {row.status === 'reconciled' ? (
          <span className="text-xs text-zinc-500 truncate block">{row.narration}</span>
        ) : (
          <input
            type="text"
            ref={el => registerFieldRef('narration', el)}
            value={narration}
            onChange={e => setNarration(e.target.value)}
            onBlur={() => {
              if (narration !== row.narration) onNarrationCommit(row.id, narration)
            }}
            onFocus={() => onFocusField(row.id, 'narration')}
            onKeyDown={e => onFieldKeyDown(e, row, 'narration')}
            disabled={dimmed}
            aria-label={`Narration for ${row.description}`}
            className={`${inputCls} disabled:bg-zinc-50 disabled:text-zinc-400`}
          />
        )}
      </td>
      <td className="px-3 py-2">
        {row.status === 'reconciled' ? (
          <span className="text-xs text-zinc-400">—</span>
        ) : (
          <input
            type="text"
            ref={el => registerFieldRef('tags', el)}
            value={tags}
            onChange={e => setTags(e.target.value)}
            onBlur={() => {
              if (tags !== row.tags) onTagsCommit(row.id, tags)
            }}
            onFocus={() => onFocusField(row.id, 'tags')}
            onKeyDown={e => onFieldKeyDown(e, row, 'tags')}
            placeholder="utilities, home"
            disabled={dimmed}
            aria-label={`Tags for ${row.description}`}
            className={`${inputCls} text-zinc-600 disabled:bg-zinc-50 disabled:text-zinc-400`}
          />
        )}
      </td>
    </tr>
  )
})
