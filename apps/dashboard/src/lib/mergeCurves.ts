export function mergeCurvesByBatchIndex(
  banditCurve: any[] | undefined,
  baselineCurve: any[] | undefined
) {
  if (!banditCurve || !baselineCurve) return [];
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
