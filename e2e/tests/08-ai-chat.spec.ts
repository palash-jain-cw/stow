/**
 * Section 8 – AI Chat (Web Interface)
 * QA checklist items: 8.1 – 8.6
 *
 * NOTE: Most tests in this section require a running oMLX server reachable
 * from within Docker (host.docker.internal:8001). Tests that depend on actual
 * LLM responses are marked with test.skip unless the server is available.
 * The UI smoke tests (chat panel renders, input works) run unconditionally.
 */
import { test, expect, request } from '@playwright/test'
import { resetDB, setupBaseState } from '../helpers/api'

async function isAiAvailable(): Promise<boolean> {
  try {
    const ctx = await request.newContext({ baseURL: 'http://localhost:8000' })
    const res = await ctx.post('/ai/test-connection', { timeout: 10_000 })
    const body = await res.json()
    await ctx.dispose()
    return body.ok === true
  } catch {
    return false
  }
}

test.describe('8. AI Chat', () => {
  test.beforeAll(async () => {
    await resetDB()
    await setupBaseState()
  })

  test.beforeEach(async ({ page }) => {
    await page.goto('/')
    await page.waitForLoadState('networkidle')
  })

  // ── 8.1 Chat UI ───────────────────────────────────────────────────────────

  test('8.1 chat panel is visible on dashboard', async ({ page }) => {
    await expect(page.getByRole('textbox', { name: /Type a message/i })).toBeVisible()
  })

  test('8.1 chat input is present and accepts text', async ({ page }) => {
    const input = page.getByRole('textbox', { name: /Type a message/i })
    await input.fill('Hello')
    await expect(input).toHaveValue('Hello')
  })

  test('8.1 "Attach image or PDF" button is present', async ({ page }) => {
    await expect(page.getByRole('button', { name: /Attach image or PDF/i })).toBeVisible()
  })

  // ── 8.2 Natural Language Transaction Entry ────────────────────────────────

  test('8.2 sending a message (with AI available)', async ({ page }) => {
    if (!(await isAiAvailable())) {
      test.skip(true, 'oMLX server not available')
      return
    }
    const input = page.getByRole('textbox', { name: /Type a message/i })
    await input.fill('Paid ₹500 at Swiggy')
    await page.keyboard.press('Enter')
    // Bot should respond within 30s
    await expect(page.getByText(/Swiggy|proposal|confirm/i)).toBeVisible({ timeout: 30_000 })
  })

  // ── 8.5 Account Queries via Chat ─────────────────────────────────────────

  test('8.5 querying balance (with AI available)', async ({ page }) => {
    if (!(await isAiAvailable())) {
      test.skip(true, 'oMLX server not available')
      return
    }
    const input = page.getByRole('textbox', { name: /Type a message/i })
    await input.fill("What's my HDFC balance?")
    await page.keyboard.press('Enter')
    // AI response bubbles use rounded-bl-sm; user bubbles use rounded-br-sm
    await expect(page.locator('.rounded-bl-sm').last()).toBeVisible({ timeout: 30_000 })
  })
})
