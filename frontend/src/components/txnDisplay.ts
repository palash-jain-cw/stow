import type { TxnType } from './TxnBadge'

export interface TxnDisplayAmount {
  /** Signed paise for MonoAmount (positive = incoming, negative = outgoing). */
  amount: number
  colored: boolean
}

/** Largest absolute debit entry amount — the usual row total for a transaction. */
export function transactionAbsoluteAmount(entries: Array<{ amount: number }>): number {
  const debits = entries.filter((e) => e.amount > 0)
  if (debits.length) return Math.max(...debits.map((e) => e.amount))
  return Math.abs(entries[0]?.amount ?? 0)
}

/** Map txn type to signed amount for user-facing green (incoming) / red (outgoing) display. */
export function signedTxnDisplayAmount(type: string, absolutePaise: number): TxnDisplayAmount {
  const amt = Math.abs(absolutePaise)
  if (type === 'receipt') {
    return { amount: amt, colored: true }
  }
  if (type === 'payment') {
    return { amount: -amt, colored: true }
  }
  return { amount: amt, colored: false }
}

export function txnDisplayFromEntries(
  type: TxnType | string,
  entries: Array<{ amount: number }>,
): TxnDisplayAmount {
  return signedTxnDisplayAmount(type, transactionAbsoluteAmount(entries))
}
