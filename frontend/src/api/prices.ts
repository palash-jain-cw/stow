import { api } from './api'

/** Fetch latest NAV/prices for all accounts that have a price_source_id. */
export async function refreshAllLivePrices(): Promise<void> {
  try {
    await api.post<unknown[]>('/prices/fetch-all', {})
  } catch {
    // Portfolio still renders using any quotes already on file.
  }
}

/** Fetch latest NAV/price for one investment account. */
export async function refreshLivePrice(accountId: number): Promise<void> {
  try {
    await api.post(`/prices/fetch/${accountId}`, {})
  } catch {
    // Caller may still show cost basis only.
  }
}
