// Captura los datos que el visor oficial de la ACA ("Aigua en temps real",
// https://aetr.aca.gencat.cat/) carga para pintar aforos y embalses (referencia L8).
// Uso: node scripts/capture_reference_aca.js <dir_salida>
const { chromium } = require('playwright');
const fs = require('fs');
const path = require('path');
const UA = 'HidroRed-Research/0.1 (proyecto ciudadano hidrologia; verificacion de fuentes)';
const URL = 'https://aetr.aca.gencat.cat/';
(async () => {
  const outDir = process.argv[2];
  const launch = process.env.HTTPS_PROXY ? { proxy: { server: process.env.HTTPS_PROXY } } : {};
  const browser = await chromium.launch(launch);
  const ctx = await browser.newContext({ userAgent: UA, viewport: { width: 1500, height: 1000 } });
  const page = await ctx.newPage();
  const saved = [];
  const pending = [];
  page.on('response', r => {
    const u = r.url();
    if (!/api\.aetr\.aca\.gencat\.cat\/(timeline\/|catalog\/elements\/(aforaments|embassaments))/.test(u)) return;
    pending.push((async () => {
      const body = await r.text().catch(() => null);
      if (!body) return;
      let name;
      if (/catalog\/elements/.test(u)) name = 'catalog_' + u.match(/elements\/(\w+)/)[1] + '.json';
      else {
        const alias = (body.match(/"alias":"([^"]+)"/) || [])[1] || 'desconocido';
        if (!/^aca\.sensor\.(flow|level|capacity|volume|river)/.test(alias) && !/aca\.sensor\.(cabal|nivell)/.test(alias)) { saved.push('(omitido) ' + alias); return; }
        name = 'timeline_' + alias + '.json';
      }
      fs.writeFileSync(path.join(outDir, name), body);
      saved.push(name + ' ' + body.length);
    })());
  });
  await page.goto(URL, { waitUntil: 'networkidle', timeout: 90000 }).catch(e => console.log('goto', e.message.slice(0, 120)));
  await page.waitForTimeout(4000);
  await Promise.all(pending);
  const capturedAt = new Date().toISOString();
  await page.screenshot({ path: path.join(outDir, 'visor_aetr.png') });
  fs.writeFileSync(path.join(outDir, 'captura.json'), JSON.stringify({ source_url: URL, user_agent: UA, captured_at_utc: capturedAt, files: saved }, null, 1));
  console.log(capturedAt); saved.forEach(s => console.log(' ', s));
  await browser.close();
})().catch(e => { console.error('ERROR', e.message); process.exit(1); });
