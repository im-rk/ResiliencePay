# ResiliencePay: 5-Minute Demo Script

**Target Length:** 4.5 minutes. 
**Objective:** Prove operational rigor, not just flashy AI. Show the judges how the system survives high-concurrency, distributed systems anomalies live on stage.

---

## 0. The Hook (30s)
*Speaker stands on stage. Dashboard is visible on the screen, showing the baseline vs. agent lift.*

"Most AI hackathon projects work perfectly—until the network drops a packet. In payments, a dropped packet means lost money. Today, we aren’t just going to show you that our Contextual Bandit recovers 20% more revenue than naive retries. We are going to show you what happens when the infrastructure actively tries to destroy our system."

## 1. The Phantom Charge Recovery (Saga / DLQ) (60s)
*Speaker opens a split-screen terminal alongside the dashboard.*

"In a distributed system, what happens if Razorpay deducts the money, but our worker process is killed before the PostgreSQL commit? Most systems permanently lose the transaction. Let’s force this exact crash."

*(Action: Execute a simulated recovery action from the UI, but instantly `kill -9` the Celery worker process mid-execution.)*

"The worker is dead. The database never recorded the success. But watch."

*(Action: Restart the worker. The 'Reconcile Pending Actions' job fires automatically.)*

"Our worker sweeps the Dead Letter Queue, identifies the orphaned idempotency key, queries Razorpay, and gracefully heals the state machine. The dashboard updates. No data lost. No phantom state."

## 2. The Webhook Flood Defense (Redis Locks) (60s)
"Next anomaly: A broken upstream bank integration starts blasting our endpoint with thousands of duplicate failed-payment webhooks in two seconds. A naive AI would process them all, updating its Thompson Sampling beta distribution thousands of times and permanently corrupting its machine learning model."

*(Action: Run a load-testing script that fires 1,000 identical webhook payloads at the FastAPI endpoint in 2 seconds.)*

"We just fired 1,000 identical webhooks. Look at the API logs."

*(Action: Show the API logs instantly rejecting 999 requests with a `409 Conflict`.)*

"Our Redis distributed lock, keyed on the `event_id`, caught the flood at the gateway. The Bandit only processed exactly *one* event. The machine learning model remains perfectly uncorrupted, and the database isn't overwhelmed."

## 3. The Localized Circuit Breaker (60s)
"Not all downtime is equal. If HDFC's gateway goes down, retrying an SBI card shouldn't be penalized. Let's inject a localized 5xx storm for a single issuer."

*(Action: Toggle the fault-injection admin endpoint to force 100% failure rates for 'HDFC Bank' instruments.)*

"Watch the Live Event Feed. The AI tries an HDFC recovery—it fails. It tries a second—it fails. Now watch the third."

*(Action: The third HDFC event comes in. The UI instantly marks it `BLOCKED - CIRCUIT BREAKER OPEN`.)*

"The system tripped a targeted circuit breaker for *only* the failing bank. It pauses retries to save the customer's maximum attempt quota. Meanwhile..." 

*(Action: An SBI event comes in and successfully recovers.)*

"...it seamlessly recovers revenue from unaffected instruments. We didn't burn the customer's trust, and we didn't DDoS the gateway."

## 4. The Closer (30s)
"Every single decision the AI made during this chaos was appended to a cryptographically secure, permission-enforced PostgreSQL audit ledger. You don't need a twelfth shiny AI feature to win in payments; you need a system that survives reality. That is ResiliencePay."

---

## Anticipated Judge Questions
- **"What happens if Redis goes down?"** → "The API degrades gracefully to a 503, leveraging Razorpay's exponential backoff webhook retries until the cache recovers. The DB remains the source of truth."
- **"How did you implement the circuit breaker?"** → "It tracks a rolling window of failure rates per bank segment in Redis. Once it crosses a 50% threshold in 60 seconds, it shifts to an 'Open' state and blocks execution at the Act layer."
