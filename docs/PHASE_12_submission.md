# Phase 12 — Rehearsal, Documentation Parity & Submission

**Depends on:** every prior phase
**Unblocks:** submission
**Owner:** whole team
**Estimated time:** ~1-1.5 days

## Objective
Ensure the delivered artifact (repo + live demo) matches the documented
design exactly, and that the team can defend every claim under judge
questioning without hesitation.

## Scope
**In scope:** documentation-parity pass, clean-machine setup verification,
full demo rehearsal (including the Phase 11 chaos beat), submission logistics.
**Out of scope:** any new features — this phase is about polish and proof,
not scope expansion. If you're tempted to add something new here, don't.

## Detailed task breakdown

1. **Documentation parity pass** — go through every file in `docs/`
   (`PRD.md`, `ARCHITECTURE.md`, `DATABASE_DESIGN.md`, `ML_DESIGN.md`, etc.)
   and update anything that diverged from what was actually built. A PRD
   that doesn't match the product is worse than no PRD — it signals you
   didn't track your own decisions.

2. **Clean-machine setup test** — on a genuinely fresh clone (a teammate's
   untouched machine, or a fresh VM/codespace), time `git clone` →
   `cp .env.example .env` → `docker-compose up` to a fully healthy system.
   Target: under 5 minutes. If it's not, fix the setup friction now, not
   during judging.

3. **README finalization** — top-level `README.md` must have: one-paragraph
   problem statement, an architecture diagram (can be the ASCII one from
   `ARCHITECTURE.md`), exact run instructions, exact instructions to
   reproduce the headline metrics (`eval/run_batch.py` invocation), and an
   explicit "what's real Razorpay API vs. what's simulated" section — don't
   make a judge dig through code to figure this out.

4. **Full demo rehearsal** — run `DEMO_SCRIPT.md` end to end, live, at
   least 3 times as a full team, timed to fit the 4-minute window,
   including:
   - The live single-event walkthrough (Phase 6/7's real pipeline).
   - The batch results reveal (Phase 8's cached + live-reproducible numbers).
   - The learning curve (Phase 5/10).
   - The graceful-failure / opt-out walkthrough (Phase 4).
   - The live chaos-injection beat (Phase 11) — this is your differentiator, don't cut it for time; cut something else instead.

5. **Fallback rehearsal** — deliberately kill your Razorpay test-mode
   connectivity or your LLM API key mid-run once, and rehearse the
   composed, honest response: *"We'll fall back to this morning's cached
   run — same pipeline, same code, just not re-triggering the live API
   right now."* Practice saying this calmly; it reads far better than a
   flustered recovery attempt.

6. **Q&A prep** — assign 1-2 people to be ready specifically for questions
   about:
   - The bandit design (why Thompson Sampling, why bucketed context, how
     convergence was verified).
   - The Gate/compliance separation (why it's architecturally independent
     of the learning system).
   - Data realism (how the synthetic dataset was constructed, and why the
     exception list is non-zero on purpose).
   - The chaos-testing result, and being able to trigger it live if asked.

7. **Submit** — via the buildathon form (https://forms.gle/d9r2gvxp8cmoZhon9),
   with: repo link, a short written summary (pull directly from `PRD.md`
   §1-2 and `TESTING_METRICS.md` §7's results table — don't rewrite from
   scratch), and a demo video/link if required by the form.

## Definition of Done (final submission checklist)

- [ ] Full pipeline runs end-to-end on a live-triggered event.
- [ ] Batch evaluation numbers are reproducible from a documented seed (multi-seed variance reported, not a single lucky run).
- [ ] Dashboard shows: live feed, metrics table, learning curve, exception list, audit trail — all five panels, all wired to real data.
- [ ] Every simulated action is visibly labeled as simulated, in both the audit trail and the dashboard.
- [ ] At least one explicit "graceful failure / stopping rule respected" case is demonstrable on request.
- [ ] The chaos-injection beat is rehearsed and can be triggered live.
- [ ] All doc files in `docs/` are up to date with what was actually built.
- [ ] Clean-machine `docker-compose up` verified under 5 minutes.
- [ ] Team has rehearsed the full demo at least 3 times, timed.
- [ ] Submission form completed with repo link, summary, and demo video/link.

## The one sentence to have ready when a judge asks "what's the most interesting engineering decision you made"

*"We separated the learning system from the compliance system
architecturally, not just logically — the bandit physically cannot execute
a money-moving action without passing through an independently-tested,
rule-based gate — and we proved the whole pipeline degrades gracefully
under injected failure, live, on demand."*
