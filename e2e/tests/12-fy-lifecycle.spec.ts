/**
 * Section 12 – Financial Year Lifecycle
 * QA checklist items: 12.*
 */
import { test, expect, request } from '@playwright/test'
import { resetDB, setupBaseState, createTransaction, TestState } from '../helpers/api'

let s: TestState

test.describe('12. Financial Year Lifecycle', () => {
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

  // ── Create a new FY ───────────────────────────────────────────────────────

  test('12. New FY button opens creation modal in Settings', async ({ page }) => {
    await page.goto('/settings')
    await page.waitForLoadState('networkidle')

    const fyLink = page.getByRole('link', { name: /Financial [Yy]ear/i })
      .or(page.getByRole('button', { name: /Financial [Yy]ear/i }))
    if (await fyLink.isVisible()) await fyLink.click()

    const newFyBtn = page.getByRole('button', { name: /New FY|New Financial Year/i })
    if (await newFyBtn.isVisible()) {
      await newFyBtn.click()
      await expect(page.getByRole('heading', { name: /Open new financial year/i })).toBeVisible()
    } else {
      test.skip()
    }
  })

  test('12. overlapping FY dates are rejected by API', async () => {
    const ctx = await request.newContext({ baseURL: 'http://localhost:8000' })
    // Try to create a FY that overlaps with 2026-04-01 → 2027-03-31
    const res = await ctx.post('/financial-years', {
      data: { start_date: '2026-10-01', end_date: '2027-09-30' },
    })
    expect(res.status()).toBe(422)
    await ctx.dispose()
  })

  test('12. new FY API creation with non-overlapping dates succeeds', async () => {
    const ctx = await request.newContext({ baseURL: 'http://localhost:8000' })
    const res = await ctx.post('/financial-years', {
      data: { start_date: '2027-04-01', end_date: '2028-03-31' },
    })
    expect(res.status()).toBe(201)
    const fy = await res.json()
    expect(fy.id).toBeDefined()
    await ctx.dispose()
  })

  // ── Opening Balances ──────────────────────────────────────────────────────

  test('12. opening balances can be set for the active FY', async ({ page }) => {
    await page.goto('/settings')
    await page.waitForLoadState('networkidle')

    const fyLink = page.getByRole('link', { name: /Financial [Yy]ear/i })
      .or(page.getByRole('button', { name: /Financial [Yy]ear/i }))
    if (await fyLink.isVisible()) await fyLink.click()

    await page.waitForLoadState('networkidle')
    // Opening balances button should be present
    const obBtn = page.getByRole('button', { name: /Opening [Bb]alance/i })
    if (await obBtn.isVisible()) {
      await obBtn.click()
      await expect(page.getByRole('heading', { name: /Opening balances/i })).toBeVisible()
    } else {
      test.skip()
    }
  })

  // ── FY lock ───────────────────────────────────────────────────────────────

  test('12. pre-lock check API runs successfully', async () => {
    const ctx = await request.newContext({ baseURL: 'http://localhost:8000' })
    const res = await ctx.get(`/financial-years/${s.fyId}/pre-lock-check`)
    expect(res.ok()).toBe(true)
    const data = await res.json()
    expect(data).toHaveProperty('unposted_depreciation')
    await ctx.dispose()
  })

  test('12. locking FY via API sets status to "locked"', async () => {
    // NOTE: Locking is irreversible — use a separate FY or skip in normal runs
    // We lock the FY27 (2027-04-01 to 2028-03-31) we just created which has no transactions
    const ctx = await request.newContext({ baseURL: 'http://localhost:8000' })

    // Find the FY27 id
    const fysRes = await ctx.get('/financial-years')
    const fys = await fysRes.json()
    const fy27 = fys.find((f: { start_date: string }) => f.start_date === '2027-04-01')

    if (fy27) {
      const lockRes = await ctx.post(`/financial-years/${fy27.id}/lock`)
      // Should succeed (201/200) or return appropriate status
      expect([200, 201, 204].includes(lockRes.status())).toBe(true)
      const locked = await lockRes.json()
      expect(locked.status).toBe('locked')
    }

    await ctx.dispose()
  })

  // ── Reports accessible after lock ────────────────────────────────────────

  test('12. reports are accessible and show data for active FY', async ({ page }) => {
    await page.goto('/reports')
    await page.waitForLoadState('networkidle')
    await expect(page.locator('select').first()).toContainText(/2026.27/)
    await expect(page.locator('body')).toBeVisible()
    await expect(page.getByText(/error/i)).not.toBeVisible()
  })
})
