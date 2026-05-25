import { useState } from 'react'
import type { FocusEventHandler, KeyboardEventHandler, Ref } from 'react'
import { InlineAccountSheet } from './InlineAccountSheet'

export const CREATE_ACCOUNT_VALUE = '__create_account__'

export interface AccountPick {
  id: number
  name: string
  group_name?: string
  nature?: string
}

const SIZE_CLS = {
  sm: 'text-xs border border-zinc-200 rounded-lg px-2.5 py-1.5 bg-white focus:outline-none focus:ring-1 focus:ring-zinc-400',
  md: 'w-full px-3.5 py-2.5 text-sm border border-zinc-200 rounded-xl focus:outline-none focus:ring-2 focus:ring-blue-500 bg-white',
} as const

interface AccountSelectProps {
  value: number | '' | null
  onChange: (id: number | null) => void
  accounts: AccountPick[]
  placeholder?: string
  className?: string
  disabled?: boolean
  id?: string
  ariaLabel?: string
  /** Pre-select group in the new-account sheet (e.g. Bank Accounts). */
  initialGroupId?: number
  showGroupName?: boolean
  groupByNature?: boolean
  size?: keyof typeof SIZE_CLS
  allowCreate?: boolean
  selectRef?: Ref<HTMLSelectElement>
  onFocus?: FocusEventHandler<HTMLSelectElement>
  onKeyDown?: KeyboardEventHandler<HTMLSelectElement>
}

function optionLabel(account: AccountPick, showGroupName: boolean) {
  if (showGroupName && account.group_name) {
    return `${account.name} — ${account.group_name}`
  }
  return account.name
}

function AccountOptions({
  accounts,
  showGroupName,
  groupByNature,
}: {
  accounts: AccountPick[]
  showGroupName: boolean
  groupByNature: boolean
}) {
  if (!groupByNature) {
    return accounts.map(a => (
      <option key={a.id} value={a.id}>{optionLabel(a, showGroupName)}</option>
    ))
  }

  const assets = accounts.filter(a => a.nature === 'asset')
  const others = accounts.filter(a => a.nature !== 'asset')

  return (
    <>
      {assets.map(a => (
        <option key={a.id} value={a.id}>{optionLabel(a, showGroupName)}</option>
      ))}
      {others.length > 0 && (
        <optgroup label="Other accounts">
          {others.map(a => (
            <option key={a.id} value={a.id}>{optionLabel(a, showGroupName)}</option>
          ))}
        </optgroup>
      )}
    </>
  )
}

export function AccountSelect({
  value,
  onChange,
  accounts,
  placeholder = 'Select account…',
  className,
  disabled,
  id,
  ariaLabel,
  initialGroupId,
  showGroupName = false,
  groupByNature = false,
  size = 'md',
  allowCreate = true,
  selectRef,
  onFocus,
  onKeyDown,
}: AccountSelectProps) {
  const [createOpen, setCreateOpen] = useState(false)

  const selectValue = value === '' || value == null ? '' : String(value)
  const sizeCls = SIZE_CLS[size]
  const combinedCls = className ? `${sizeCls} ${className}` : sizeCls

  const handleChange = (e: React.ChangeEvent<HTMLSelectElement>) => {
    const raw = e.target.value
    if (raw === CREATE_ACCOUNT_VALUE) {
      e.target.value = selectValue
      setCreateOpen(true)
      return
    }
    onChange(raw === '' ? null : Number(raw))
  }

  return (
    <>
      <select
        ref={selectRef}
        id={id}
        aria-label={ariaLabel}
        value={selectValue}
        onChange={handleChange}
        onFocus={onFocus}
        onKeyDown={onKeyDown}
        disabled={disabled}
        className={combinedCls}
      >
        <option value="">{placeholder}</option>
        <AccountOptions
          accounts={accounts}
          showGroupName={showGroupName}
          groupByNature={groupByNature}
        />
        {allowCreate && (
          <option value={CREATE_ACCOUNT_VALUE}>+ New account…</option>
        )}
      </select>

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
