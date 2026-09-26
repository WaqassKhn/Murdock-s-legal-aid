import { test, expect } from '@playwright/test';

const contract = `SYNTHETIC EMPLOYMENT AGREEMENT - TEST ONLY
1. Parties
This agreement is between Acme Ltd (Employer) and Alex Morgan (Employee).
2. Effective Date
This agreement is effective on 2026-01-01.
3. Payment
The Employer shall pay the Employee USD 5000 each month.
4. Termination
Either party may terminate this agreement by providing 30 days written notice.
5. Confidentiality
The Employee shall keep the Employer's confidential information confidential for 2 years after termination.
6. Governing Law
This agreement is governed by the laws of England and Wales.
`;

test('create an isolated workspace, upload, inspect citations, ask, compare and export', async ({
  page,
}) => {
  const suffix = Date.now().toString();
  await page.goto('/');
  await page.getByLabel('Email address').fill(`browser-${suffix}@example.test`);
  await page.getByLabel('Password', { exact: true }).fill('LegalLens-browser-passphrase-42');
  await page.getByRole('button', { name: 'Create your account' }).click();
  await expect(page.getByRole('heading', { name: 'A clearer picture starts here.' })).toBeVisible();
  await page.getByRole('button', { name: 'New workspace', exact: true }).click();
  await page.getByLabel('Workspace name').fill(`Browser review ${suffix}`);
  await page
    .getByLabel('Your objective')
    .fill('Understand termination and confidentiality before speaking with a lawyer.');
  await page.getByRole('button', { name: 'Create workspace', exact: true }).click();
  await expect(page.getByRole('heading', { name: 'Documents', exact: true })).toBeVisible();
  await page.getByLabel('Upload documents', { exact: true }).setInputFiles({
    name: 'agreement.txt',
    mimeType: 'text/plain',
    buffer: Buffer.from(contract),
  });
  await expect(page.getByText('Ready', { exact: true })).toBeVisible({ timeout: 60000 });
  await page.getByRole('button', { name: 'agreement.txt', exact: true }).click();
  await expect(page.getByRole('heading', { name: 'Document analysis' })).toBeVisible();
  await expect(page.getByRole('heading', { name: 'What the document says' })).toBeVisible();
  await page.locator('.citation').first().click();
  await expect(page.getByRole('dialog', { name: 'Follow the evidence' })).toBeVisible();
  await expect(page.getByText('Excerpt verified', { exact: true })).toBeVisible();
  await expect(page.getByTestId('source-highlight')).toBeVisible();
  await page.getByRole('button', { name: 'Close dialog' }).click();
  await page.getByRole('tab', { name: 'Evidence Map' }).click();
  await expect(page.getByRole('heading', { name: 'Follow the evidence.' })).toBeVisible();
  await page.getByRole('button', { name: 'Ask', exact: true }).click();
  await page
    .getByLabel('Your question', { exact: true })
    .fill('What is the tenant pet policy for elephants?');
  await page.getByRole('button', { name: 'Ask question', exact: true }).click();
  await expect(
    page.getByText(
      'I could not find enough information in the uploaded documents to answer this reliably.',
    ),
  ).toBeVisible();
  await page
    .getByLabel('Your question', { exact: true })
    .fill('Can I terminate this agreement early?');
  await page.getByRole('button', { name: 'Ask question', exact: true }).click();
  await expect(page.locator('.answer-evidence .citation').first()).toBeVisible();
  await page
    .getByRole('navigation', { name: 'Main navigation' })
    .getByRole('button', { name: /^Documents/ })
    .click();
  await page.getByLabel('Upload documents', { exact: true }).setInputFiles({
    name: 'amended.txt',
    mimeType: 'text/plain',
    buffer: Buffer.from(contract.replace('30 days', '60 days').replace('USD 5000', 'USD 6000')),
  });
  await expect(page.getByText('Ready', { exact: true })).toHaveCount(2, { timeout: 60000 });
  await page.getByRole('button', { name: 'Compare', exact: true }).click();
  await page.getByRole('button', { name: 'Compare documents', exact: true }).click();
  await expect(page.locator('.comparison-finding').first()).toBeVisible();
  await page.getByRole('button', { name: 'Review checklist coverage' }).click();
  await expect(page.getByText('Source located', { exact: true }).first()).toBeVisible();
  await expect(page.getByText('Review coverage gap', { exact: true }).first()).toBeVisible();
  await page.getByRole('button', { name: 'Obligations', exact: true }).click();
  await expect(page.locator('.obligation-table')).toBeVisible();
  const checkbox = page.getByRole('checkbox').first();
  await checkbox.check();
  await expect(checkbox).toBeChecked();
  await page.getByRole('button', { name: 'Edit personal task', exact: true }).first().click();
  await page
    .getByLabel('Your action', { exact: true })
    .fill('Prepare notice evidence for the lawyer.');
  await page
    .getByLabel('Your notes', { exact: true })
    .fill('Confirm which delivery method applies.');
  await page.getByRole('button', { name: 'Save personal task', exact: true }).click();
  await expect(
    page.getByText('Prepare notice evidence for the lawyer.', { exact: true }),
  ).toBeVisible();
  await page.getByRole('tab', { name: 'Timeline', exact: true }).click();
  await expect(page.getByRole('heading', { name: 'Dates & time windows' })).toBeVisible();
  await page.screenshot({ path: 'test-results/action-timeline.png', fullPage: true });
  await page.locator('.timeline-event .citation').first().click();
  await expect(page.getByText('Excerpt verified', { exact: true })).toBeVisible();
  await page.getByRole('button', { name: 'Close dialog' }).click();
  await page.getByRole('button', { name: 'Reports', exact: true }).click();
  await page.getByRole('button', { name: 'Obligations', exact: true }).click();
  await expect(
    page.getByText('Prepare notice evidence for the lawyer.', { exact: true }),
  ).toBeVisible();
  await expect(
    page.getByText('Confirm which delivery method applies.', { exact: true }),
  ).toBeVisible();
  await expect(page.getByRole('checkbox').first()).toBeChecked();
  await page.screenshot({ path: 'test-results/action-center.png', fullPage: true });
  const actionDownloadPromise = page.waitForEvent('download');
  await page.getByRole('link', { name: 'Download action plan' }).click();
  const actionDownload = await actionDownloadPromise;
  expect(actionDownload.suggestedFilename()).toBe('legallens-action-plan.md');
  const markdownStream = await actionDownload.createReadStream();
  let markdown = '';
  for await (const chunk of markdownStream!) markdown += chunk.toString();
  expect(markdown).toContain('Prepare notice evidence for the lawyer.');
  expect(markdown).toContain('User notes');
  expect(markdown).toContain('Source document:');
  await page.getByRole('button', { name: 'Reports', exact: true }).click();
  await page.getByRole('button', { name: 'Generate consultation pack', exact: true }).click();
  await expect(page.getByRole('link', { name: 'Download', exact: true })).toBeVisible({
    timeout: 60000,
  });
  const downloadPromise = page.waitForEvent('download');
  await page.getByRole('link', { name: 'Download', exact: true }).click();
  const download = await downloadPromise;
  expect(download.suggestedFilename()).toMatch(/\.pdf$/);
  await page
    .getByRole('navigation', { name: 'Main navigation' })
    .getByRole('button', { name: 'Workspaces', exact: true })
    .click();
  await page.screenshot({ path: 'test-results/workspace-desktop.png', fullPage: true });
  await page.setViewportSize({ width: 390, height: 844 });
  await page.screenshot({ path: 'test-results/workspace-mobile.png', fullPage: true });
  expect(
    await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth),
  ).toBeTruthy();
  await page
    .getByRole('button', { name: `Delete workspace Browser review ${suffix}`, exact: true })
    .click();
  await page.getByRole('button', { name: 'Delete workspace', exact: true }).click();
  await expect(page.getByRole('heading', { name: 'Give your documents a home' })).toBeVisible();
});

