'use client';

import { useState } from 'react';
import { formatThreshold } from '@/lib/metric-display';

export interface ThresholdRow {
  metric: string;
  /** Rounded FAIL bound from the engine's {Species}_metrics.csv — what downstream tools see. */
  rounded_lower: number | null;
  rounded_upper: number | null;
  /** Unrounded FAIL bound from summary.csv (engine's FINAL_LOWER / FINAL_UPPER). */
  raw_lower: number | null;
  raw_upper: number | null;
  /** Rounded WARN bound from the engine's {Species}_metrics.csv. */
  warn_lower: number | null;
  warn_upper: number | null;
  /** Unrounded WARN bound from summary.csv (engine's WARN_LOWER / WARN_UPPER). */
  raw_warn_lower: number | null;
  raw_warn_upper: number | null;
}

export interface ThresholdTableProps {
  rows: ThresholdRow[];
  summaryHasMy: boolean;
  metricsURL?: string;
  /** External (third-party) schemes ship published integer cutoffs and have no
   *  pre-rounding raw bound or WARN band — the mode toggle is meaningless. */
  hideModeToggle?: boolean;
}

export default function ThresholdTable({ rows, summaryHasMy, metricsURL, hideModeToggle }: ThresholdTableProps) {
  const [mode, setMode] = useState<'rounded' | 'raw'>('rounded');

  return (
    <>
      <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
        {!hideModeToggle && (
        <div className="inline-flex rounded-full border border-neutral-200 dark:border-neutral-700 bg-neutral-50 dark:bg-neutral-900 p-1">
          {(['rounded', 'raw'] as const).map((m) => (
            <button
              key={m}
              type="button"
              onClick={() => setMode(m)}
              aria-pressed={mode === m}
              className={[
                'px-4 py-1 text-xs font-medium rounded-full transition-colors',
                mode === m
                  ? 'bg-white dark:bg-neutral-800 text-neutral-900 dark:text-neutral-100 shadow-sm'
                  : 'text-neutral-600 dark:text-neutral-400 hover:text-neutral-900 dark:hover:text-neutral-100',
              ].join(' ')}
            >
              {m === 'rounded' ? 'Rounded (published)' : 'Raw (pre-rounding)'}
            </button>
          ))}
        </div>
        )}
        {!hideModeToggle && (
        <p className="text-[11px] text-neutral-500 dark:text-neutral-400">
          {mode === 'rounded'
            ? 'Both Fail and Warn bands shown as the published rounded values — easier to cite and consistent across the species page, CSV downloads, and downstream QC tools.'
            : 'Both Fail and Warn bands shown as the engine’s unrounded statistical bounds, exactly as derived from the reference distribution.'}
        </p>
        )}
      </div>

      {!hideModeToggle && !summaryHasMy && (
        <div className="mb-4 rounded border border-amber-300 dark:border-amber-700 bg-amber-50 dark:bg-amber-950/40 px-3 py-2 text-xs text-amber-800 dark:text-amber-200">
          Pre-rounding bounds are unavailable for this scheme. The published bounds remain available in the table and CSV download.
        </div>
      )}

      <div className="overflow-x-auto">
        <table className="min-w-full text-sm">
          <thead>
            <tr className="border-b border-neutral-200 dark:border-neutral-700">
              <th className="py-2 pr-4 text-left font-semibold">Metric</th>
              <th className="py-2 px-4 text-right font-semibold text-red-700 dark:text-red-300">Fail below</th>
              <th className="py-2 px-4 text-right font-semibold text-amber-700 dark:text-amber-300">Warn below</th>
              <th className="py-2 px-4 text-right font-semibold text-amber-700 dark:text-amber-300">Warn above</th>
              <th className="py-2 pl-4 text-right font-semibold text-red-700 dark:text-red-300">Fail above</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((row, i) => {
              const failLow = mode === 'rounded' ? row.rounded_lower : row.raw_lower;
              const failHigh = mode === 'rounded' ? row.rounded_upper : row.raw_upper;
              const warnLow = mode === 'rounded' ? row.warn_lower : row.raw_warn_lower;
              const warnHigh = mode === 'rounded' ? row.warn_upper : row.raw_warn_upper;
              return (
                <tr key={row.metric} className={i % 2 === 0 ? '' : 'bg-neutral-50 dark:bg-neutral-800/50'}>
                  <td className="py-2 pr-4 font-mono">{row.metric}</td>
                  <td className="py-2 px-4 text-right font-mono text-red-700 dark:text-red-300">{formatThreshold(failLow)}</td>
                  <td className="py-2 px-4 text-right font-mono text-amber-700 dark:text-amber-300">{formatThreshold(warnLow)}</td>
                  <td className="py-2 px-4 text-right font-mono text-amber-700 dark:text-amber-300">{formatThreshold(warnHigh)}</td>
                  <td className="py-2 pl-4 text-right font-mono text-red-700 dark:text-red-300">{formatThreshold(failHigh)}</td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>

      <p className="mt-3 text-xs text-neutral-500 dark:text-neutral-400">
        <strong>How to read this:</strong>{' '}
        {hideModeToggle ? (
          <>This scheme provides failure limits only. A value outside a published failure limit fails that criterion; blank warning columns mean that no separate warning band is defined.</>
        ) : (
          <>A value outside a failure limit fails QC. Within the failure limits, values beyond a warning limit are borderline and worth a manual look; values within the warning limits pass that criterion. A dash means that no bound is defined on that side.</>
        )}
      </p>

      {metricsURL && (
        <div className="mt-3 flex justify-end">
          <a href={metricsURL} className="btn btn-primary" download>
            Download CSV
          </a>
        </div>
      )}
    </>
  );
}
