import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import test from 'node:test';
import ts from 'typescript';

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
// Exercise the production helper on the Node 20 runtime used by CI.
const helperSource = fs.readFileSync(path.join(root, 'src/lib/metric-display.ts'), 'utf8');
const helperJavaScript = ts.transpileModule(helperSource, {
  compilerOptions: { module: ts.ModuleKind.ESNext, target: ts.ScriptTarget.ES2020 },
}).outputText;
const {
  formatThreshold,
  gcStdInPercentagePoints,
  gcValueInPercent,
  summaryNumber,
} = await import(`data:text/javascript;base64,${Buffer.from(helperJavaScript).toString('base64')}`);

test('published GC cutoffs retain their values rather than being widened', () => {
  assert.deepEqual(
    [38.68, 38.8, 39.17, 39.75].map(formatThreshold),
    ['38.68', '38.8', '39.17', '39.75'],
  );
  const api = JSON.parse(fs.readFileSync(path.join(root, 'public/api/v2/thresholds.json'), 'utf8'));
  let checked = 0;
  for (const species of Object.values(api.species)) {
    for (const scheme of Object.values(species.schemes)) {
      const row = scheme.thresholds.find((r) => r.metric === 'GC_Content');
      if (!row) continue;
      for (const key of ['final_lower', 'warn_lower', 'warn_upper', 'final_upper']) {
        if (row[key] == null) continue;
        assert.equal(Number(formatThreshold(row[key]).replaceAll(',', '')), row[key], key);
        checked++;
      }
    }
  }
  assert.ok(checked > 1200, `Only ${checked} GC bounds checked`);
});

test('a fractional GC distribution scales its SD into percentage points', () => {
  // Regression values from the N. meningitidis v1.1 fractional summary.
  const centre = 0.517249;
  const std = 0.0017008859868293145;
  assert.equal(gcValueInPercent('GC_Content', centre), centre * 100);
  assert.equal(gcStdInPercentagePoints('GC_Content', std, centre), std * 100);
  assert.equal(gcStdInPercentagePoints('GC_Content', std, centre).toFixed(2), '0.17');
});

test('a small SD already expressed in percentage points is not multiplied', () => {
  assert.equal(gcStdInPercentagePoints('GC_Content', 0.0017, 51.72), 0.0017);
  assert.equal(gcStdInPercentagePoints('GC_Content', 0.17, 51.72), 0.17);
  assert.equal(gcStdInPercentagePoints('Genome_Size', 12000, 2100000), 12000);
  assert.equal(gcValueInPercent('GC_Content', 51.72), 51.72);
  // Mixed historical bound units still normalise independently of summary units.
  assert.equal(gcValueInPercent('GC_Content', 0.5172), 51.72);
});

test('one-sided missing bounds stay missing and are distinct from a true zero', () => {
  assert.equal(formatThreshold(null), '-');
  assert.equal(formatThreshold(undefined), '-');
  assert.equal(formatThreshold(NaN), '-');
  assert.equal(formatThreshold(0), '0');
  assert.ok(Number.isNaN(summaryNumber('')));
  assert.ok(Number.isNaN(summaryNumber('  ')));
  assert.ok(Number.isNaN(summaryNumber(undefined)));
  assert.equal(summaryNumber('0'), 0);
});
