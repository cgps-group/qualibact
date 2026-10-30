/** Keep the published numeric value; adding directional rounding changes a QC cutoff. */
export function formatThreshold(value: number | null | undefined): string {
  if (value === null || value === undefined || !Number.isFinite(value)) return '-';
  return value.toLocaleString('en', {
    maximumFractionDigits: Math.abs(value) >= 1000 ? 0 : 4,
  });
}

/** Empty CSV cells are missing values, not zero. */
export function summaryNumber(value: string | undefined): number {
  return value === undefined || value.trim() === '' ? NaN : Number(value);
}

export function gcValueInPercent(metric: string, value: number): number {
  return metric === 'GC_Content' && Number.isFinite(value) && Math.abs(value) <= 1.5
    ? value * 100
    : value;
}

/** SD has the unit of the source distribution, determined from its unconverted centre. */
export function gcStdInPercentagePoints(metric: string, std: number, sourceCentre: number): number {
  return metric === 'GC_Content' && Number.isFinite(sourceCentre) && Math.abs(sourceCentre) <= 1.5
    ? std * 100
    : std;
}
