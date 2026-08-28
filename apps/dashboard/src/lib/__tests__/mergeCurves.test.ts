import { expect, test } from "vitest";
import { mergeCurvesByBatchIndex } from "../mergeCurves";

test("aligns series of mismatched length without crashing", () => {
  const bandit = [
    { batch_index: 0, recovery_rate: 0.2 },
    { batch_index: 1, recovery_rate: 0.5 },
    { batch_index: 2, recovery_rate: 0.7 }
  ];
  const baseline = [
    { batch_index: 0, recovery_rate: 0.2 },
    { batch_index: 1, recovery_rate: 0.22 }
  ];
  const merged = mergeCurvesByBatchIndex(bandit, baseline);
  expect(merged).toHaveLength(2); // aligned to the shorter series
  expect(merged[1]).toMatchObject({ banditRate: 0.5, baselineRate: 0.22 });
});
