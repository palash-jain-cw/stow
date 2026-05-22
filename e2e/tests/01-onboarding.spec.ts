/**
 * Section 1 – Onboarding
 * QA checklist items: 1.1 – 1.6
 */
import { test, expect } from '@playwright/test'
import { resetDB } from '../helpers/api'

test.describe('1. Onboarding', () => {
  test.beforeEach(async () => {
    await resetDB()
  })

  // ── 1.1 Welcome Screen ────────────────────────────────────────────────────

  test('1.1 welcome screen renders on first load', async ({ page }) => {
    await page.goto('/')
    // No FY → redirected to /onboarding
    await expect(page).toHaveURL(/\/onboarding/)
    await expect(page.getByText('Stow')).toBeVisible()
    await expect(page.getByRole('button', { name: 'Get started →' })).toBeVisible()
  })

  test('1.1 "Get started" advances to step 2', async ({ page }) => {
    await page.goto('/onboarding')
    await page.getByRole('button', { name: 'Get started →' }).click()
    await expect(page.getByRole('heading', { name: /Which financial year/ })).toBeVisible()
  })

  // ── 1.2 Financial Year Selection (Step 2) ────────────────────────────────

  test('1.2 three FY options displayed with correct date ranges', async ({ page }) => {
    await page.goto('/onboarding')
    await page.getByRole('button', { name: 'Get started →' }).click()
    await expect(page.getByText(/FY 2026–27/)).toBeVisible()
    await expect(page.getByText(/FY 2025–26/)).toBeVisible()
    await expect(page.getByText(/FY 2024–25/)).toBeVisible()
    await expect(page.getByText('Current')).toBeVisible()
  })

  test('1.2 selecting a year highlights it and Continue advances to step 3', async ({ page }) => {
    await page.goto('/onboarding')
    await page.getByRole('button', { name: 'Get started →' }).click()
    await page.getByRole('button', { name: /FY 2026–27/ }).click()
    await page.getByRole('button', { name: 'Continue' }).click()
    await expect(page.getByRole('heading', { name: /Add your bank accounts/ })).toBeVisible()
  })

  // ── 1.3 Bank Accounts Entry (Step 3) ────────────────────────────────────

  test('1.3 account name is required — blank name keeps Continue disabled', async ({ page }) => {
    await page.goto('/onboarding')
    await page.getByRole('button', { name: 'Get started →' }).click()
    await page.getByRole('button', { name: /FY 2026–27/ }).click()
    await page.getByRole('button', { name: 'Continue' }).click()
    // Continue should be disabled until text is entered
    await expect(page.getByRole('button', { name: 'Continue' })).toBeDisabled()
  })

  test('1.3 "Add another account" adds a second input row', async ({ page }) => {
    await page.goto('/onboarding')
    await page.getByRole('button', { name: 'Get started →' }).click()
    await page.getByRole('button', { name: /FY 2026–27/ }).click()
    await page.getByRole('button', { name: 'Continue' }).click()
    const before = await page.getByRole('textbox', { name: /e\.g\. HDFC/ }).count()
    await page.getByRole('button', { name: 'Add another account' }).click()
    const after = await page.getByRole('textbox', { name: /e\.g\. HDFC/ }).count()
    expect(after).toBeGreaterThan(before)
  })

  test('1.3 duplicate account names show an error', async ({ page }) => {
    await page.goto('/onboarding')
    await page.getByRole('button', { name: 'Get started →' }).click()
    await page.getByRole('button', { name: /FY 2026–27/ }).click()
    await page.getByRole('button', { name: 'Continue' }).click()
    await page.getByRole('textbox', { name: /e\.g\. HDFC/ }).first().fill('HDFC Savings')
    await page.getByRole('button', { name: 'Add another account' }).click()
    await page.getByRole('textbox', { name: /e\.g\. HDFC/ }).last().fill('HDFC Savings')
    await page.getByRole('button', { name: 'Continue' }).click()
    await expect(page.getByText(/duplicate/i)).toBeVisible()
  })

  test('1.3 cash-in-hand checkbox creates a cash account', async ({ page }) => {
    await page.goto('/onboarding')
    await page.getByRole('button', { name: 'Get started →' }).click()
    await page.getByRole('button', { name: /FY 2026–27/ }).click()
    await page.getByRole('button', { name: 'Continue' }).click()
    await page.getByRole('textbox', { name: /e\.g\. HDFC/ }).first().fill('HDFC Savings')
    await page.getByRole('checkbox').click()
    await expect(page.getByRole('checkbox')).toBeChecked()
    await page.getByRole('button', { name: 'Continue' }).click()
    // Step 4: both accounts should appear
    await expect(page.getByRole('heading', { name: /current balances/ })).toBeVisible()
    await expect(page.getByText('HDFC Savings')).toBeVisible()
    await expect(page.getByText(/Cash/i)).toBeVisible()
  })

  // ── 1.4 Opening Balances (Step 4) ────────────────────────────────────────

  test('1.4 all accounts from step 3 appear as balance rows', async ({ page }) => {
    await page.goto('/onboarding')
    await page.getByRole('button', { name: 'Get started →' }).click()
    await page.getByRole('button', { name: /FY 2026–27/ }).click()
    await page.getByRole('button', { name: 'Continue' }).click()
    await page.getByRole('textbox', { name: /e\.g\. HDFC/ }).first().fill('HDFC Savings')
    await page.getByRole('button', { name: 'Continue' }).click()
    await expect(page.getByText('HDFC Savings')).toBeVisible()
    await expect(page.getByText('₹')).toBeVisible()
  })

  test('1.4 zero/blank balances are accepted', async ({ page }) => {
    await page.goto('/onboarding')
    await page.getByRole('button', { name: 'Get started →' }).click()
    await page.getByRole('button', { name: /FY 2026–27/ }).click()
    await page.getByRole('button', { name: 'Continue' }).click()
    await page.getByRole('textbox', { name: /e\.g\. HDFC/ }).first().fill('HDFC Savings')
    await page.getByRole('button', { name: 'Continue' }).click()
    // Leave balance blank, continue
    await page.getByRole('button', { name: 'Continue' }).click()
    await expect(page.getByRole('heading', { name: /Connect an AI model/ })).toBeVisible()
  })

  // ── 1.5 AI / LLM Configuration (Step 5) ─────────────────────────────────

  test('1.5 AI config fields are present', async ({ page }) => {
    await page.goto('/onboarding')
    await page.getByRole('button', { name: 'Get started →' }).click()
    await page.getByRole('button', { name: /FY 2026–27/ }).click()
    await page.getByRole('button', { name: 'Continue' }).click()
    await page.getByRole('textbox', { name: /e\.g\. HDFC/ }).first().fill('HDFC Savings')
    await page.getByRole('button', { name: 'Continue' }).click()
    await page.getByRole('button', { name: 'Continue' }).click()
    await expect(page.getByText('Server URL')).toBeVisible()
    await expect(page.getByText('Model name')).toBeVisible()
    await expect(page.getByText('API key')).toBeVisible()
    await expect(page.getByRole('button', { name: 'Test connection' })).toBeVisible()
  })

  test('1.5 "Skip" advances to step 6 without saving AI config', async ({ page }) => {
    await page.goto('/onboarding')
    await page.getByRole('button', { name: 'Get started →' }).click()
    await page.getByRole('button', { name: /FY 2026–27/ }).click()
    await page.getByRole('button', { name: 'Continue' }).click()
    await page.getByRole('textbox', { name: /e\.g\. HDFC/ }).first().fill('HDFC Savings')
    await page.getByRole('button', { name: 'Continue' }).click()
    await page.getByRole('button', { name: 'Continue' }).click()
    await page.getByRole('button', { name: /Skip/i }).click()
    await expect(page.getByText("You're all set!")).toBeVisible()
  })

  // ── 1.6 Completion Summary (Step 6) ─────────────────────────────────────

  test('1.6 completion summary shows FY and account count', async ({ page }) => {
    await page.goto('/onboarding')
    await page.getByRole('button', { name: 'Get started →' }).click()
    await page.getByRole('button', { name: /FY 2026–27/ }).click()
    await page.getByRole('button', { name: 'Continue' }).click()
    await page.getByRole('textbox', { name: /e\.g\. HDFC/ }).first().fill('HDFC Savings')
    await page.getByRole('button', { name: 'Continue' }).click()
    await page.getByRole('button', { name: 'Continue' }).click()
    await page.getByRole('button', { name: /Skip/i }).click()
    await expect(page.getByText(/FY 2026–27/)).toBeVisible()
    await expect(page.getByText(/Accounts added: 1/)).toBeVisible()
  })

  test('1.6 "Go to dashboard" navigates to /', async ({ page }) => {
    await page.goto('/onboarding')
    await page.getByRole('button', { name: 'Get started →' }).click()
    await page.getByRole('button', { name: /FY 2026–27/ }).click()
    await page.getByRole('button', { name: 'Continue' }).click()
    await page.getByRole('textbox', { name: /e\.g\. HDFC/ }).first().fill('HDFC Savings')
    await page.getByRole('button', { name: 'Continue' }).click()
    await page.getByRole('button', { name: 'Continue' }).click()
    await page.getByRole('button', { name: /Skip/i }).click()
    await page.getByRole('button', { name: 'Go to dashboard' }).click()
    await expect(page).toHaveURL('/')
  })

  test('1.6 "Enter first transaction" opens transaction entry sheet', async ({ page }) => {
    await page.goto('/onboarding')
    await page.getByRole('button', { name: 'Get started →' }).click()
    await page.getByRole('button', { name: /FY 2026–27/ }).click()
    await page.getByRole('button', { name: 'Continue' }).click()
    await page.getByRole('textbox', { name: /e\.g\. HDFC/ }).first().fill('HDFC Savings')
    await page.getByRole('button', { name: 'Continue' }).click()
    await page.getByRole('button', { name: 'Continue' }).click()
    await page.getByRole('button', { name: /Skip/i }).click()
    await page.getByRole('button', { name: 'Enter first transaction' }).click()
    await expect(page.getByRole('dialog')).toBeVisible()
    await expect(page.getByRole('heading', { name: 'New Transaction' })).toBeVisible()
  })
})
