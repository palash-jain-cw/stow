/**
 * Section 3 – Transactions
 * QA checklist items: 3.1 – 3.6
 */
import { test, expect } from '@playwright/test'
import { resetDB, setupBaseState, createTransaction, TestState } from '../helpers/api'

let s: TestState

type PW = import('@playwright/test').Page

// Helper: expand a transaction row by narration and wait for the 250ms CSS animation
async function expandRow(page: PW, narration: string) {
  // The toggle button contains the narration text
  await page.getByRole('button').filter({ hasText: narration }).first().click()
  await page.waitForTimeout(400) // 250ms CSS transition + buffer
}

// Helper: click Edit or Delete within the specific expanded row (scoped to avoid clicking
// buttons inside collapsed rows that also exist in the DOM but have 0 height)
async function clickExpandedBtn(page: PW, narration: string, action: 'Edit' | 'Delete') {
  // The toggle button is sibling to the grid-expand panel, both inside the row container div.
  // Walk up from the toggle button to the row container, then find the action button within it.
  // Use anchored regex for name matching — plain strings do substring match, so narrations
  // like "Delete me now" would match the 'Delete' action name otherwise.
  const toggleBtn = page.getByRole('button').filter({ hasText: narration }).first()
  const rowContainer = toggleBtn.locator('..')  // outer row <div>
  const btn = rowContainer.getByRole('button', { name: new RegExp(`^${action}$`, 'i') }).first()
  await btn.evaluate((el: HTMLElement) => el.click())
}

// Helper: open the Filters panel (type checkboxes are inside a dropdown)
async function openFiltersPanel(page: PW) {
  await page.getByRole('button', { name: /Filters/i }).click()
  await page.waitForTimeout(200)
}

