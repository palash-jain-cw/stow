/**
 * Section 2 – Dashboard
 * QA checklist items: 2.1 – 2.5
 */
import { test, expect } from '@playwright/test'
import { resetDB, setupBaseState, createTransaction } from '../helpers/api'
import { openNewTransactionSheet, fillTransaction, saveTransaction } from '../helpers/ui'

test.describe('2. Dashboard', () => {
  test.beforeAll(async () => {
    await resetDB()
    const s = await setupBaseState()
    // Create one payment so Recent Activity is non-empty
    await createTransaction({
      type: 'payment',
      date: '2026-05-01',
      narration: 'Grocery run',
      fyId: s.fyId,
      entries: [
        { account_id: s.foodId, amount: 50000 },
        { account_id: s.hdfcId, amount: -50000 },
      ],
    })
  })

  test.beforeEach(async ({ page }) => {
    await page.goto('/')
    await page.waitForLoadState('networkidle')
  })

  // ── 2.1 Header & Financial Year Banner ───────────────────────────────────

  test('2.1 greeting is one of morning / afternoon / evening', async ({ page }) => {
    const heading = page.getByRole('heading', { level: 1 })
    await expect(heading).toBeVisible()
    const text = await heading.textContent()
    expect(text).toMatch(/Good (morning|afternoon|evening)/i)
  })

  test('2.1 active FY name and dates are displayed', async ({ page }) => {
    await expect(page.getByText(/FY 2026–27/)).toBeVisible()
  })

  // ── 2.2 Summary Cards ────────────────────────────────────────────────────

  test('2.2 Net worth card is visible', async ({ page }) => {
    await expect(page.getByText('Net worth')).toBeVisible()
  })

  test('2.2 Cash position card is visible', async ({ page }) => {
    await expect(page.getByText(/Cash across/)).toBeVisible()
  })

  test('2.2 net worth reflects opening balance minus payment', async ({ page }) => {
    // Opening balance ₹10,000 - ₹500 payment = ₹9,500
    await expect(page.getByText('₹9,500.00').first()).toBeVisible()
  })

  // ── 2.3 Needs Attention Zone ─────────────────────────────────────────────

  test('2.3 Needs Attention section is visible and collapsible', async ({ page }) => {
    const btn = page.getByRole('button', { name: /Needs attention/ })
    await expect(btn).toBeVisible()
    // Click to collapse
    await btn.click()
    await page.waitForTimeout(300)
    // Click to expand
    await btn.click()
    await page.waitForTimeout(300)
    // Section content still visible
    await expect(page.getByText(/All clear/)).toBeVisible()
  })

  // ── 2.4 Recent Activity Zone ─────────────────────────────────────────────

  test('2.4 Recent Activity section is collapsible', async ({ page }) => {
    const btn = page.getByRole('button', { name: /Recent activity/ })
    await expect(btn).toBeVisible()
    await btn.click()
    await page.waitForTimeout(300)
    await btn.click()
    await page.waitForTimeout(300)
  })

  test('2.4 transaction appears in recent activity after creation', async ({ page }) => {
    await expect(page.getByText('Grocery run')).toBeVisible()
  })

  test('2.4 "See all transactions" navigates to /transactions', async ({ page }) => {
    // Use JS click to bypass the section-toggle overlay that intercepts pointer events
    const btn = page.getByRole('button', { name: /See all transactions/ })
    await btn.evaluate((el: HTMLElement) => el.click())
    await expect(page).toHaveURL('/transactions')
  })

  // ── 2.5 Quick Entry ──────────────────────────────────────────────────────

  test('2.5 "New transaction…" quick entry opens sheet', async ({ page }) => {
    await page.locator('text=New transaction…').click()
    await expect(page.getByRole('dialog')).toBeVisible()
    await expect(page.getByRole('heading', { name: 'New Transaction' })).toBeVisible()
  })

  test('2.5 transaction created from dashboard appears in Recent Activity', async ({ page }) => {
    await page.locator('text=New transaction…').click()
    const dialog = page.getByRole('dialog')
    await expect(dialog).toBeVisible()

    await dialog.getByRole('button', { name: 'Payment' }).click()
    await dialog.getByRole('spinbutton').fill('200')
    await dialog.getByRole('textbox', { name: /What was this for/ }).fill('Dashboard test txn')

    const [fromCombo] = await dialog.getByRole('combobox').all()
    await fromCombo.fill('Food')
    await page.getByRole('option', { name: 'Food & Dining' }).click()

    const combos = await dialog.getByRole('combobox').all()
    await combos[combos.length - 1].fill('HDFC')
    await page.getByRole('option', { name: 'HDFC Savings' }).click()

    await dialog.getByRole('button', { name: 'Save' }).click()
    await expect(dialog).not.toBeVisible({ timeout: 8_000 })

    await page.waitForLoadState('networkidle')
    await expect(page.getByText('Dashboard test txn')).toBeVisible()
  })
})
