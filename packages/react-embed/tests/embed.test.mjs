import test from 'node:test';
import assert from 'node:assert/strict';
import { buildEmbedUrl } from '../dist/index.js';

test('buildEmbedUrl constructs correct URL with path and parameters', () => {
  const url = buildEmbedUrl({
    targetUrl: 'https://gateway.metastatistic.com/',
    embedType: 'dashboard',
    resourceId: 'dash_hospital_kpi_1',
    tenantId: 'clinic_south',
    token: 'jwt_abc_123',
    theme: 'dark',
    filters: { site: 'NYC', year: 2026 },
  });

  assert.match(url, /^https:\/\/gateway\.metastatistic\.com\/embed\/dashboard\/dash_hospital_kpi_1\?/);
  assert.ok(url.includes('tenant=clinic_south'));
  assert.ok(url.includes('token=jwt_abc_123'));
  assert.ok(url.includes('theme=dark'));
  assert.ok(url.includes('filters=%7B%22site%22%3A%22NYC%22%2C%22year%22%3A2026%7D'));
});

test('buildEmbedUrl works with minimal parameters', () => {
  const url = buildEmbedUrl({
    targetUrl: 'http://localhost:8080',
    embedType: 'report',
    resourceId: 'rep_summary_42',
  });

  assert.equal(url, 'http://localhost:8080/embed/report/rep_summary_42');
});

test('buildEmbedUrl encodes special characters in resourceId', () => {
  const url = buildEmbedUrl({
    targetUrl: 'http://localhost:8080',
    embedType: 'apa_table',
    resourceId: 'table/special&id',
  });

  assert.equal(url, 'http://localhost:8080/embed/apa_table/table%2Fspecial%26id');
});