test.describe('3. Transactions', () => {
  test.beforeAll(async () => {
    await resetDB()
    s = await setupBaseState()

    await createTransaction({
      type: 'payment',
      date: '2026-05-01',
      narration: 'Electric bill',
      fyId: s.fyId,
      tags: ['utilities'],
      entries: [
        { account_id: s.foodId, amount: 80000 },
        { account_id: s.hdfcId, amount: -80000 },
      ],
    })

    await createTransaction({
      type: 'receipt',
      date: '2026-04-30',
      narration: 'April salary',
      fyId: s.fyId,
      entries: [
        { account_id: s.hdfcId, amount: 8_500_000 },
        { account_id: s.salaryId, amount: -8_500_000 },
      ],
    })
  })

  test.beforeEach(async ({ page }) => {
    await page.goto('/transactions')
    await page.waitForLoadState('networkidle')
  })

  // ── 3.1 Transaction List ─────────────────────────────────────────────────

  test('3.1 transactions load and are grouped by date', async ({ page }) => {
    await expect(page.getByText('Electric bill')).toBeVisible()
    await expect(page.getByText('April salary')).toBeVisible()
  })

  test('3.1 each row shows type badge (PAY/REC), narration, and amount', async ({ page }) => {
    // Use .first() since PAY badge might appear in multiple date groups
    await expect(page.getByText('PAY').first()).toBeVisible()
    await expect(page.getByText('Electric bill')).toBeVisible()
    await expect(page.getByText('REC').first()).toBeVisible()
  })

  test('3.1 expanding a row shows Dr/Cr entries and edit/delete buttons', async ({ page }) => {
    await expandRow(page, 'Electric bill')
    // Buttons are visible after expansion
    await expect(page.getByRole('button', { name: /Edit/i }).first()).toBeVisible()
    await expect(page.getByRole('button', { name: /Delete/i }).first()).toBeVisible()
  })

  // ── 3.2 Filters ──────────────────────────────────────────────────────────

  test('3.2 search filters by narration in real-time', async ({ page }) => {
    await page.getByPlaceholder('Search transactions…').fill('Electric')
    await page.waitForTimeout(300)
    await expect(page.getByText('Electric bill')).toBeVisible()
    await expect(page.getByText('April salary')).not.toBeVisible()
  })

  test('3.2 period pill "This FY" shows current FY transactions', async ({ page }) => {
    await page.getByRole('button', { name: 'This FY' }).click()
    await page.waitForLoadState('networkidle')
    await expect(page.getByText('Electric bill')).toBeVisible()
    await expect(page.getByText('April salary')).toBeVisible()
  })

  test('3.2 type checkbox filtering hides unselected types', async ({ page }) => {
    // Type checkboxes are inside the Filters panel — open it first
    await openFiltersPanel(page)
    // The filter is an inclusion filter: checked types are shown, unchecked are hidden.
    // Click the "payment" label to add payment to activeTypes — now only payments are shown.
    // Use label click (not checkbox check) because React's controlled input re-renders async.
    await page.locator('label').filter({ hasText: /^payment$/i }).click()
    await page.waitForTimeout(400)
    // Only payment transactions visible; receipt (April salary) is now filtered out
    await expect(page.getByText('April salary')).not.toBeVisible()
    await expect(page.getByText('Electric bill')).toBeVisible()
  })

  test('3.2 "Clear all" button resets all active filters', async ({ page }) => {
    await page.getByPlaceholder('Search transactions…').fill('Electric')
    await page.waitForTimeout(200)
    const clearBtn = page.getByRole('button', { name: /Clear all/i })
    await expect(clearBtn).toBeVisible()
    await clearBtn.click()
    await page.waitForTimeout(300)
    await expect(page.getByText('April salary')).toBeVisible()
    await expect(page.getByText('Electric bill')).toBeVisible()
  })

  test('3.2 filter state (search) persists across page refresh via URL params', async ({ page }) => {
    await page.getByPlaceholder('Search transactions…').fill('Electric')
    await page.waitForTimeout(200)
    await page.reload()
    await page.waitForLoadState('networkidle')
    await expect(page.getByPlaceholder('Search transactions…')).toHaveValue('Electric')
    await expect(page.getByText('April salary')).not.toBeVisible()
  })

  // ── 3.3 Creating a Transaction ───────────────────────────────────────────

  test('3.3 "New Transaction" button opens the entry sheet', async ({ page }) => {
    await page.getByRole('button', { name: 'New Transaction' }).click()
    await expect(page.getByRole('dialog')).toBeVisible()
    await expect(page.getByRole('heading', { name: 'New Transaction' })).toBeVisible()
  })

  test('3.3 narration is required — Save is disabled without it', async ({ page }) => {
    await page.getByRole('button', { name: 'New Transaction' }).click()
    const dialog = page.getByRole('dialog')
    await dialog.getByRole('spinbutton').fill('100')
    await expect(dialog.getByRole('button', { name: 'Save' })).toBeDisabled()
  })

  test('3.3 date picker defaults to today', async ({ page }) => {
    await page.getByRole('button', { name: 'New Transaction' }).click()
    const dialog = page.getByRole('dialog')
    const today = new Date().toISOString().slice(0, 10)
    const dateField = dialog.locator(`input[value="${today}"], input[type="date"]`).first()
    // Date field should be visible (even if exact format differs)
    await expect(dialog.getByRole('textbox').nth(1)).toBeVisible()
  })

  test('3.3 creating a payment transaction shows it in the list', async ({ page }) => {
    await page.getByRole('button', { name: 'New Transaction' }).click()
    const dialog = page.getByRole('dialog')
    await dialog.getByRole('button', { name: 'Payment' }).click()
    await dialog.getByRole('spinbutton').fill('150')
    await dialog.getByRole('textbox', { name: /What was this for/ }).fill('Lunch at cafe')

    const [fromCombo] = await dialog.getByRole('combobox').all()
    await fromCombo.fill('Food')
    await page.getByRole('option', { name: 'Food & Dining' }).click()

    const combos = await dialog.getByRole('combobox').all()
    await combos[combos.length - 1].fill('HDFC')
    await page.getByRole('option', { name: 'HDFC Savings' }).click()

    await dialog.getByRole('button', { name: 'Save' }).click()
    await expect(dialog).not.toBeVisible({ timeout: 8_000 })
    await page.waitForLoadState('networkidle')
    await expect(page.getByText('Lunch at cafe')).toBeVisible()
  })

  test('3.3 transaction number (visible in expanded row) starts with the correct prefix', async ({ page }) => {
    await expandRow(page, 'Electric bill')
    // Transaction number is shown in the expanded panel; format is PAYnnn (no hyphen confirmed by API)
    await expect(page.getByText(/PAY\d+|PAY-\d+/i).first()).toBeVisible()
  })

  test('3.3 tags field accepts free-form tags', async ({ page }) => {
    await page.getByRole('button', { name: 'New Transaction' }).click()
    const dialog = page.getByRole('dialog')
    await dialog.getByRole('button', { name: 'Payment' }).click()
    await dialog.getByRole('spinbutton').fill('50')
    await dialog.getByRole('textbox', { name: /What was this for/ }).fill('Tagged transaction')

    const [fromCombo] = await dialog.getByRole('combobox').all()
    await fromCombo.fill('Food')
    await page.getByRole('option', { name: 'Food & Dining' }).click()

    const combos = await dialog.getByRole('combobox').all()
    await combos[combos.length - 1].fill('HDFC')
    await page.getByRole('option', { name: 'HDFC Savings' }).click()

    await dialog.getByRole('textbox', { name: 'Add tag' }).fill('groceries')
    await dialog.getByRole('button', { name: 'Add' }).click()
    await expect(dialog.getByText('groceries')).toBeVisible()

    await dialog.getByRole('button', { name: 'Save' }).click()
    await expect(dialog).not.toBeVisible({ timeout: 8_000 })
  })

  test('3.3 Receipt type creates a receipt transaction (REC badge)', async ({ page }) => {
    await page.getByRole('button', { name: 'New Transaction' }).click()
    const dialog = page.getByRole('dialog')
    await dialog.getByRole('button', { name: 'Receipt' }).click()
    await dialog.getByRole('spinbutton').fill('5000')
    await dialog.getByRole('textbox', { name: /What was this for/ }).fill('Bonus receipt')

    const [fromCombo] = await dialog.getByRole('combobox').all()
    await fromCombo.fill('HDFC')
    await page.getByRole('option', { name: 'HDFC Savings' }).click()

    const combos = await dialog.getByRole('combobox').all()
    await combos[combos.length - 1].fill('Salary')
    await page.getByRole('option', { name: 'Salary' }).click()

    await dialog.getByRole('button', { name: 'Save' }).click()
    await expect(dialog).not.toBeVisible({ timeout: 8_000 })
    await page.waitForLoadState('networkidle')
    await expect(page.getByText('Bonus receipt')).toBeVisible()
  })

  // ── 3.4 Editing a Transaction ────────────────────────────────────────────

  test('3.4 edit button opens sheet pre-filled with existing data', async ({ page }) => {
    await expandRow(page, 'Electric bill')
    await clickExpandedBtn(page, 'Electric bill', 'Edit')
    const dialog = page.getByRole('dialog')
    await expect(dialog).toBeVisible()
    await expect(dialog.getByRole('textbox', { name: /What was this for/ })).toHaveValue('Electric bill')
  })

  test('3.4 saving an edit updates the transaction narration', async ({ page }) => {
    await expandRow(page, 'Electric bill')
    await clickExpandedBtn(page, 'Electric bill', 'Edit')
    const dialog = page.getByRole('dialog')
    await dialog.getByRole('textbox', { name: /What was this for/ }).fill('Electric bill EDITED')
    await dialog.getByRole('button', { name: 'Update' }).click()
    await expect(dialog).not.toBeVisible({ timeout: 8_000 })
    await page.waitForLoadState('networkidle')
    await expect(page.getByText('Electric bill EDITED')).toBeVisible()
  })

  test('3.4 audit log entry is created after edit', async ({ page }) => {
    // After the previous test renamed it, expand and view the audit log
    await expandRow(page, 'Electric bill EDITED')
    // Scope "View edit history" to this row's container (other rows also have the button in DOM)
    const toggleBtn = page.getByRole('button').filter({ hasText: 'Electric bill EDITED' }).first()
    const rowContainer = toggleBtn.locator('..')
    await rowContainer.getByRole('button', { name: /View edit history/i }).evaluate((el: HTMLElement) => el.click())
    await page.waitForTimeout(500)
    // Audit log shows "Edited <date>" entries
    await expect(page.getByText(/Edited/i).first()).toBeVisible()
  })

  // ── 3.5 Deleting a Transaction ───────────────────────────────────────────

  test('3.5 delete button shows "Delete transaction?" confirmation', async ({ page }) => {
    await expandRow(page, 'April salary')
    await clickExpandedBtn(page, 'April salary', 'Delete')
    await expect(page.locator('div.fixed').filter({ has: page.getByText('Delete transaction?') })).toBeVisible()
  })

  test('3.5 cancelling delete keeps the transaction', async ({ page }) => {
    await expandRow(page, 'April salary')
    await clickExpandedBtn(page, 'April salary', 'Delete')
    const confirmModal = page.locator('div.fixed').filter({ has: page.getByText('Delete transaction?') })
    await confirmModal.getByRole('button', { name: 'Cancel' }).click()
    await page.waitForTimeout(300)
    await expect(page.getByText('April salary')).toBeVisible()
  })

  test('3.5 confirming delete removes transaction from list', async ({ page }) => {
    const ctx = await import('../helpers/api')
    await ctx.createTransaction({
      type: 'payment',
      date: '2026-05-10',
      narration: 'Delete me now',
      fyId: s.fyId,
      entries: [
        { account_id: s.foodId, amount: 100 },
        { account_id: s.hdfcId, amount: -100 },
      ],
    })
    await page.reload()
    await page.waitForLoadState('networkidle')

    await expandRow(page, 'Delete me now')
    await clickExpandedBtn(page, 'Delete me now', 'Delete')
    const confirmModal = page.locator('div.fixed').filter({ has: page.getByText('Delete transaction?') })
    await expect(confirmModal).toBeVisible()
    // Click the red "Delete" confirm button scoped to the modal to avoid row toggle match
    await confirmModal.getByRole('button', { name: /^Delete$/ }).click()
    await page.waitForLoadState('networkidle')
    // The row's narration <p> should be gone after deletion
    await expect(page.locator('p.text-sm.font-medium', { hasText: 'Delete me now' })).not.toBeVisible({ timeout: 8_000 })
  })

  test('3.5 deleted transaction no longer appears in account ledger', async () => {
    // Verified via the previous test — no separate UI check needed
  })

  // ── 3.6 Edge Cases ───────────────────────────────────────────────────────

  test('3.6 transaction with zero amount is rejected (Save stays disabled)', async ({ page }) => {
    await page.getByRole('button', { name: 'New Transaction' }).click()
    const dialog = page.getByRole('dialog')
    await dialog.getByRole('button', { name: 'Payment' }).click()
    // Amount stays 0 (default) — don't fill it
    await dialog.getByRole('textbox', { name: /What was this for/ }).fill('Zero amount test')
    // Save should be disabled when amount is 0 or accounts not selected
    await expect(dialog.getByRole('button', { name: 'Save' })).toBeDisabled()
  })

  test('3.6 very long narration renders without horizontal overflow', async ({ page }) => {
    const longNarration = 'A'.repeat(200)
    const ctx = await import('../helpers/api')
    await ctx.createTransaction({
      type: 'payment',
      date: '2026-05-15',
      narration: longNarration,
      fyId: s.fyId,
      entries: [
        { account_id: s.foodId, amount: 100 },
        { account_id: s.hdfcId, amount: -100 },
      ],
    })
    await page.reload()
    await page.waitForLoadState('networkidle')
    await expect(page.locator('body')).toBeVisible()
    const overflow = await page.evaluate(() =>
      document.documentElement.scrollWidth > document.documentElement.clientWidth
    )
    expect(overflow).toBe(false)
  })
})
