import { expect, test } from '@playwright/test'

test('child plays, parent adds a word, child finds it', async ({ page }) => {
  const password = process.env.ADMIN_PASSWORD
  if (!password) throw new Error('Set ADMIN_PASSWORD for this smoke test')
  const word = `lantern${Date.now()}`

  await page.goto('/')
  await page.getByRole('button', { name: /Explorer One/ }).click()
  await expect(page.getByText('Ready to study?')).toBeVisible()
  await page
    .getByRole('article')
    .filter({ hasText: 'Animals' })
    .getByRole('button', { name: 'Study' })
    .click()
  await page.getByRole('button', { name: 'Flip Cards' }).click()
  for (let i = 0; i < 10; i++) {
    await page.getByRole('button', { name: 'Reveal' }).click()
    await page.getByRole('button', { name: 'Easy' }).click()
    await page.getByRole('button', { name: i === 9 ? 'See Stars' : 'Next' }).click()
  }
  await expect(page.getByText('Great job!')).toBeVisible()
  await page.getByRole('button', { name: 'Home' }).click()
  await page.getByRole('button', { name: 'Switch' }).click()
  await page.getByRole('button', { name: /Parent Parent area/ }).click()
  await page.getByLabel('Password', { exact: true }).fill(password)
  await page.getByRole('button', { name: 'Sign in', exact: true }).click()
  await expect(page.getByText('Welcome, Parent')).toBeVisible()
  await page.getByRole('button', { name: 'Vocabulary' }).click()
  await page.getByRole('button', { name: 'Add Word' }).click()
  await page.getByLabel('English', { exact: true }).fill(word)
  await page.getByLabel('Russian translations (separate with ;)').fill('фонарь')
  await page.getByRole('button', { name: 'Save Word' }).click()
  await expect(page.getByText(word)).toBeVisible()
  await page.getByRole('button', { name: 'Switch profile' }).click()
  await page.getByRole('button', { name: /Explorer One/ }).click()
  await page.getByRole('button', { name: /My Words/ }).click()
  await expect(page.getByText(word)).toBeVisible()
})
