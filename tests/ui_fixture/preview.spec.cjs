const { test, expect } = require('@playwright/test');
const fs = require('node:fs');
const http = require('node:http');
let server, origin;

test.beforeAll(async () => {
  server = http.createServer((request, response) => {
    if (request.url === '/') {
      response.writeHead(200, { 'Content-Type': 'text/html' });
      response.end(fs.readFileSync('dist/index.html'));
    } else if (request.url.startsWith('/doc?name=')) {
      response.end(new URL(request.url, 'http://localhost').searchParams.get('name'));
    } else { response.writeHead(404); response.end(); }
  });
  await new Promise(resolve => server.listen(0, '127.0.0.1', resolve));
  origin = `http://127.0.0.1:${server.address().port}`;
});
test.afterAll(async () => {
  server.closeAllConnections();
  await new Promise(resolve => server.close(resolve));
});

test('[document-current] later selection survives an earlier response', async ({ page }) => {
  const errors = [];
  page.on('pageerror', error => errors.push(error.message));
  page.on('console', message => { if (message.type() === 'error') errors.push(message.text()); });
  let holdA;
  const requestedA = new Promise(resolve => { holdA = resolve; });
  let completeA;
  const releasedA = new Promise(resolve => { completeA = resolve; });
  await page.route('**/doc?name=A', async route => {
    holdA();
    await releasedA;
    await route.fulfill({ status: 200, body: 'A' });
  });
  await page.goto(origin);
  await page.getByRole('button', { name: 'Open A' }).click();
  await requestedA;
  await page.getByRole('button', { name: 'Open B' }).click();
  await expect(page.locator('#document'), 'latest selection is shown').toHaveText('B');
  completeA();
  await expect(page.locator('article')).toHaveAttribute('data-pending', '0');
  await expect(page.locator('#document'), 'stale response cannot replace selection').toHaveText('B');
  expect(errors, 'no unexpected browser errors').toEqual([]);
});
