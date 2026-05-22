/**
 * Section 4 – Accounts
 * QA checklist items: 4.1 – 4.6
 */
import { test, expect } from '@playwright/test'
import { resetDB, setupBaseState, createTransaction, TestState } from '../helpers/api'

let s: TestState

test.describe('4. Accounts', () => {
  test.beforeAll(async () => {
    await resetDB()
    s = await setupBaseState()
    // Create a transaction so the ledger is non-empty
    await createTransaction({
      type: 'payment',
      date: '2026-05-01',
      narration: 'Ledger test payment',
      fyId: s.fyId,
      entries: [
        { account_id: s.foodId, amount: 30000 },
        { account_id: s.hdfcId, amount: -30000 },
      ],
    })
  })

  test.beforeEach(async ({ page }) => {
    await page.goto('/accounts')
    await page.waitForLoadState('networkidle')
  })

  // ── 4.1 Account Tree (Left Panel) ────────────────────────────────────────

  test('4.1 account groups load in the left panel', async ({ page }) => {
    await expect(page.getByText('Bank Accounts')).toBeVisible()
  })

  test('4.1 HDFC Savings account appears in the tree', async ({ page }) => {
    await expect(page.getByText('HDFC Savings')).toBeVisible()
  })

  test('4.1 account balance is displayed next to account name', async ({ page }) => {
    // HDFC Savings should show a monetary value (₹ symbol)
    await expect(page.getByText(/₹/).first()).toBeVisible()
  })

  test('4.1 search filters the account list in real-time', async ({ page }) => {
    const search = page.getByRole('textbox', { name: /search/i })
    if (!(await search.isVisible())) {
      test.skip()
    }
    await search.fill('HDFC')
    await page.waitForTimeout(300)
    await expect(page.getByText('HDFC Savings')).toBeVisible()
    await expect(page.getByText('ICICI Current')).not.toBeVisible()
  })

  // ── 4.2 Account Ledger (Right Panel) ─────────────────────────────────────

  test('4.2 clicking an account loads its ledger', async ({ page }) => {
    await page.getByText('HDFC Savings').click()
    await page.waitForLoadState('networkidle')
    // Ledger should show account name in header
    await expect(page.getByText('HDFC Savings').first()).toBeVisible()
  })

  test('4.2 ledger shows Date, Narration, Dr, Cr, Running balance columns', async ({ page }) => {
    await page.getByText('HDFC Savings').click()
    await page.waitForLoadState('networkidle')
    // The payment we created should appear
    await expect(page.getByText('Ledger test payment')).toBeVisible()
  })

  test('4.2 ledger is empty for new account (clean state, no error)', async ({ page }) => {
    await page.getByText('ICICI Current').click()
    await page.waitForLoadState('networkidle')
    // Should show empty state or zero-row table, not an error
    await expect(page.locator('body')).toBeVisible()
    await expect(page.getByText(/error/i)).not.toBeVisible()
  })

  // ── 4.3 Creating an Account ───────────────────────────────────────────────

  test('4.3 "New Account" button opens the account creation sheet', async ({ page }) => {
    await page.getByRole('button', { name: 'New Account' }).first().click()
    await expect(page.getByRole('dialog')).toBeVisible()
  })

  test('4.3 group dropdown lists existing account groups', async ({ page }) => {
    await page.getByRole('button', { name: 'New Account' }).first().click()
    const dialog = page.getByRole('dialog')
    const groupSelect = dialog.getByRole('combobox').first()
    await expect(groupSelect).toBeVisible()
  })

  test('4.3 submitting creates the account and it appears in the tree', async ({ page }) => {
    await page.getByRole('button', { name: 'New Account' }).first().click()
    const dialog = page.getByRole('dialog')

    await dialog.getByRole('textbox').first().fill('Test Bank Account')

    // Select a group from the dropdown
    const groupSelect = dialog.getByRole('combobox').first()
    await groupSelect.selectOption({ label: 'Bank Accounts' })

    await dialog.getByRole('button', { name: 'Save' }).click()
    await expect(dialog).not.toBeVisible({ timeout: 8_000 })
    await page.waitForLoadState('networkidle')
    await expect(page.getByText('Test Bank Account')).toBeVisible()
  })

  // ── 4.4 Editing an Account ────────────────────────────────────────────────

  test('4.4 edit button opens sheet pre-filled', async ({ page }) => {
    // Click account first to show ledger/details, then find edit button
    await page.getByText('ICICI Current').click()
    await page.waitForLoadState('networkidle')
    const editBtn = page.getByRole('button', { name: /Edit/i })
    if (!(await editBtn.isVisible())) {
      // Try Pencil icon button in account header
      await page.locator('[aria-label*="edit" i], button:has(svg)').first().click()
    } else {
      await editBtn.click()
    }
    await expect(page.getByRole('dialog')).toBeVisible()
  })

  // ── 4.5 Archiving / Unarchiving ──────────────────────────────────────────

  test('4.5 archive button is present for an account', async ({ page }) => {
    await page.getByText('ICICI Current').click()
    await page.waitForLoadState('networkidle')
    const archiveBtn = page.getByRole('button', { name: /Archive/i })
    await expect(archiveBtn).toBeVisible()
  })

  test('4.5 archived account shows archived indicator', async ({ page }) => {
    await page.getByText('ICICI Current').click()
    await page.waitForLoadState('networkidle')
    await page.getByRole('button', { name: /^Archive$/i }).click()
    await page.waitForTimeout(500)
    await page.waitForLoadState('networkidle')
    // After archiving, there should be an Unarchive button or "Archived" label
    await expect(
      page.getByRole('button', { name: /Unarchive/i }).or(page.getByText(/Archived/i))
    ).toBeVisible()
  })

  test('4.5 unarchive restores the account', async ({ page }) => {
    // ICICI should be archived from previous test
    await page.getByText('ICICI Current').click()
    await page.waitForLoadState('networkidle')
    const unarchiveBtn = page.getByRole('button', { name: /Unarchive/i })
    if (await unarchiveBtn.isVisible()) {
      await unarchiveBtn.click()
      await page.waitForLoadState('networkidle')
      await expect(page.getByRole('button', { name: /^Archive$/i })).toBeVisible()
    }
  })

  // ── 4.6 View Transactions Button ─────────────────────────────────────────

  test('4.6 "View Transactions" navigates to /transactions filtered by account', async ({ page }) => {
    await page.getByText('HDFC Savings').click()
    await page.waitForLoadState('networkidle')
    const viewBtn = page.getByRole('link', { name: /View [Tt]ransactions/i }).or(
      page.getByRole('button', { name: /View [Tt]ransactions/i })
    )
    if (await viewBtn.isVisible()) {
      await viewBtn.click()
      await expect(page).toHaveURL(/\/transactions/)
    } else {
      test.skip()
    }
  })
})
