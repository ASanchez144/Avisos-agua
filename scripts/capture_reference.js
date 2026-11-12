// Captura la tabla visible en el visor oficial del SAI Cantábrico (referencia L8).
// Uso: node scripts/capture_reference.js <dir_salida>
// Usa el User-Agent identificable del proyecto. No modifica nada en el sitio.
const { chromium } = require('playwright');
const fs = require('fs');
const path = require('path');

const UA = 'HidroRed-Research/0.1 (proyecto ciudadano hidrologia; verificacion de fuentes)';
const URL = 'https://visor.saichcantabrico.es/';

(async () => {
  const outDir = process.argv[2];
  if (!outDir) { console.error('falta dir_salida'); process.exit(2); }
  const launch = process.env.HTTPS_PROXY ? { proxy: { server: process.env.HTTPS_PROXY } } : {};
  const browser = await chromium.launch(launch);
  const ctx = await browser.newContext({ userAgent: UA, viewport: { width: 1900, height: 1200 }, deviceScaleFactor: 1 });
  const page = await ctx.newPage();
  await page.goto(URL, { waitUntil: 'networkidle', timeout: 90000 });
  await page.waitForTimeout(3000);
  await page.getByText('Tabla', { exact: true }).first().click({ timeout: 15000 });
  await page.waitForSelector('#tabla-datos tbody tr', { timeout: 30000 });
  await page.waitForTimeout(3000);
  const capturedAt = new Date().toISOString();
  const table = await page.evaluate(() => {
    const t = document.querySelector('#tabla-datos');
    const clean = s => (s || '').replace(/\s+/g, ' ').trim();
    const header = [...t.tHead.rows[0].cells].map(c => clean(c.innerText));
    const rows = [...t.tBodies[0].rows].map(r => [...r.cells].map(c => clean(c.innerText)));
    return { header, rows };
  });
  const out = { source_url: URL, how: 'Clic en "Tabla" del visor oficial; texto visible de #tabla-datos', user_agent: UA, captured_at_utc: capturedAt, header: table.header, rows: table.rows };
  fs.writeFileSync(path.join(outDir, 'visor_tabla.json'), JSON.stringify(out, null, 1));
  await page.screenshot({ path: path.join(outDir, 'visor_tabla.png'), fullPage: false });
  console.log('capturado', capturedAt, 'filas', table.rows.length);
  await browser.close();
})().catch(e => { console.error('ERROR', e.message); process.exit(1); });
