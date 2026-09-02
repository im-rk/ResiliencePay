# SOLUTION.md — ResiliencePay: Complete Solution Architecture

**This is the master document.** Every other file in `docs/` provides depth on one piece of what's described here. Read this first to understand the whole; go deeper into `docs/phases/*_DETAILED.md` for implementation specifics on any one part.

---

## 1. The Problem, Stated Precisely

Razorpay's Track 03 brief: build an agent that detects revenue at risk, determines the right intervention, and executes a bounded recovery workflow — closing the loop from payment failures and checkout abandonment to overdue receivables, with measured money recovered, compliant escalation, stopping rules, and an audit trail.

Stripped of hackathon language, this is a **dunning-management system** — the same problem Stripe Billing's Smart Retries, Recurly, Chargebee Retain, and Butter Payments exist to solve commercially. That identification matters: it means the correct architecture already exists in the industry, and the job is to build it correctly, not invent something novel for its own sake.

---

## 2. The Solution in Brief

ResiliencePay is an end-to-end, production-grade revenue recovery engine. It operates through a continuous, closed loop:
1. **Ingest & Diagnose:** Captures failed-payment events and classifies the root cause against a standardized taxonomy (with a generative LLM fallback for unknown errors).
2. **Decide:** Selects the optimal recovery action using a contextual bandit (Thompson Sampling) that continuously learns and improves from real observed outcomes.
   * **Explicit Context Features Evaluated:**
     * **Transaction amount tier:** Micro (<₹500), Standard (₹500–₹5,000), High (>₹5,000).
     * **Time-of-day / Day-of-week buckets:** Specifically avoiding Indian core banking maintenance windows between 11:30 PM and 1:30 AM IST.
     * **Payment instrument:** UPI Autopay, e-Mandate, Debit Card, Credit Card.
3. **Gate (Compliance):** Passes the chosen action through an independent, deterministic compliance gate that no learning system can override.
4. **Act & Observe:** Executes the action idempotently (a real Razorpay test-mode API call or a simulated customer nudge), observes the financial outcome, feeds the reward back to the bandit, and records every step in an immutable, DB-enforced audit log.

The entire pipeline is proven through controlled experiments against a naive baseline and designed to degrade gracefully under injected real-world failures.

---

## 3. Why this is the *Correct* Architecture

A senior engineer's first job on a problem like this is to correctly classify which parts of the problem are genuinely open-ended and which parts are closed, standardized, and must remain deterministic. Get this wrong, and the system fails predictably:

- **Treat a closed problem as open** (e.g., let an LLM decide compliance rules) → The system becomes unauditable and illegally unpredictable.
- **Treat an open problem as closed** (e.g., hardcode "always retry in 3 days") → The system can never learn or improve beyond the engineer's initial guess.

The architecture is built strictly around getting this classification right:

| Problem Area | Genuinely Open-Ended? | Architectural Answer | Why |
|---|---|---|---|
| **Payment Decline Reasons** | **No** — standardized by card networks | Lookup table (`cause_categories`) | Matches real-world payment processors; auditable and stable. |
| **Recovery Action Space** | **No** — bounded by product definition | Lookup table (`arms`) | The *menu* of actions is fixed by product design, not learned. |
| **Context-to-Action Mapping** | **Yes** — varies empirically | Contextual Bandit (Thompson Sampling) | The one place the system *must* adapt based on real outcomes. |
| **Ambiguous Failure Text** | **Yes** — gateway messages evolve | LLM Fallback Classifier | Genuinely needs semantic understanding; strictly kept as a fallback. |
| **Customer-Facing Copy** | **Yes** — requires natural language | LLM-Generated Nudges | The only end-to-end LLM generative task, scoped with template fallbacks. |
| **Compliance Rules** | **No** — legally fixed | Deterministic `Gate` Layer | Architecturally unable to accept a probabilistic score. Must never fail. |

---

## 4. High-Level Architecture

```text
                    EVENT SOURCE
        Synthetic generator + Razorpay test-mode webhooks
                          |
                          v
                    DIAGNOSE
      Closed-taxonomy lookup (primary, deterministic)
      + LLM fallback (only on taxonomy miss)
                          |
                          v
        DECIDE  — the one genuinely learned component
      Contextual bandit (Thompson Sampling)
      Never sees compliance state; only picks an arm
                          |
                          v
      GATE  — deterministic, independent, non-negotiable
      evaluate_gate() cannot accept a confidence score
      as input — architecturally, not just by convention
                          |
                          v
              ACT  — idempotent, fault-injectable
      Real: Razorpay test-mode call | Simulated: nudge
                          |
                          v
      OBSERVE — webhook-driven + reconciliation fallback
      Outcome -> reward -> fed back into the bandit
                          |
                          v
      AUDIT LOG — append-only, DB-permission-enforced
```

`services/` (Diagnose, Decide, Gate, Act, Observe, Audit) contains zero web-framework or task-queue dependencies. Every module is independently testable and callable identically from a live API request, a Celery task, or an offline batch script.

---

## 5. "Works for all cases, nothing hardcoded" — Explained

### 5.1 What genuinely adapts at runtime

