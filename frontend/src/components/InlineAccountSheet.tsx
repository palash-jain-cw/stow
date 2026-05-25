import { useQuery } from '@tanstack/react-query'
import { AccountSheet } from './AccountSheet'
import { api, queryKeys } from '../api/api'
import { resolveActiveFy } from './investmentHelpers'

interface AccountGroup {
  id: number
  name: string
  nature: string
  parent_id: number | null
  sort_order: number
  cash_flow_tag: string | null
}

interface InlineAccountSheetProps {
  open: boolean
  onClose: () => void
  onCreated: (accountId: number) => void
  initialGroupId?: number
}

export function findAccountGroupId(
  groups: { id: number; name: string }[],
  name: string,
): number | undefined {
  return groups.find(g => g.name === name)?.id
}

/** Account creation sheet loaded on demand for inline "new account" flows. */
export function InlineAccountSheet({
  open,
  onClose,
  onCreated,
  initialGroupId,
}: InlineAccountSheetProps) {
  const { data: groups = [] } = useQuery({
    queryKey: queryKeys.accountGroups.all(),
    queryFn: () => api.get<AccountGroup[]>('/account-groups'),
    enabled: open,
  })

  const { data: fys = [] } = useQuery({
    queryKey: queryKeys.financialYears.all(),
    queryFn: () => api.get<{ id: number; status: string }[]>('/financial-years'),
    enabled: open,
  })

  const activeFyId = resolveActiveFy(fys)?.id

  return (
    <AccountSheet
      open={open}
      onClose={onClose}
      groups={groups}
      activeFyId={activeFyId}
      initialGroupId={initialGroupId}
      onSaved={accountId => {
        if (accountId != null) onCreated(accountId)
      }}
    />
  )
}
