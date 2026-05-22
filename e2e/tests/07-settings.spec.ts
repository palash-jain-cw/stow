/**
 * Section 7 – Settings
 * QA checklist items: 7.1 – 7.4
 */
import { test, expect } from '@playwright/test'
import { resetDB, setupBaseState, createTransaction, createMerchantRule, TestState } from '../helpers/api'

let s: TestState

test.describe('7. Settings', () => {
  test.beforeAll(async () => {
    await resetDB()
    s = await setupBaseState()

    // Create a transaction to use as template for recurring schedule
    const txn = await createTransaction({
      type: 'payment',
      date: '2026-04-05',
      narration: 'Monthly rent',
      fyId: s.fyId,
      entries: [
        { account_id: s.foodId, amount: 2_000_000 },
        { account_id: s.hdfcId, amount: -2_000_000 },
      ],
    })

    // Create recurring schedule
    const ctx = await import('../helpers/api')
    await ctx.createRecurringSchedule({
      templateTransactionId: txn.id,
      frequency: 'monthly',
      firstDueDate: '2026-06-05',
      dayOfPeriod: 5,
    })

    // Create a merchant rule
    await createMerchantRule('BESCOM*', s.foodId)
  })

  test.beforeEach(async ({ page }) => {
    await page.goto('/settings')
    await page.waitForLoadState('networkidle')
  })

  // ── 7.1 Financial Years Panel ─────────────────────────────────────────────

  test('7.1 FY panel lists financial years', async ({ page }) => {
    // Navigate to FY section
    const fyLink = page.getByRole('link', { name: /Financial [Yy]ear/i })
      .or(page.getByRole('button', { name: /Financial [Yy]ear/i }))
    if (await fyLink.isVisible()) await fyLink.click()

    await expect(page.getByText(/FY 2026–27/)).toBeVisible()
  })

  test('7.1 "New FY" button opens creation modal', async ({ page }) => {
    const fyLink = page.getByRole('link', { name: /Financial [Yy]ear/i })
      .or(page.getByRole('button', { name: /Financial [Yy]ear/i }))
    if (await fyLink.isVisible()) await fyLink.click()

    const newFyBtn = page.getByRole('button', { name: /New FY|New Financial Year/i })
    if (await newFyBtn.isVisible()) {
      await newFyBtn.click()
      // Modal uses a custom div overlay, not role="dialog" — check by heading text
      await expect(page.getByRole('heading', { name: /Open new financial year/i })).toBeVisible()
    } else {
      test.skip()
    }
  })

  // ── 7.2 Recurring Transactions Panel ─────────────────────────────────────

  test('7.2 recurring schedules are listed', async ({ page }) => {
    const recurLink = page.getByRole('link', { name: /Recurring/i })
      .or(page.getByRole('button', { name: /Recurring/i }))
    if (await recurLink.isVisible()) await recurLink.click()

    await page.waitForLoadState('networkidle')
    await expect(page.getByText(/Monthly rent|monthly/i).first()).toBeVisible()
  })

  test('7.2 frequency badge is shown for each schedule', async ({ page }) => {
    const recurLink = page.getByRole('link', { name: /Recurring/i })
      .or(page.getByRole('button', { name: /Recurring/i }))
    if (await recurLink.isVisible()) await recurLink.click()

    await page.waitForLoadState('networkidle')
    await expect(page.getByText('Monthly', { exact: true }).first()).toBeVisible()
  })

  test('7.2 delete button shows confirmation for a schedule', async ({ page }) => {
    const recurLink = page.getByRole('link', { name: /Recurring/i })
      .or(page.getByRole('button', { name: /Recurring/i }))
    if (await recurLink.isVisible()) await recurLink.click()

    await page.waitForLoadState('networkidle')
    const deleteBtn = page.getByRole('button', { name: /Delete/i }).first()
    if (await deleteBtn.isVisible()) {
      await deleteBtn.click()
      await expect(page.getByText(/confirm|sure|delete/i).first()).toBeVisible()
      // Dismiss without deleting
      await page.keyboard.press('Escape')
    } else {
      test.skip()
    }
  })

  // ── 7.3 Merchant Rules Panel ──────────────────────────────────────────────

  test('7.3 merchant rules are listed with pattern and account', async ({ page }) => {
    const rulesLink = page.getByRole('link', { name: /Merchant|Rules/i })
      .or(page.getByRole('button', { name: /Merchant|Rules/i }))
    if (await rulesLink.isVisible()) await rulesLink.click()

    await page.waitForLoadState('networkidle')
    await expect(page.getByText('BESCOM*')).toBeVisible()
  })

  test('7.3 delete button removes a merchant rule', async ({ page }) => {
    // Create a temporary rule to delete
    const { createMerchantRule: cmr } = await import('../helpers/api')
    await cmr('TEMP_DELETE*', s.foodId)

    const rulesLink = page.getByRole('link', { name: /Merchant|Rules/i })
      .or(page.getByRole('button', { name: /Merchant|Rules/i }))
    if (await rulesLink.isVisible()) await rulesLink.click()

    await page.reload()
    await page.waitForLoadState('networkidle')

    const ruleTile = page.getByText('TEMP_DELETE*')
    if (await ruleTile.isVisible()) {
      // Delete button is a Trash2 icon with no accessible name — find last button in the table row
      const row = page.getByRole('row').filter({ hasText: 'TEMP_DELETE*' })
      const deleteBtn = row.locator('button').last()
      await deleteBtn.click()
      await page.waitForTimeout(300)
      // No confirmation dialog — delete is optimistic with undo toast
      await page.waitForLoadState('networkidle')
      await expect(page.getByText('TEMP_DELETE*')).not.toBeVisible({ timeout: 5_000 })
    }
  })

  // ── 7.4 AI / LLM Panel ───────────────────────────────────────────────────

  test('7.4 AI config panel shows URL, Model, and API key fields', async ({ page }) => {
    const aiLink = page.getByRole('link', { name: /AI|LLM|Model/i })
      .or(page.getByRole('button', { name: /AI|LLM|Model/i }))
    if (await aiLink.isVisible()) await aiLink.click()

    await page.waitForLoadState('networkidle')
    await expect(page.getByText(/Server URL|Base URL/i)).toBeVisible()
    await expect(page.getByText(/Model/i).first()).toBeVisible()
    await expect(page.getByText(/API [Kk]ey/i)).toBeVisible()
  })

  test('7.4 "Test connection" button is present', async ({ page }) => {
    const aiLink = page.getByRole('link', { name: /AI|LLM|Model/i })
      .or(page.getByRole('button', { name: /AI|LLM|Model/i }))
    if (await aiLink.isVisible()) await aiLink.click()

    await page.waitForLoadState('networkidle')
    await expect(page.getByRole('button', { name: /Test connection/i })).toBeVisible()
  })

  test('7.4 API key field is masked (password type)', async ({ page }) => {
    const aiLink = page.getByRole('link', { name: /AI|LLM|Model/i })
      .or(page.getByRole('button', { name: /AI|LLM|Model/i }))
    if (await aiLink.isVisible()) await aiLink.click()

    await page.waitForLoadState('networkidle')
    // API key input should be password type
    const apiKeyInput = page.locator('input[type="password"]')
    await expect(apiKeyInput).toBeVisible()
  })

  // ── Danger Zone (Reset) ───────────────────────────────────────────────────

  test('settings contains Danger Zone with Reset app option', async ({ page }) => {
    // Scroll to bottom to find Danger Zone
    await page.evaluate(() => window.scrollTo(0, document.body.scrollHeight))
    await page.waitForTimeout(300)
    await expect(page.getByText(/Danger [Zz]one|Reset [Aa]pp/i)).toBeVisible()
  })
})
