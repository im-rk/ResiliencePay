# PRE_SUBMISSION_CHECKLIST.md — Final Verification Before You Submit

Run through this the way a release engineer at a fintech company would
before shipping to production — methodically, in order, not skimming.
Check each box only after actually verifying it, not because it "should"
be true. Where a check requires running something, run it now, don't
assume yesterday's result still holds.

---

## 1. Environment & infrastructure sanity

- [ ] `git clone` into a genuinely fresh directory (or ask a teammate to),
      copy `.env.example` to `.env`, fill in real keys, and confirm the
      entire stack starts with zero undocumented manual steps.
- [ ] Confirm Supabase Postgres, Upstash Redis, Razorpay test-mode, and
      your LLM provider are all reachable **right now** — API keys expire,
      free-tier services sleep, and "it worked yesterday" is not evidence
      it works today.
- [ ] Confirm your `.env` is in `.gitignore` and was never committed —
      run `git log --all --full-history -- .env` and confirm it returns nothing.
- [ ] Confirm no API key, secret, or credential appears in any committed
      file — grep your full history for the literal key prefixes
      (`rzp_test_`, `sk-ant-`, your Supabase/Upstash tokens) across all
      branches, not just the current one.

## 2. Data integrity — verify against the live database, not memory

- [ ] Run a fresh batch (`python -m eval.run_batch` or equivalent) and
      confirm the row counts make sense: N events in → N audit_log rows
      out. If any events are unaccounted for, that's a gap to find now,
      not during judging.
- [ ] Query `cause_categories` and `arms` directly — confirm both are
      still fully seeded, not accidentally truncated by an earlier test run.
- [ ] Query the Redis bandit state directly — confirm alpha/beta values
      are not all still at their default `(1.0, 1.0)` prior (if they are,
      your batch run never actually updated the bandit — a real bug worth
      catching now).
- [ ] Re-run the audit-log immutability test **right now, against your
      real Supabase instance**, not just against a local Postgres from
      earlier testing — connect as the app-inheriting role and confirm
      `UPDATE`/`DELETE` are still rejected. Supabase's role/permission
      setup can differ subtly from a local instance; verify it directly.
- [ ] Confirm every `amount`/`amount_recovered` field in a spot-check
      query is a sane integer paise value — no negative numbers, no
      absurdly large numbers, no floats.

## 3. The headline number — reproduce it live, don't trust a screenshot

- [ ] Re-run your baseline-vs-bandit batch comparison **right now** and
      confirm the lift number you plan to present still holds. If it's
      drifted meaningfully from what you remember, find out why before
      presenting a stale number.
