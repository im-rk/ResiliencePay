# ResiliencePay

ResiliencePay is an AI revenue-recovery agent that acts as a dunning-management system for merchants. It leverages a contextual bandit (Thompson Sampling) to intelligently retry failed payments based on a closed taxonomy of failure causes, while ensuring all actions are bounded by an independently auditable, hardcoded compliance Gate that no learning system can override. 

## Architecture

```text
                    ┌─────────────────────────────────────────────────────┐
                    │                 EVENT SOURCE                        │
                    │  Synthetic generator  +  Razorpay test-mode webhooks│
                    └───────────────────────┬─────────────────────────────┘
                                             ▼
                    ┌─────────────────────────────────────────────────────┐
                    │  DIAGNOSE                                           │
                    │  Rule-based mapping of gateway error code → cause   │
                    │  + LLM fallback for ambiguous/free-text reasons     │
                    └───────────────────────┬─────────────────────────────┘
                                             ▼
                    ┌─────────────────────────────────────────────────────┐
                    │  DECIDE  (the novelty core)                         │
                    │  Contextual bandit (Thompson Sampling)              │
                    │  context → arm (intervention + timing)              │
                    └───────────────────────┬─────────────────────────────┘
                                             ▼
                    ┌─────────────────────────────────────────────────────┐
                    │  GATE  (stopping-rule / compliance engine)          │
                    │  max attempts, cool-off, opt-out/decline = terminal │
                    └───────────────────────┬─────────────────────────────┘
                                             ▼
                    ┌─────────────────────────────────────────────────────┐
                    │  ACT                                                │
                    │  Real: Razorpay test-mode retry / payment link      │
                    │  Simulated (labeled): nudge message via LLM         │
                    └───────────────────────┬─────────────────────────────┘
                                             ▼
                    ┌─────────────────────────────────────────────────────┐
                    │  OBSERVE                                            │
                    │  Outcome captured → reward computed → fed to bandit │
                    └───────────────────────┬─────────────────────────────┘
                                             ▼
                    ┌─────────────────────────────────────────────────────┐
                    │  AUDIT TRAIL (append-only log)                      │
                    │  event → diagnosis → decision → gate result →       │
                    │  action → outcome, all timestamped                  │
                    └───────────────────────┬─────────────────────────────┘
                                             ▼
                    ┌─────────────────────────────────────────────────────┐
                    │  DASHBOARD                                          │
                    │  live feed · metrics · learning curve · exceptions  │
                    └─────────────────────────────────────────────────────┘
```

## Setup & Run Instructions
1. `git clone` the repository.
2. `cp .env.example .env` and fill in API keys (`RAZORPAY_KEY_ID`, `RAZORPAY_KEY_SECRET`, `GEMINI_API_KEY`, Supabase, Upstash Redis).
3. Start the infrastructure: `docker-compose up -d`.
4. Run the API and Dashboard locally: `npm run dev` in `apps/dashboard` and `uvicorn apps.api.src.main:app --reload`.

## Reproducing Headline Metrics
We proved this works with a controlled experiment (comparing bandit vs. baseline on the same synthetic data).
Run the batch evaluation script:
```bash
python eval/run_batch.py
```
This runs exactly the same pipeline code without the web server, generating synthetic events, running the agent through the Gate, and plotting the learning curve.

## What is Real vs. Simulated
- **Real:**
  - The API, Database, Cache, Background Workers, and Dashboard.
  - Razorpay Test-mode Actions (e.g., Retries and Payment Link generation via the Razorpay test credentials).
  - LLM Message generation (via Gemini).
- **Simulated:**
  - Sending "nudge" messages (SMS/WhatsApp) is simulated by logging the LLM-generated message and tagging it explicitly as `simulated: true` in the audit log. Real messages are not dispatched.
  - The inbound webhook traffic is artificially generated via our synthetic generator, though it matches Razorpay's actual decline taxonomy.