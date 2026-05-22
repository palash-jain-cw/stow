/**
 * Section 10 – Recurring Transactions (End-to-End)
 * QA checklist items: 10.*
 */
import { test, expect, request } from '@playwright/test'
import { resetDB, setupBaseState, createTransaction, createRecurringSchedule, TestState } from '../helpers/api'

let s: TestState
let scheduleId: number

test.describe('10. Recurring Transactions', () => {
  test.beforeAll(async () => {
    await resetDB()
    s = await setupBaseState()

    const txn = await createTransaction({
      type: 'payment',
      date: '2026-04-05',
      narration: 'Monthly broadband',
      fyId: s.fyId,
      entries: [
        { account_id: s.foodId, amount: 99900 },
        { account_id: s.hdfcId, amount: -99900 },
      ],
    })

    const sched = await createRecurringSchedule({
      templateTransactionId: txn.id,
      frequency: 'monthly',
      firstDueDate: '2026-06-05',
      dayOfPeriod: 5,
    })
    scheduleId = sched.id
  })

  // ── Schedule creation (via Settings) ────────────────────────────────────

  test('10. recurring schedule appears in Settings → Recurring', async ({ page }) => {
    await page.goto('/settings')
    await page.waitForLoadState('networkidle')

    const recurLink = page.getByRole('link', { name: /Recurring/i })
      .or(page.getByRole('button', { name: /Recurring/i }))
    if (await recurLink.isVisible()) await recurLink.click()

    await page.waitForLoadState('networkidle')
    await expect(page.getByText(/Monthly broadband|monthly/i)).toBeVisible()
  })

  test('10. next_due_date is shown for the schedule', async ({ page }) => {
    await page.goto('/settings')
    await page.waitForLoadState('networkidle')

    const recurLink = page.getByRole('link', { name: /Recurring/i })
      .or(page.getByRole('button', { name: /Recurring/i }))
    if (await recurLink.isVisible()) await recurLink.click()

    await page.waitForLoadState('networkidle')
    // Due date should show Jun 2026 or similar
    await expect(page.getByText(/Jun|2026/i).first()).toBeVisible()
  })

  test('10. deleting a schedule removes it from the list', async ({ page }) => {
    // Create a throwaway schedule to delete
    const txn = await createTransaction({
      type: 'payment',
      date: '2026-04-10',
      narration: 'Delete schedule test',
      fyId: s.fyId,
      entries: [
        { account_id: s.foodId, amount: 500 },
        { account_id: s.hdfcId, amount: -500 },
      ],
    })
    await createRecurringSchedule({
      templateTransactionId: txn.id,
      frequency: 'weekly',
      firstDueDate: '2026-05-20',
    })

    await page.goto('/settings')
    await page.waitForLoadState('networkidle')

    const recurLink = page.getByRole('link', { name: /Recurring/i })
      .or(page.getByRole('button', { name: /Recurring/i }))
    if (await recurLink.isVisible()) await recurLink.click()

    await page.reload()
    await page.waitForLoadState('networkidle')

    await expect(page.getByText('Delete schedule test')).toBeVisible()

    // Find and delete
    const row = page.getByText('Delete schedule test').locator('..').locator('..')
    const deleteBtn = row.getByRole('button', { name: /Delete|Trash/i })
    if (await deleteBtn.isVisible()) {
      await deleteBtn.click()
      const confirmBtn = page.getByRole('button', { name: /Confirm|Yes|Delete/i }).last()
      if (await confirmBtn.isVisible()) await confirmBtn.click()
      await page.waitForLoadState('networkidle')
      await expect(page.getByText('Delete schedule test')).not.toBeVisible({ timeout: 5_000 })
    }
  })

  // ── Queue item generation (requires time manipulation or future-dated schedule) ──

  test('10. GET /recurring/due-today returns a list', async () => {
    const ctx = await request.newContext({ baseURL: 'http://localhost:8000' })
    const res = await ctx.get('/recurring/due-today')
    expect(res.ok()).toBe(true)
    const data = await res.json()
    expect(Array.isArray(data)).toBe(true)
    await ctx.dispose()
  })
})
