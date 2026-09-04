# Judge Q&A Prep — ResiliencePay

Anticipated questions, organized by theme, with the answer already worked
out. Read this the night before your demo, not during it — you want these
internalized, not read off a screen.

## Architecture & design judgment

**"What's the most interesting engineering decision you made?"**
> "We separated the learning system from the compliance system
> architecturally, not just logically — `evaluate_gate()`'s function
> signature doesn't even accept a confidence score as a parameter, so it's
> structurally impossible for the bandit's certainty to influence a
> compliance decision. This mirrors how real payments companies actually
> have to build this — regulators don't accept 'the model was confident'
> as a justification."

**"Why a contextual bandit instead of just having an LLM decide everything?"**
> "Auditability, reproducibility, and provable improvement. A bandit gives
> us an exact numeric reason for every decision — the α/β values at
> decision time — that we can show a regulator or a merchant. An LLM
> decision is neither reproducible nor provably improving over time the
> way a bandit's convergence is. We use LLMs exactly where their strength
> applies — classifying ambiguous failure text and generating message
> copy — and nowhere else."

**"Isn't your cause-category / arm taxonomy just hardcoded?"**
> "Yes, deliberately — because the real world is closed-taxonomy here too.
> Card networks publish a standardized set of decline codes; Stripe and
> Razorpay both map these into a bounded internal category set the same
> way we do. What's genuinely learned is which recovery action to pick
> given that classification — that's the bandit, and that part is not
> hardcoded at all."

**"Why not just use rules for the whole thing, no ML at all?"**
> "A rule table can't improve — it encodes today's best guess as
> permanent. We seed the bandit with the same domain intuition a rule
> table would encode, as an informed prior, then let it update on real
> observed outcomes. You get the best of both: a sensible starting point
> and a policy that gets measurably better over time."

## The bandit specifically

**"How do you know the bandit is actually learning, not just noise?"**
> "Two things: the multi-seed variance check — we ran the comparison
> across multiple random seeds and the bandit beat the baseline
> consistently, not just once by luck — and the arm-selection-distribution
> chart, which shows the policy visibly shifting away from a
> poorly-matched action for a given failure cause as it accumulates
> evidence."

**"What happens if the bandit picks a bad action repeatedly?"**
> "The Gate caps the downside regardless — a genuinely bad action either
> gets blocked by a compliance rule or simply produces a low reward, which
> Thompson Sampling naturally down-weights for that context going forward.
> The compliance layer's guarantee doesn't depend on the bandit ever
> being 'good.'"

**"Why Thompson Sampling specifically, not another bandit algorithm?"**
> "It's simple enough to implement correctly and explain honestly in the
> time we had, it has well-understood convergence properties, and its
> explore/exploit balance is automatic — no manually-tuned schedule to get
> wrong. A more complex algorithm (LinUCB, a contextual neural bandit)
> would add risk without adding anything we actually needed at this scale."

## Data & measurement honesty

**"Is this data real?"**
> "It's synthetic, and we're upfront about that — real production
> transaction data isn't something Razorpay could hand us for a hackathon.
> What's real is the mapping methodology: we based our failure-cause
> distribution and gateway error codes on Razorpay's actual documented
> categories, and everywhere we could trigger a real Razorpay test-mode
> API call, we did — that's marked explicitly as non-simulated in our
> audit trail."

**"Why is your exception rate not zero?"**
> "Because a zero percent exception rate would mean we're not being
> honest about which cases are genuinely unrecoverable — a hard decline or
> an explicit cancellation shouldn't be 'fixed' by retrying harder. We
> report those honestly rather than hiding them, and you can see exactly
> which cases and why in the exception list."

**"How do I know your baseline comparison isn't rigged in your favor?"**
> "The baseline and the bandit run through the identical pipeline code —
> same synthetic dataset, same seed, same diagnosis logic, same gate
> rules. The only difference is which object implements the decision
> policy interface. We have a fairness test that literally asserts both
> runs see the exact same event sequence."

## Resilience / chaos

**"What happens if Razorpay is actually down right now?"**
> [If you can trigger it live] "Let me show you — I'll enable fault
> injection." [Trigger it, show the dashboard reflecting a `failed` action
> with a full audit row, not a silent gap.] "The retry logic treats this
> exactly like a real outage — same exception types, same backoff, same
> logging — because our fault injection raises the actual exception types
> a real failure would raise, not a fake one our code specifically knows
> to expect."

**"Isn't this chaos testing just theater — did you actually verify it?"**
> "Yes — we have a specific test proving the injected fault is caught by
> the exact same exception-handling code path as a real Razorpay 5xx,
> not a special test-only branch. If our retry logic ever needed
> modification to catch the simulated fault type, that itself would be a
> red flag that the test wasn't real — we checked for that specifically."

## Security & production-readiness

**"What about security — is this actually safe to run?"**
> "A few concrete things: the audit log has database-level immutability —
> the application's own database role literally cannot run UPDATE or
> DELETE against it, we can show you that live. Secrets are never
> committed, redacted from logs automatically, and Razorpay credentials
> are test-mode only throughout. We deliberately didn't build full OAuth
> for this hackathon scope — that would be over-engineering for a demo —
> but the one genuinely dangerous endpoint, the fault-injection toggle, is
> protected behind a shared secret."

**"Would this actually work in production?"**
> "The core architecture would carry over directly — the taxonomy tables,
> the Gate/Decide separation, the audit trail design are all
> production-shaped decisions, not hackathon shortcuts. What would need to
> change for real production use: real customer consent/communication
> integrations instead of simulated nudges, proper authentication instead
> of a shared secret, and a longer bandit warm-up period against real
> traffic before trusting its policy over the naive baseline."

## If something breaks live

**"Your demo just failed — what happened?"**
> Stay calm, say exactly what's true: "We'll fall back to this morning's
> cached batch run — same pipeline, same code, we're just not
> re-triggering the live API call right now." Then continue the demo from
> the cached data. Do not apologize excessively or over-explain — state it
> once, move on.

## Closing line, if given the chance to end on your own terms

> "We tried to build this the way a payments company would actually have
> to build it — not just something that demos well, but something where
> every load-bearing claim, from 'the compliance layer can't be
> overridden' to 'the bandit is genuinely learning' to 'this survives real
> failure,' is backed by a test we can show you, not just a slide."
