/**
 * Portfolio investment UI — TDD cycles (buy, sell, FD open/mature, deep links)
 */
import { test, expect, request } from '@playwright/test'
import { resetDB, setupBaseState, TestState, API_BASE } from '../helpers/api'

let s: TestState
let mfAccountId: number
let mfAccountName: string

async function createMfAccount(name: string): Promise<number> {
  const ctx = await request.newContext({ baseURL: API_BASE })
  const res = await ctx.post('/accounts', {
    data: { name, group_id: s.invGroupId, investment_subtype: 'equity_mf' },
  })
  const account = await res.json()
  await ctx.dispose()
  return account.id
}

async function buyViaApi(accountId: number, units: number, costPerUnit: number, date: string) {
  const ctx = await request.newContext({ baseURL: API_BASE })
  await ctx.post(`/investments/${accountId}/buy`, {
    data: {
      units,
      cost_per_unit: costPerUnit,
      date,
      fy_id: s.fyId,
      bank_account_id: s.hdfcId,
      narration: 'API buy',
    },
  })
  await ctx.dispose()
}

test.describe('Portfolio investment UI', () => {
  test.beforeEach(async () => {
    await resetDB()
    s = await setupBaseState()
    mfAccountName = 'Axis Bluechip Fund'
    mfAccountId = await createMfAccount(mfAccountName)
  })

  test('user can record MF purchase from Portfolio', async ({ page }) => {
    await page.goto('/portfolio')
    await page.waitForLoadState('networkidle')

    await page.getByRole('button', { name: 'Record purchase' }).click()
    const dialog = page.getByRole('dialog')
    await expect(dialog).toBeVisible()

    await dialog.getByLabel('Investment account').selectOption({ label: mfAccountName })
    await dialog.getByLabel('Pay from').selectOption(String(s.hdfcId))
    await dialog.getByLabel('Units').fill('10')
    await dialog.getByLabel('NAV per unit').fill('45')
    await dialog.getByLabel('Narration').fill('SIP purchase')
    await dialog.getByRole('button', { name: 'Record purchase' }).click()

    await expect(dialog).not.toBeVisible({ timeout: 10_000 })
    await expect(page.getByText(mfAccountName)).toBeVisible()
    await expect(page.getByRole('cell', { name: '10' }).first()).toBeVisible()
  })

  test('user can partially sell MF from holdings row', async ({ page }) => {
    await buyViaApi(mfAccountId, 100_000, 4500, '2026-05-01')

    await page.goto('/portfolio')
    await page.waitForLoadState('networkidle')

    await page.getByRole('button', { name: 'Sell' }).click()
    const dialog = page.getByRole('dialog')
    await expect(dialog).toBeVisible()
    await expect(dialog.getByText(/Available: 100/)).toBeVisible()

    await dialog.getByLabel('Units').fill('50')
    await dialog.getByLabel('NAV per unit').fill('55')
    await dialog.getByLabel('Receive into').selectOption(String(s.hdfcId))
    await dialog.getByLabel('Narration').fill('Partial redemption')
    await dialog.getByRole('button', { name: 'Record sale' }).click()

    await expect(dialog).not.toBeVisible({ timeout: 10_000 })
    await expect(page.getByRole('cell', { name: '50' }).first()).toBeVisible()
  })

  test('user can open a fixed deposit from Portfolio', async ({ page }) => {
    await page.goto('/portfolio?tab=fds')
    await page.waitForLoadState('networkidle')

    await page.getByRole('button', { name: 'Open fixed deposit' }).click()
    const dialog = page.getByRole('dialog')
    await expect(dialog).toBeVisible()

    await dialog.getByLabel('FD name').fill('ICICI FD May 2027')
    await dialog.getByLabel('Principal').fill('100000')
    await dialog.getByLabel('Interest rate').fill('7.5')
    await dialog.getByLabel('Start date').fill('2026-05-01')
    await dialog.getByLabel('Maturity date').fill('2027-05-01')
    await dialog.getByLabel('Compounding').selectOption('quarterly')
    await dialog.getByLabel('Fund from').selectOption(String(s.hdfcId))
    await dialog.getByLabel('Narration').fill('Open FD')
    await dialog.getByRole('button', { name: 'Open fixed deposit' }).click()

    await expect(dialog).not.toBeVisible({ timeout: 10_000 })
    await expect(page.getByText('ICICI FD May 2027')).toBeVisible()
    await expect(page.getByText('Active')).toBeVisible()
  })

  test('user can mature an active FD from row', async ({ page }) => {
    const ctx = await request.newContext({ baseURL: API_BASE })
    await ctx.post('/investments/fds', {
      data: {
        name: 'HDFC FD Mature Test',
        principal: 5_000_000,
        interest_rate: 700,
        start_date: '2026-04-01',
        maturity_date: '2027-04-01',
        compounding: 'quarterly',
        from_account_id: s.hdfcId,
        fy_id: s.fyId,
        date: '2026-04-01',
        narration: 'Open FD for mature test',
      },
    })
    await ctx.dispose()

    await page.goto('/portfolio?tab=fds')
    await page.waitForLoadState('networkidle')

    await page.getByRole('button', { name: 'Mature' }).click()
    const dialog = page.getByRole('dialog')
    await expect(dialog).toBeVisible()

    await dialog.getByLabel('Receive into').selectOption(String(s.hdfcId))
    await dialog.getByLabel('Narration').fill('FD matured')
    await dialog.getByRole('button', { name: 'Mature fixed deposit' }).click()

    await expect(dialog).not.toBeVisible({ timeout: 10_000 })
    await expect(page.locator('span').filter({ hasText: 'Matured' }).first()).toBeVisible()
  })

  test('Record investment link opens buy sheet on Portfolio', async ({ page }) => {
    await page.goto('/transactions')
    await page.waitForLoadState('networkidle')

    await page.getByRole('link', { name: 'Record investment' }).click()
    await page.waitForLoadState('networkidle')

    await expect(page).toHaveURL(/\/portfolio/)
    const dialog = page.getByRole('dialog')
    await expect(dialog).toBeVisible()
    await expect(dialog.getByRole('heading', { name: 'Record purchase' })).toBeVisible()
  })
})
