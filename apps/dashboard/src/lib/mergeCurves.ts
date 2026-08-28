export function mergeCurvesByBatchIndex(
  banditCurve: { batch_index: number; recovery_rate: number }[],
  baselineCurve: { batch_index: number; recovery_rate: number }[]
) {
  // We want to align series of mismatched length without crashing.
  // Take the shortest length to align.
  const length = Math.min(banditCurve.length, baselineCurve.length);
  const merged = [];
  
  for (let i = 0; i < length; i++) {
    merged.push({
      batchIndex: banditCurve[i].batch_index,
      banditRate: banditCurve[i].recovery_rate,
      baselineRate: baselineCurve[i].recovery_rate,
    });
  }
  return merged;
}
