# Phase Implementation Files — Index

Each file below is a standalone, production-grade implementation ticket for
one phase of the pipeline. Every file follows the same structure: Objective
→ Scope → Deliverables (mapped to exact `MONOREPO_STRUCTURE.md` paths) →
Detailed task breakdown → Edge-case matrix → Design decisions & trade-offs →
Test plan → Definition of Done → Handoff to the next phase.

Read `../PHASE_IMPLEMENTATION_PLAN.md` first for the full narrative version
with deeper pseudocode; use these files as the actual day-to-day tickets
your team works from.

| Phase | File | Depends on | Estimated time |
|---|---|---|---|
| 0 | [PHASE_00_foundations.md](./PHASE_00_foundations.md) | — | ~2-3 hrs |
| 1 | [PHASE_01_data_layer.md](./PHASE_01_data_layer.md) | 0 | ~1 day |
| 2 | [PHASE_02_synthetic_data.md](./PHASE_02_synthetic_data.md) | 1 | ~0.5-1 day |
| 3 | [PHASE_03_diagnose.md](./PHASE_03_diagnose.md) | 1, 2 | ~1 day |
| 4 | [PHASE_04_gate.md](./PHASE_04_gate.md) | 1 | ~1 day |
| 5 | [PHASE_05_decide.md](./PHASE_05_decide.md) | 3, 4 | ~1-1.5 days |
| 6 | [PHASE_06_act.md](./PHASE_06_act.md) | 4, 5 | ~1-1.5 days |
| 7 | [PHASE_07_observe.md](./PHASE_07_observe.md) | 5, 6 | ~1 day |
| 8 | [PHASE_08_batch_eval.md](./PHASE_08_batch_eval.md) | 2-7 | ~1 day |
| 9 | [PHASE_09_api_audit.md](./PHASE_09_api_audit.md) | 1-8 | ~1 day |
| 10 | [PHASE_10_dashboard.md](./PHASE_10_dashboard.md) | 9 | ~1.5-2 days |
| 11 | [PHASE_11_resilience_chaos.md](./PHASE_11_resilience_chaos.md) | 6, 10 | ~1 day |
| 12 | [PHASE_12_submission.md](./PHASE_12_submission.md) | all | ~1-1.5 days |

## Suggested parallelization (4-person team)

Phases 5 and 6 can run in parallel once Phase 4 is done. Phase 8 needs
Phase 5's `BanditPolicy` Protocol satisfied by both the bandit and the
baseline, so don't start Phase 8 until Phase 5's interface is locked, even
if the bandit's internals are still being refined.

```
Day:     1    2    3    4    5    6    7    8    9    10
Person A: [--0--][----1----][--2--]              [------8------]
Person B:                    [----3----][----4----]
Person C:                              [----5----][----6----]
Person D:                                                    [--7--][--9--][------10------]
Whole team:                                                                        [--11--][--12--]
```
Adjust to your actual headcount and skill distribution — the dependency
graph in the table above is the real constraint, not this specific timeline.
