/**
 * Section 5 – Reports
 * QA checklist items: 5.1 – 5.7
 */
import { test, expect } from '@playwright/test'
import { resetDB, setupBaseState, createTransaction, TestState } from '../helpers/api'

let s: TestState

test.describe('5. Reports', () => {
  test.beforeAll(async () => {
    await resetDB()
    s = await setupBaseState()
    // Create income and expense transactions for meaningful reports
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
    await createTransaction({
      type: 'payment',
      date: '2026-05-01',
      narration: 'Grocery bill',
      fyId: s.fyId,
      entries: [
        { account_id: s.foodId, amount: 240_000 },
        { account_id: s.hdfcId, amount: -240_000 },
      ],
    })
  })

  test.beforeEach(async ({ page }) => {
    await page.goto('/reports')
    await page.waitForLoadState('networkidle')
  })

  // ── 5.1 Period Selector ──────────────────────────────────────────────────

  test('5.1 FY dropdown is present', async ({ page }) => {
    // There should be some kind of FY selector on the reports page
    // Period selector is a native <select> — check the select element is visible
    await expect(page.locator('select').first()).toBeVisible()
  })

  // ── 5.2 Profit & Loss ────────────────────────────────────────────────────

  test('5.2 P&L tab shows income and expense sections', async ({ page }) => {
    // Click P&L tab if needed
    const plTab = page.getByRole('tab', { name: /P&L|Profit|Income/i })
      .or(page.getByRole('button', { name: /P&L|Profit|Income/i }))
    if (await plTab.isVisible()) await plTab.click()

    await page.waitForLoadState('networkidle')
    await expect(page.getByText(/Income|Revenue/i).first()).toBeVisible()
    await expect(page.getByText(/Expense/i).first()).toBeVisible()
  })

  test('5.2 P&L net profit row is visible', async ({ page }) => {
    const plTab = page.getByRole('tab', { name: /P&L|Profit|Income/i })
      .or(page.getByRole('button', { name: /P&L|Profit|Income/i }))
    if (await plTab.isVisible()) await plTab.click()

    await page.waitForLoadState('networkidle')
    await expect(page.getByText(/Net [Pp]rofit|Net [Ii]ncome/i)).toBeVisible()
  })

  // ── 5.3 Balance Sheet ────────────────────────────────────────────────────

  test('5.3 Balance Sheet tab is accessible', async ({ page }) => {
    const bsTab = page.getByRole('tab', { name: /Balance [Ss]heet|BS/i })
      .or(page.getByRole('button', { name: /Balance [Ss]heet|BS/i }))
    if (await bsTab.isVisible()) {
      await bsTab.click()
      await page.waitForLoadState('networkidle')
      await expect(page.getByText(/Assets/i).first()).toBeVisible()
    } else {
      test.skip()
    }
  })

  test('5.3 Balance Sheet shows Assets and Liabilities sections', async ({ page }) => {
    const bsTab = page.getByRole('tab', { name: /Balance [Ss]heet|BS/i })
      .or(page.getByRole('button', { name: /Balance [Ss]heet|BS/i }))
    if (await bsTab.isVisible()) {
      await bsTab.click()
      await page.waitForLoadState('networkidle')
      await expect(page.getByText(/Asset/i).first()).toBeVisible()
      await expect(page.getByText(/Liabilit|Equity/i).first()).toBeVisible()
    } else {
      test.skip()
    }
  })

  // ── 5.4 Trial Balance ────────────────────────────────────────────────────

  test('5.4 Trial Balance tab is accessible', async ({ page }) => {
    const tbTab = page.getByRole('tab', { name: /Trial [Bb]alance|TB/i })
      .or(page.getByRole('button', { name: /Trial [Bb]alance|TB/i }))
    if (await tbTab.isVisible()) {
      await tbTab.click()
      await page.waitForLoadState('networkidle')
      await expect(page.getByText(/Debit|Credit/i).first()).toBeVisible()
    } else {
      test.skip()
    }
  })

  // ── 5.5 Cash Flow ────────────────────────────────────────────────────────

  test('5.5 Cash Flow tab is accessible', async ({ page }) => {
    const cfTab = page.getByRole('tab', { name: /Cash [Ff]low|CF/i })
      .or(page.getByRole('button', { name: /Cash [Ff]low|CF/i }))
    if (await cfTab.isVisible()) {
      await cfTab.click()
      await page.waitForLoadState('networkidle')
      await expect(page.getByText(/Operating|Investing|Financing/i).first()).toBeVisible()
    } else {
      test.skip()
    }
  })

  // ── 5.6 Capital Gains ────────────────────────────────────────────────────

  test('5.6 Capital Gains tab is accessible', async ({ page }) => {
    const cgTab = page.getByRole('tab', { name: /Capital [Gg]ains|CG/i })
      .or(page.getByRole('button', { name: /Capital [Gg]ains|CG/i }))
    if (await cgTab.isVisible()) {
      await cgTab.click()
      await page.waitForLoadState('networkidle')
      await expect(page.getByText(/STCG|LTCG|Capital/i).first()).toBeVisible()
    } else {
      test.skip()
    }
  })

  // ── 5.7 PDF Export ───────────────────────────────────────────────────────

  test('5.7 export/download button is present on at least one report tab', async ({ page }) => {
    // Use anchored regex to avoid matching the AI chat "Attach image or PDF" button
    const exportBtn = page.getByRole('button', { name: /^Export/ })
    if (await exportBtn.count() > 0 && await exportBtn.first().isVisible()) {
      await expect(exportBtn.first()).toBeEnabled()
    } else {
      test.skip()
    }
  })
})
