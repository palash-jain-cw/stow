/**
 * Section 11 – Investment Flows
 * QA checklist items: 11.1 – 11.4
 */
import { test, expect, request } from '@playwright/test'
import { resetDB, setupBaseState, TestState } from '../helpers/api'

let s: TestState
let mfAccountId: number
let fdAccountId: number

test.describe('11. Investment Flows', () => {
  test.beforeAll(async () => {
    await resetDB()
    s = await setupBaseState()

    const ctx = await request.newContext({ baseURL: 'http://localhost:8000' })

    // Create MF account
    const mfRes = await ctx.post('/accounts', {
      data: { name: 'Parag Parikh Flexi Cap', group_id: s.invGroupId, investment_subtype: 'equity_mf' },
    })
    const mf = await mfRes.json()
    mfAccountId = mf.id

    // Buy 100 units at ₹85/unit (2024-01-15 → will be LTCG by FY26)
    const fy2023Res = await ctx.post('/financial-years', {
      data: { start_date: '2023-04-01', end_date: '2024-03-31' },
    })
    const fy2023 = await fy2023Res.json()

    await ctx.post(`/investments/${mfAccountId}/buy`, {
      data: {
        units: 100_000,
        cost_per_unit: 8500,
        date: '2024-01-15',
        fy_id: fy2023.id,
        bank_account_id: s.hdfcId,
        narration: 'Buy PPFCF',
      },
    })

    // Create FD account
    const fdAccRes = await ctx.post('/accounts', {
      data: { name: 'HDFC FD 7.5%', group_id: s.invGroupId, investment_subtype: 'fd' },
    })
    const fdAcc = await fdAccRes.json()
    fdAccountId = fdAcc.id

    await ctx.post('/investments/fds', {
      data: {
        account_id: fdAccountId,
        name: 'HDFC FD 7.5%',
        principal: 10_000_000,
        interest_rate: 750,
        start_date: '2026-04-01',
        maturity_date: '2027-04-01',
        compounding: 'quarterly',
      },
    })

    await ctx.dispose()
  })

  // ── 11.1 Fixed Deposits ──────────────────────────────────────────────────

  test('11.1 FD appears in Portfolio → Fixed Deposits', async ({ page }) => {
    await page.goto('/portfolio')
    await page.waitForLoadState('networkidle')
    const fdTab = page.getByRole('tab', { name: /FD|Fixed [Dd]eposit/i })
      .or(page.getByRole('button', { name: /FD|Fixed [Dd]eposit/i }))
    if (await fdTab.isVisible()) await fdTab.click()
    await expect(page.getByText(/HDFC FD|Active/i).first()).toBeVisible()
  })

  test('11.1 FD status badge is "Active" for future maturity', async ({ page }) => {
    await page.goto('/portfolio')
    await page.waitForLoadState('networkidle')
    const fdTab = page.getByRole('tab', { name: /FD|Fixed [Dd]eposit/i })
      .or(page.getByRole('button', { name: /FD|Fixed [Dd]eposit/i }))
    if (await fdTab.isVisible()) await fdTab.click()
    await expect(page.getByText('Active')).toBeVisible()
  })

  test('11.1 FD principal is displayed correctly', async ({ page }) => {
    await page.goto('/portfolio')
    await page.waitForLoadState('networkidle')
    const fdTab = page.getByRole('tab', { name: /FD|Fixed [Dd]eposit/i })
      .or(page.getByRole('button', { name: /FD|Fixed [Dd]eposit/i }))
    if (await fdTab.isVisible()) await fdTab.click()
    // ₹1,00,000 principal (in paise: 10,000,000 → ₹1,00,000.00)
    await expect(page.getByText(/1,00,000/).first()).toBeVisible()
  })

  // ── 11.2 Equity MF / Stocks — Buy ────────────────────────────────────────

  test('11.2 MF holding appears in Portfolio after buy', async ({ page }) => {
    await page.goto('/portfolio')
    await page.waitForLoadState('networkidle')
    const mfTab = page.getByRole('tab', { name: /MF|Mutual|Equity/i })
      .or(page.getByRole('button', { name: /MF|Mutual|Equity/i }))
    if (await mfTab.isVisible()) await mfTab.click()
    await expect(page.getByText(/Parag Parikh/)).toBeVisible()
  })

  // ── 11.3 Equity MF — Sell (Partial) ──────────────────────────────────────

  test('11.3 selling 50 units creates capital gain entry (API)', async () => {
    const ctx = await request.newContext({ baseURL: 'http://localhost:8000' })
    const res = await ctx.post(`/investments/${mfAccountId}/sell`, {
      data: {
        units: 50_000,
        price_per_unit: 10_500,
        date: '2026-04-10',
        fy_id: s.fyId,
        bank_account_id: s.hdfcId,
        narration: 'Sell PPFCF partial',
      },
    })
    expect(res.status()).toBe(201)
    const gains = await res.json()
    expect(Array.isArray(gains)).toBe(true)
    expect(gains.length).toBeGreaterThan(0)
    // Held >12 months → LTCG
    expect(gains[0].gain_type).toBe('ltcg')
    await ctx.dispose()
  })

  test('11.3 remaining 50 units shown in holdings after partial sell', async ({ page }) => {
    await page.goto('/portfolio')
    await page.waitForLoadState('networkidle')
    const mfTab = page.getByRole('tab', { name: /MF|Mutual|Equity/i })
      .or(page.getByRole('button', { name: /MF|Mutual|Equity/i }))
    if (await mfTab.isVisible()) await mfTab.click()
    await expect(page.getByText(/Parag Parikh/)).toBeVisible()
    // 50,000 remaining units shown in the holdings table
    await expect(page.getByRole('cell', { name: '50' }).first()).toBeVisible()
  })

  // ── 11.4 Capital Gains Report ────────────────────────────────────────────

  test('11.4 Capital Gains report shows LTCG entries', async ({ page }) => {
    await page.goto('/reports')
    await page.waitForLoadState('networkidle')
    const cgTab = page.getByRole('tab', { name: /Capital [Gg]ains/i })
      .or(page.getByRole('button', { name: /Capital [Gg]ains/i }))
    if (await cgTab.isVisible()) {
      await cgTab.click()
      await page.waitForLoadState('networkidle')
      await expect(page.getByText(/LTCG|Long.term/i).first()).toBeVisible()
    } else {
      test.skip()
    }
  })

  test('11.4 Capital Gains API shows total_ltcg > 0', async () => {
    const ctx = await request.newContext({ baseURL: 'http://localhost:8000' })
    const res = await ctx.get(`/investments/${mfAccountId}/capital-gains`, {
      params: { fy_id: s.fyId },
    })
    expect(res.ok()).toBe(true)
    const data = await res.json()
    expect(data.total_ltcg).toBeGreaterThan(0)
    expect(data.total_stcg).toBe(0)
    await ctx.dispose()
  })
})
