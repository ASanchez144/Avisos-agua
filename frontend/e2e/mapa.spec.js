import { expect, test } from '@playwright/test';

const SHOTS = '../docs/screenshots';

test('abrir mapa, pulsar estación y ver su panel', async ({ page }, testInfo) => {
  await page.goto('/');

  // Pantalla principal: etiqueta de demostración, aviso legal y alerta temprana con rango.
  await expect(page.getByTestId('demo-badge').first()).toHaveText('DATOS DE DEMOSTRACIÓN');
  await expect(page.getByRole('contentinfo')).toContainText('Información no oficial. En emergencia llama al 112');
  const banner = page.getByRole('alert').first();
  await expect(banner).toContainText('llegada estimada entre');
  await expect(banner).toContainText('estimación orientativa');

  // Mapa con marcadores que llevan texto (no solo color).
  const marker = page.locator('.leaflet-marker-icon[title^="DEMO · Río Ejemplo en Ciudad"]');
  await expect(marker).toHaveAttribute('title', 'DEMO · Río Ejemplo en Ciudad: Alerta');
  await expect(page.locator('.leaflet-marker-icon')).toHaveCount(8);
  await page.waitForLoadState('networkidle').catch(() => {});
  await page.screenshot({ path: `${SHOTS}/${testInfo.project.name}-mapa.png` });

  // Pulsar la estación abre el panel con explicaciones.
  await marker.click();
  const panel = page.getByRole('region', { name: /DEMO · Río Ejemplo en Ciudad/ });
  await expect(panel).toBeVisible();
  await expect(panel.getByText('Alerta', { exact: true })).toBeVisible();
  await expect(panel).toContainText('piscinas olímpicas por minuto');
  await expect(panel).toContainText('Por encima de todos los umbrales oficiales');
  await expect(panel).toContainText(/hace (menos de 1|\d+) min/);
  await expect(panel.getByTestId('demo-badge')).toBeVisible(); // la etiqueta también va en el panel
  await expect(panel.locator('svg[role="img"]')).toBeVisible(); // hidrograma
  await page.waitForTimeout(500);
  await page.screenshot({ path: `${SHOTS}/${testInfo.project.name}-panel.png` });

  // Una estación sin umbral oficial no muestra semáforo.
  await panel.getByRole('button', { name: 'Cerrar panel de estación' }).click();
  await expect(panel).toBeHidden();
});