- [ ] Run it a second time with a different seed. If the direction of the
      lift flips or collapses to near-zero, do not present a single
      favorable run as your headline number — investigate (per
      `PHASE_05_decide_DETAILED.md` section 3.2's tuning guidance) before submission.
- [ ] Confirm the SQL cross-check query (`eval/metrics_queries.sql`)
      independently reproduces the same recovery rate your Python harness
      reports — a mismatch here means one of the two is wrong, and you
      want to know which before a judge finds the discrepancy.
- [ ] Confirm your exception count is genuinely non-zero and the
      exception list shows real, explainable entries — a suspiciously
      perfect 100% recovery rate is a red flag to fix, not a result to celebrate.

## 4. The compliance guarantee — prove it, don't just claim it

- [ ] Run `test_high_confidence_bandit_choice_still_blocked_at_max_attempts`
      directly and read the actual output — confirm it passes for real,
      right now, against your current code.
- [ ] Manually construct one test case where a customer has opted out AND
      hit max attempts, and confirm the audit trail correctly reports
      `customer_opted_out` (not `max_attempts_exceeded`) as the blocking
      reason, per the priority ordering in `PHASE_04_gate_DETAILED.md`.
- [ ] Confirm `evaluate_gate()`'s actual function signature in your
      current code has no parameter through which a confidence score
      could be passed — read the real code, don't rely on memory of the spec.

## 5. Security — verify these are real, not aspirational

- [ ] If you implemented webhook signature verification
      (`ADVANCED_06_webhook_security_and_idempotency.md`): send a request
      with a deliberately wrong signature and confirm it's actually
      rejected with a 401 right now.
- [ ] Confirm your admin/fault-injection endpoint (if built) rejects a
      request with no secret header and rejects one with a wrong secret —
      test both, not just one.
- [ ] Grep your logs from a recent run for your actual secret values —
      confirm none appear, even truncated or partially masked incorrectly.
- [ ] Confirm your database role permissions match what you intend —
      query `\dp audit_log` (or Supabase's permissions UI) directly and
      confirm `UPDATE`/`DELETE` are genuinely absent for your app role.

## 6. Resilience — trigger it live, don't just point at a passing test

- [ ] Actually enable fault injection and run one event through the
      pipeline. Confirm the dashboard shows the failure clearly, the
      audit trail has no gap, and no episode's `attempt_count` was
      consumed by a systemically-doomed attempt (if you built the circuit
      breaker from `ADVANCED_05`).
- [ ] Time this live-trigger sequence, start to finish. If it takes more
      than ~45 seconds, simplify it — dead air during a demo is costly.
- [ ] Turn fault injection back off afterward and confirm a subsequent
      run shows zero injected failures — a chaos toggle stuck "on" would
      quietly sabotage your main demo run.

## 7. Dashboard — check every panel's failure states, not just the happy path

- [ ] Load the dashboard with zero batch runs yet executed — confirm
      every panel shows a sensible loading/empty state, not a blank
      screen or a JavaScript error in the console.
- [ ] Open your browser's dev console while using the dashboard normally
      — confirm there are no red errors, even ones that don't visibly
      break the UI.
- [ ] Confirm the "Simulated" vs "Real" labeling in the audit trail table
      is visually obvious at a glance, not something you have to explain
      is technically there.
- [ ] Confirm the exception list and learning-curve chart both render
      correctly on the actual screen resolution/aspect ratio you'll be
      presenting on, not just your primary dev monitor.

## 8. Code quality — a judge or recruiter may actually open your repo

- [ ] Run your full linter/type-checker (`ruff`, `mypy`) fresh, right
      now, and fix anything currently failing — don't submit with a red CI badge.
- [ ] Run your full test suite fresh and confirm the pass count matches
      what you expect — a silently-skipped test is worse than a known
      failing one.
- [ ] Skim `services/gate/service.py`, `services/decide/bandit.py`, and
      `services/act/service.py` specifically — these are your three
      strongest architectural claims; make sure the actual code still
      matches what you'll say about it out loud.
- [ ] Confirm there's no leftover debug code (`print()` statements,
      hardcoded test values, commented-out blocks) in these core files.
- [ ] Confirm your `README.md` at the repo root actually reflects the
      current state — run its documented setup steps literally, as
      written, and fix anything that's drifted.

## 9. Documentation-to-code honesty check

- [ ] Open `CURRENT_STATUS_AND_NEXT_STEPS.md` and update it to reflect
      what's genuinely true right now — don't submit with a status doc
      claiming something isn't built when it actually is (undersells you)
      or claiming something works when it's flaky (a judge who finds the
      gap will trust nothing else in your docs afterward).
- [ ] If any phase doc's described design diverged from what you actually
      built, note the correction in that doc — an honest "we changed X
      because Y" note reads better than silent drift a judge discovers themselves.

## 10. Demo rehearsal — the actual dry run, not a mental walkthrough

- [ ] Run the full `DEMO_SCRIPT.md` sequence out loud, on the actual
      machine and network you'll present from, at least twice.
- [ ] Have one teammate deliberately try to break something during
      rehearsal (kill the network mid-call, close the wrong tab, etc.)
      and confirm your fallback plan (cached `eval/results/` data) is
      actually ready to swap in, not just described in a doc.
- [ ] Confirm every team member can answer at least three questions from
      `JUDGE_QA_PREP.md` without reading from the document.
- [ ] Time the full demo end to end — confirm it fits the actual time
      slot with margin, not exactly at the limit.

## 11. Submission logistics

- [ ] Confirm the repository is set to the correct visibility (public, or
      shared with the specific judges/reviewers as required).
- [ ] Confirm the submission form's repo link resolves correctly when
      opened in a fresh, logged-out browser session — a private-looking
      404 to a judge is unrecoverable once the deadline passes.
- [ ] Double-check the exact submission deadline and timezone — submit
      with buffer, not at the literal last minute.
- [ ] Confirm any required demo video (if applicable) is uploaded,
      playable, and under any stated length/size limit.

---

## The one question to ask yourself before hitting submit

**If a judge opened this repo cold, with no context, and read only the
code in `services/gate/`, `services/decide/`, and `services/act/`, plus
one batch run's output — would they independently arrive at the same
conclusion your demo narrative claims?** If yes, submit. If you're not
sure, that's the specific gap to close in whatever time remains — not a
new feature, a verification of what already exists.