- **The bandit's policy:** Expected values for every arm and context bucket are live statistical estimates (alpha, beta) updated from real rewards. New contexts fall back to an *informed prior* lazily materialized on first access, never a crash.
- **Failure classification for unmapped inputs:** Unknown gateway errors trigger an LLM classifier constrained to the valid taxonomy. It degrades gracefully to `unknown` if the LLM fails.
- **Customer-facing message content:** Generated per-event by an LLM, with static template fallbacks only as a last-resort safety net.
- **Recovery timing under real-world drift:** Compliance status is re-evaluated fresh at execution time against the current state, preventing illegal actions if a user opts out after a task is scheduled.

### 5.2 What is deliberately fixed (and why it's correct)

- **The decline-code taxonomy itself:** Fixed because card networks publish a closed, standardized set of decline reasons.
- **The recovery action menu:** Fixed because it's a product decision. The bandit chooses *among* them, it doesn't invent new ones.
- **Compliance rules:** Fixed and deterministic. This is the one place where "dynamic" would be a catastrophic legal bug.

---

## 6. How the Solution is Proven (Not Just Asserted)

1. **A Real Postgres 16 Database:** All 16 tables mapped via Alembic migrations.
2. **Audit-Log Immutability:** Enforced at the database level. Postgres rejects `UPDATE`/`DELETE` for the application role with `permission denied`.
3. **Controlled Experimentation:** Phase 8's batch harness runs the bandit and a naive baseline through identical synthetic data, proving lift across multiple random seeds.
4. **Adversarial Testing:** `test_high_confidence_bandit_choice_still_blocked_at_max_attempts` proves that a confident bandit choice past the retry limit is strictly blocked by the Gate.
5. **Chaos Testing Suite:** Proves graceful degradation under real failure conditions, injecting actual exception types indistinguishable from genuine network failures.
6. **Full-Loop Razorpay Integration:** Successfully integrated live webhooks and test-mode API calls, validating end-to-end financial state reconciliation.

---

## 7. Production Engineering Practices Applied

- **DTO/Mapper Boundaries:** ORM models never serialize directly.
- **Enforced Layer Separation:** `services/*` cannot import from `apps/*`, checked in CI.
- **Strict Idempotency:** Any money-affecting external call is safe to retry.
- **Least-Privilege DB Roles:** The application role cannot `DROP`, `TRUNCATE`, `ALTER`, or `DELETE` financial records.
- **Correlation IDs:** Traceable history across API requests, downstream services, and Celery tasks.
- **Integer Currency:** Money is always strictly represented as integer `paise`, never floats.

---

## 8. Component-by-Component Rationale

| Component | What it does | Why built this way | Full detail |
|---|---|---|---|
| **Diagnose** | Classifies failure cause | Rules-first (free, instant, auditable), LLM fallback only on miss | `PHASE_03_diagnose.md` |
| **Decide** | Chooses a recovery action | Thompson Sampling bandit — the one place learning belongs | `PHASE_05_decide_DETAILED.md` |
| **Gate** | Enforces compliance | Deterministic, architecturally isolated from Decide | `PHASE_04_gate_DETAILED.md` |
| **Act** | Executes the chosen action | Idempotent, fault-injectable, real/simulated boundary structurally explicit | `PHASE_06_act_DETAILED.md` |
| **Observe** | Captures outcomes, feeds reward back | Webhook-driven + reconciliation fallback; identical reward logic in live and batch mode | `PHASE_07_observe_DETAILED.md` |
| **Audit** | Records every step | Append-only, DB-permission-enforced immutability | `PHASE_09_api_audit_DETAILED.md` |
| **Batch Eval** | Proves the system works | Controlled experiment: same code, same data, one variable | `PHASE_08_batch_eval_DETAILED.md` |
| **Chaos** | Proves graceful degradation | Fault injection indistinguishable from real failure | `PHASE_11_resilience_chaos_DETAILED.md` |
| **Dashboard** | Makes evidence legible | Explicit loading/error/empty states throughout | `PHASE_10_dashboard_DETAILED.md` |

---

## 9. What Makes This a Winning Solution

Most competing submissions will solve this problem by pointing an LLM at the entire decision (fast to build, impressive in a demo, but unauditable, non-reproducible, and unprovable). A smaller number will hardcode a rule table (auditable, but static and never improves). 

This solution correctly separates the two: **a closed, auditable taxonomy for what's genuinely fixed in the real world, a learned policy for what's genuinely open, and a compliance layer that neither can touch.** This is the exact architecture professional dunning platforms use, built with the depth of adversarial and chaos testing that proves it works reliably at scale.

---

## 10. Current State: 100% Complete and Production-Ready

The system is fully implemented and verified against real infrastructure. As of this writing:
- **All 12 Phases are complete.** The core architecture, data layer, contextual bandit, compliance gate, fault injection, and Razorpay integrations are live.
- **Test coverage is exhaustive**, including adversarial compliance tests, concurrency stress tests, and automated chaos testing. 
- **Documentation is at parity with code.** Everything described in the `docs/phases/*_DETAILED.md` files has been successfully deployed and rigorously tested. 

See `CURRENT_STATUS_AND_NEXT_STEPS.md` for the detailed deployment record and final verification results.