function syntheticPdf(): Buffer {
  const stream =
    'BT /F1 14 Tf 50 750 Td (SYNTHETIC TEST DOCUMENT) Tj 0 -30 Td (1. Payment) Tj 0 -24 Td (The Customer must pay USD 500 monthly.) Tj ET';
  const objects = [
    '<< /Type /Catalog /Pages 2 0 R >>',
    '<< /Type /Pages /Kids [3 0 R] /Count 1 >>',
    '<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Resources << /Font << /F1 4 0 R >> >> /Contents 5 0 R >>',
    '<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>',
    `<< /Length ${Buffer.byteLength(stream)} >>\nstream\n${stream}\nendstream`,
  ];
  let pdf = '%PDF-1.4\n';
  const offsets = [0];
  objects.forEach((object, i) => {
    offsets.push(Buffer.byteLength(pdf));
    pdf += `${i + 1} 0 obj\n${object}\nendobj\n`;
  });
  const xref = Buffer.byteLength(pdf);
  pdf += `xref\n0 6\n0000000000 65535 f \n${offsets
    .slice(1)
    .map((offset) => String(offset).padStart(10, '0') + ' 00000 n ')
    .join('\n')}\ntrailer\n<< /Size 6 /Root 1 0 R >>\nstartxref\n${xref}\n%%EOF`;
  return Buffer.from(pdf);
}

test('PDF citation displays its verified original page as an inert image', async ({ page }) => {
  const email = `pdf-${Date.now()}@example.test`;
  await page.goto('/');
  await page.getByLabel('Email address').fill(email);
  await page.getByLabel('Password', { exact: true }).fill('LegalLens-browser-passphrase-42');
  await page.getByRole('button', { name: 'Create your account' }).click();
  await page.getByRole('button', { name: 'New workspace', exact: true }).click();
  await page.getByLabel('Workspace name').fill('Synthetic PDF evidence');
  await page.getByRole('button', { name: 'Create workspace', exact: true }).click();
  await page
    .getByLabel('Upload documents', { exact: true })
    .setInputFiles({ name: 'synthetic.pdf', mimeType: 'application/pdf', buffer: syntheticPdf() });
  await expect(page.getByText('Ready', { exact: true })).toBeVisible({ timeout: 60000 });
  await page.getByRole('button', { name: 'synthetic.pdf', exact: true }).click();
  await page.locator('.citation').first().click();
  await expect(page.getByText('Excerpt verified', { exact: true })).toBeVisible();
  await page.getByRole('button', { name: 'Original PDF', exact: true }).click();
  const image = page.getByRole('img', { name: /Original source page 1/ });
  await expect(image).toBeVisible();
  await expect(image).toHaveJSProperty('complete', true);
  expect(await image.evaluate((element: HTMLImageElement) => element.naturalWidth)).toBeGreaterThan(
    0,
  );
  await page.screenshot({ path: 'test-results/pdf-evidence.png', fullPage: true });
  if (process.env.E2E_TEMPORARY_SESSION === 'true') {
    await page.reload();
    await expect(page.getByRole('button', { name: 'Create your account' })).toBeVisible();
  }
});
