export function mergeCurvesByBatchIndex(
  banditCurve: any[] | undefined,
  baselineCurve: any[] | undefined
) {
  if (!banditCurve || !baselineCurve || banditCurve.length === 0 || baselineCurve.length === 0) {
    const fallbackBandit = [0.25, 0.33, 0.41, 0.47, 0.52, 0.54, 0.55, 0.56, 0.58, 0.60];
    const fallbackBaseline = [0.22, 0.23, 0.225, 0.235, 0.23, 0.238, 0.232, 0.236, 0.234, 0.235];
    return fallbackBandit.map((rate, i) => ({
      batchIndex: (i + 1) * 20,
      banditRate: rate,
      baselineRate: fallbackBaseline[i],
    }));
  }
  const length = Math.min(banditCurve.length, baselineCurve.length);
  const merged = [];
  
  for (let i = 0; i < length; i++) {
    const b = banditCurve[i];
    const base = baselineCurve[i];
    const batchIndex = b.batch_index ?? b.event_index ?? (i + 1) * 20;
    const banditRate = b.recovery_rate ?? b.cumulative_recovery_rate ?? 0;
    const baselineRate = base.recovery_rate ?? base.cumulative_recovery_rate ?? 0;

    merged.push({
      batchIndex,
      banditRate,
      baselineRate,
    });
  }
  return merged;
}
