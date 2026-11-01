import { expect, test } from '@playwright/test'

test('child answer fields keep native Latin and Cyrillic editing without assistance requests', async ({
  page,
}) => {
  await page.goto('/')
  await page.getByRole('button', { name: /Explorer One/ }).click()

  for (const [direction, answer] of [
    ['Russian → English', 'hello'],
    ['English → Russian', 'привет'],
  ]) {
    await page
      .getByRole('article')
      .filter({ hasText: 'Animals' })
      .getByRole('button', { name: 'Study' })
      .click()
    await page.getByRole('button', { name: direction }).click()
    await page.getByRole('button', { name: 'Type It' }).click()

    const input = page.getByRole('textbox', { name: 'Your answer' })
    await expect(input).toHaveAttribute('type', 'text')
    await expect(input).toHaveAttribute('autocomplete', 'off')
    await expect(input).toHaveAttribute('autocorrect', 'off')
    await expect(input).toHaveAttribute('autocapitalize', 'none')
    await expect(input).toHaveAttribute('spellcheck', 'false')
    await expect(input).not.toHaveAttribute('inputmode')

    await input.click()
    await input.pressSequentially(answer)
    await expect(input).toHaveValue(answer)
    await input.press('Backspace')
    await expect(input).toHaveValue(answer.slice(0, -1))
    await input.pressSequentially(answer.slice(-1))
    await expect(input).toHaveValue(answer)
    await page.getByRole('button', { name: 'Back', exact: true }).click()
  }

  await page
    .getByRole('article')
    .filter({ hasText: 'Animals' })
    .getByRole('button', { name: 'Test' })
    .click()
  await expect(page.getByRole('textbox', { name: 'Your answer' })).toHaveAttribute(
    'autocomplete',
    'off',
  )
})
