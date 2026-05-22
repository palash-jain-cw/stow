import { Page, expect } from '@playwright/test'

/** Open the transaction entry sheet from wherever. */
export async function openNewTransactionSheet(page: Page): Promise<void> {
  // Works from the Transactions page button or the Dashboard quick-entry bar
  const btn = page.getByRole('button', { name: /New [Tt]ransaction/ })
  if (await btn.isVisible()) {
    await btn.click()
  } else {
    // Dashboard quick-entry bar (a div, not a button)
    await page.locator('text=New transaction…').click()
  }
  await expect(page.getByRole('dialog')).toBeVisible()
}

/** Fill a transaction in the entry sheet. Assumes the sheet is already open. */
export async function fillTransaction(
  page: Page,
  opts: {
    type?: 'Payment' | 'Receipt' | 'Journal' | 'Contra'
    amount: string
    narration: string
    date?: string
    fromAccount?: string
    toAccount?: string
    tags?: string[]
  },
): Promise<void> {
  const dialog = page.getByRole('dialog')

  if (opts.type) {
    await dialog.getByRole('button', { name: opts.type }).click()
  }

  await dialog.getByRole('spinbutton').fill(opts.amount)
  await dialog.getByRole('textbox', { name: /What was this for/ }).fill(opts.narration)

  if (opts.date) {
    const dateInput = dialog.getByRole('textbox').filter({ hasText: '' }).last()
    await dateInput.fill(opts.date)
  }

  if (opts.fromAccount) {
    const [from] = await dialog.getByRole('combobox').all()
    await from.fill(opts.fromAccount)
    await page.getByRole('option', { name: opts.fromAccount }).click()
  }

  if (opts.toAccount) {
    const combos = await dialog.getByRole('combobox').all()
    const to = combos[combos.length - 1]
    await to.fill(opts.toAccount)
    await page.getByRole('option', { name: opts.toAccount }).click()
  }

  for (const tag of opts.tags ?? []) {
    await dialog.getByRole('textbox', { name: 'Add tag' }).fill(tag)
    await dialog.getByRole('button', { name: 'Add' }).click()
  }
}

/** Save the open transaction sheet and wait for it to close. */
export async function saveTransaction(page: Page): Promise<void> {
  const dialog = page.getByRole('dialog')
  await dialog.getByRole('button', { name: 'Save' }).click()
  await expect(dialog).not.toBeVisible({ timeout: 8_000 })
}

/** Navigate to a sidebar link by name. */
export async function navTo(page: Page, name: string): Promise<void> {
  await page.getByRole('link', { name }).click()
  await page.waitForLoadState('networkidle')
}

/** Wait for the app to finish all in-flight requests. */
export async function waitForIdle(page: Page): Promise<void> {
  await page.waitForLoadState('networkidle')
}
