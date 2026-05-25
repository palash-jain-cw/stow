/** Normalize merchant rule patterns — bare text matches as substring (via *text*). */
export function normalizeMerchantPattern(pattern: string): string {
  const trimmed = pattern.trim()
  if (!trimmed) return trimmed
  if (!trimmed.includes('*') && !trimmed.includes('?')) {
    return `*${trimmed}*`
  }
  return trimmed
}

/** Case-insensitive fnmatch-style match (supports * and ?). */
export function merchantPatternMatches(description: string, pattern: string): boolean {
  const normalized = normalizeMerchantPattern(pattern)
  if (!normalized) return false
  const escaped = normalized
    .replace(/[.+^${}()|[\]\\]/g, '\\$&')
    .replace(/\*/g, '.*')
    .replace(/\?/g, '.')
  return new RegExp(`^${escaped}$`, 'i').test(description)
}

export function defaultImportAccountId(
  amountPaise: number,
  miscExpenseId: number | null,
  miscIncomeId: number | null,
): number | null {
  return amountPaise < 0 ? miscExpenseId : miscIncomeId
}

export function rowEligibleForRuleApply(
  status: string,
  accountId: number | null,
  amountPaise: number,
  miscExpenseId: number | null,
  miscIncomeId: number | null,
): boolean {
  if (status === 'reconciled' || status === 'discarded') return false
  const defaultId = defaultImportAccountId(amountPaise, miscExpenseId, miscIncomeId)
  return accountId === null || accountId === defaultId
}
