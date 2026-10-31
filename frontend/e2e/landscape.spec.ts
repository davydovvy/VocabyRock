import { expect, test, type Page } from '@playwright/test'

test.use({ hasTouch: true, isMobile: true })

async function expectInViewport(page: Page, selector: string) {
  const bottom = await page
    .locator(selector)
    .evaluate((element) => element.getBoundingClientRect().bottom)
  const height = await page.evaluate(() => window.innerHeight)
  expect(bottom).toBeLessThanOrEqual(height)
}

test('child home and common games fit a short iPad landscape viewport', async ({ page }) => {
  await page.setViewportSize({ width: 1024, height: 700 })
  await page.goto('/')
  await page.locator('.profile-grid').waitFor()
  await expectInViewport(page, '.profile-grid')
  await page.getByRole('button', { name: /Explorer One/ }).click()
  await page.getByRole('article').filter({ hasText: 'Animals' }).waitFor()
  await expectInViewport(page, '.home-pack-grid')

  for (const game of ['Pick the Word', 'Big Match', 'Flip Cards', 'Type It', 'Listen']) {
    await page
      .getByRole('article')
      .filter({ hasText: 'Animals' })
      .getByRole('button', { name: 'Study' })
      .click()
    await expectInViewport(page, '.child-choose')
    await page.getByRole('button', { name: game, exact: true }).click()
    const selector = game === 'Big Match' ? '.big-match' : '.game-screen'
    await page.locator(selector).waitFor()
    await expectInViewport(page, selector)
    if (game === 'Type It') {
      await expect(page.getByRole('textbox', { name: 'Your answer' })).not.toBeFocused()
    }
    await page.getByRole('button', { name: 'Back', exact: true }).click()
    await page.getByRole('article').filter({ hasText: 'Animals' }).waitFor()
  }
})

test('Big Match fits iPad landscape and supports dragging and tapping', async ({ page }) => {
  for (const size of [
    { width: 1024, height: 768 },
    { width: 1180, height: 820 },
  ]) {
    await page.setViewportSize(size)
    await page.context().clearCookies()
    await page.goto('/')
    await page.locator('.profile-grid').waitFor()
    await page.getByRole('button', { name: /Explorer One/ }).click()
    await page
      .getByRole('article')
      .filter({ hasText: 'Animals' })
      .getByRole('button', { name: 'Study' })
      .click()
    await page.getByRole('button', { name: 'Big Match' }).click()
    await expect(page.locator('.big-match-card')).toHaveCount(8)
    await expect(page.locator('.big-match-pool-cell')).toHaveCount(8)
    await expectInViewport(page, '.big-match')
    expect(
      await page.evaluate(() => document.documentElement.scrollHeight <= window.innerHeight + 1),
    ).toBe(true)
    const tile = page.locator('.big-match-pool .big-match-tile').first()
    const card = page.locator('.big-match-card').first()
    await tile.dragTo(card)
    await expect(card.locator('.big-match-tile')).toHaveCount(1)
    await card.locator('.big-match-tile').dragTo(page.locator('.big-match-pool-cell').first())
    await expect(card.locator('.big-match-tile')).toHaveCount(0)
    const sourceBox = await tile.boundingBox()
    const targetBox = await card.boundingBox()
    if (!sourceBox || !targetBox) throw new Error('Big Match tile or card is missing')
    const source = { x: sourceBox.x + sourceBox.width / 2, y: sourceBox.y + sourceBox.height / 2 }
    const target = { x: targetBox.x + targetBox.width / 2, y: targetBox.y + targetBox.height / 2 }
    const cdp = await page.context().newCDPSession(page)
    await cdp.send('Input.dispatchTouchEvent', { type: 'touchStart', touchPoints: [source] })
    for (let step = 1; step <= 6; step++) {
      await cdp.send('Input.dispatchTouchEvent', {
        type: 'touchMove',
        touchPoints: [
          {
            x: source.x + ((target.x - source.x) * step) / 6,
            y: source.y + ((target.y - source.y) * step) / 6,
          },
        ],
      })
    }
    await cdp.send('Input.dispatchTouchEvent', { type: 'touchEnd', touchPoints: [] })
    await expect(card.locator('.big-match-tile')).toHaveCount(1)
    await cdp.detach()
    const firstText = await card.locator('.big-match-tile').textContent()
    await page.locator('.big-match-pool .big-match-tile').first().click()
    await card.locator('.big-match-word').click()
    await expect(
      page.locator('.big-match-pool .big-match-tile').filter({ hasText: firstText || '' }),
    ).toHaveCount(1)
    const nextCard = page.locator('.big-match-card').nth(1)
    await card.locator('.big-match-tile').dragTo(nextCard)
    await expect(card.locator('.big-match-tile')).toHaveCount(0)
    await expect(nextCard.locator('.big-match-tile')).toHaveCount(1)
    await nextCard.locator('.big-match-tile').dragTo(page.locator('.big-match-heading h1'))
    await expect(nextCard.locator('.big-match-tile')).toHaveCount(1)
    await page.getByRole('button', { name: 'Reset' }).click()
    await expect(page.locator('.big-match-pool .big-match-tile')).toHaveCount(8)
    await page.getByRole('button', { name: 'Back', exact: true }).click()
  }
})
