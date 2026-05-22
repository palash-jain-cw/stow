/**
 * Section 13 – Cross-Cutting Concerns
 * QA checklist items: 13.1 – 13.5
 */
import { test, expect, request } from '@playwright/test'
import { resetDB, setupBaseState, createTransaction, TestState } from '../helpers/api'

let s: TestState

test.describe('13. Cross-Cutting Concerns', () => {
  test.beforeAll(async () => {
    await resetDB()
    s = await setupBaseState()

    await createTransaction({
      type: 'receipt',
      date: '2026-04-30',
      narration: 'Salary',
      fyId: s.fyId,
      entries: [
        { account_id: s.hdfcId, amount: 5_000_000 },
        { account_id: s.salaryId, amount: -5_000_000 },
      ],
    })
  })

  // ── 13.1 Data Integrity ───────────────────────────────────────────────────

  test('13.1 trial balance always balances (Dr = Cr)', async () => {
    const ctx = await request.newContext({ baseURL: 'http://localhost:8000' })
    const res = await ctx.get('/reports/trial-balance', { params: { fy_id: s.fyId } })
    expect(res.ok()).toBe(true)
    const tb = await res.json()
    expect(tb.total_debit).toBe(tb.total_credit)
    await ctx.dispose()
  })

  test('13.1 unbalanced entries are rejected by the API (422)', async () => {
    const ctx = await request.newContext({ baseURL: 'http://localhost:8000' })
    const res = await ctx.post('/transactions', {
      data: {
        type: 'payment',
        date: '2026-05-01',
        narration: 'Unbalanced',
        fy_id: s.fyId,
        entries: [
          { account_id: s.foodId, amount: 100_000 },
          { account_id: s.hdfcId, amount: -99_999 },  // off by ₹0.01
        ],
      },
    })
    expect(res.status()).toBe(422)
    await ctx.dispose()
  })

  // ── 13.2 Error & Edge-Case Handling ──────────────────────────────────────

  test('13.2 API returns 422 for missing required fields', async () => {
    const ctx = await request.newContext({ baseURL: 'http://localhost:8000' })
    // Missing narration and entries
    const res = await ctx.post('/transactions', {
      data: { type: 'payment', date: '2026-05-01', fy_id: s.fyId },
    })
    expect(res.status()).toBe(422)
    await ctx.dispose()
  })

  test('13.2 API returns 404 for unknown resource', async () => {
    const ctx = await request.newContext({ baseURL: 'http://localhost:8000' })
    const res = await ctx.get('/transactions/999999')
    expect(res.status()).toBe(404)
    await ctx.dispose()
  })

  test('13.2 non-PDF upload in import flow returns friendly error', async () => {
    // Upload a text file to the import endpoint
    const ctx = await request.newContext({ baseURL: 'http://localhost:8000' })
    const res = await ctx.post('/import/batch', {
      multipart: {
        file: { name: 'test.txt', mimeType: 'text/plain', buffer: Buffer.from('not a PDF') },
      },
    })
    // Should not be 500 — 400 or 422 is expected
    expect(res.status()).not.toBe(500)
    await ctx.dispose()
  })

  test('13.2 empty transactions page renders without errors', async ({ page }) => {
    // After a fresh reset/state, navigating to transactions should show empty state
    await page.goto('/transactions')
    await page.waitForLoadState('networkidle')
    await expect(page.locator('body')).toBeVisible()
    // No JS error text
    const errorText = page.getByText(/cannot read|undefined is not|TypeError/i)
    await expect(errorText).not.toBeVisible()
  })

  test('13.2 empty portfolio page renders without errors', async ({ page }) => {
    await page.goto('/portfolio')
    await page.waitForLoadState('networkidle')
    await expect(page.locator('body')).toBeVisible()
    await expect(page.getByText(/TypeError|undefined/i)).not.toBeVisible()
  })

  // ── 13.3 Performance ─────────────────────────────────────────────────────

  test('13.3 transactions page loads within 3 seconds', async ({ page }) => {
    const start = Date.now()
    await page.goto('/transactions')
    await page.waitForLoadState('networkidle')
    const elapsed = Date.now() - start
    expect(elapsed).toBeLessThan(3_000)
  })

  test('13.3 reports page loads within 5 seconds', async ({ page }) => {
    const start = Date.now()
    await page.goto('/reports')
    await page.waitForLoadState('networkidle')
    const elapsed = Date.now() - start
    expect(elapsed).toBeLessThan(5_000)
  })

  // ── 13.4 UI Consistency ───────────────────────────────────────────────────

  test('13.4 monetary amounts use ₹ symbol on dashboard', async ({ page }) => {
    await page.goto('/')
    await page.waitForLoadState('networkidle')
    await expect(page.getByText(/₹/).first()).toBeVisible()
  })

  test('13.4 dates display in readable format (not raw ISO)', async ({ page }) => {
    await page.goto('/transactions')
    await page.waitForLoadState('networkidle')
    // Should not show raw ISO like "2026-04-30" — should show "30 April 2026" or similar
    // Check that the date column contains month names or formatted dates
    const isoPattern = page.getByText(/^\d{4}-\d{2}-\d{2}$/)
    await expect(isoPattern).not.toBeVisible()
  })

  test('13.4 Escape key closes open dialog', async ({ page }) => {
    await page.goto('/transactions')
    await page.waitForLoadState('networkidle')
    await page.getByRole('button', { name: 'New Transaction' }).click()
    await expect(page.getByRole('dialog')).toBeVisible()
    await page.keyboard.press('Escape')
    await expect(page.getByRole('dialog')).not.toBeVisible({ timeout: 3_000 })
  })

  test('13.4 no horizontal overflow on transactions page', async ({ page }) => {
    await page.goto('/transactions')
    await page.waitForLoadState('networkidle')
    const hasOverflow = await page.evaluate(() =>
      document.documentElement.scrollWidth > document.documentElement.clientWidth
    )
    expect(hasOverflow).toBe(false)
  })

  test('13.4 no horizontal overflow on accounts page', async ({ page }) => {
    await page.goto('/accounts')
    await page.waitForLoadState('networkidle')
    const hasOverflow = await page.evaluate(() =>
      document.documentElement.scrollWidth > document.documentElement.clientWidth
    )
    expect(hasOverflow).toBe(false)
  })

  // ── 13.5 Settings Persistence ─────────────────────────────────────────────

  test('13.5 merchant rules persist across page reload', async ({ page }) => {
    // Create a rule via API
    const { createMerchantRule } = await import('../helpers/api')
    await createMerchantRule('PERSIST_TEST*', s.foodId)

    await page.goto('/settings')
    await page.waitForLoadState('networkidle')

    const rulesLink = page.getByRole('link', { name: /Merchant|Rules/i })
      .or(page.getByRole('button', { name: /Merchant|Rules/i }))
    if (await rulesLink.isVisible()) await rulesLink.click()

    await page.waitForLoadState('networkidle')
    await page.reload()
    await page.waitForLoadState('networkidle')

    await expect(page.getByText('PERSIST_TEST*')).toBeVisible()
  })

  // ── Health check ─────────────────────────────────────────────────────────

  test('backend /health returns ok', async () => {
    const ctx = await request.newContext({ baseURL: 'http://localhost:8000' })
    const res = await ctx.get('/health')
    expect(res.ok()).toBe(true)
    const data = await res.json()
    expect(data.status).toBe('ok')
    await ctx.dispose()
  })
})
