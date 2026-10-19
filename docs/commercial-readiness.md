# Commercial-readiness backlog (separate from the demo; nothing here is implemented)
`DOEDU_LAUNCH_MODE=commercial` refuses to start today, on purpose. Items are ordered by dependency, not by effort. Estimates and prices are deliberately omitted.

## Product / business decisions (owner: you)
1. Paying customer and offer: operator subscription vs commission vs booking-request management (manual confirmation) as an intermediate product; unit economics.
2. Who confirms bookings and who owns passenger support, refunds, disputes and incident response (people, hours, escalation).
3. Legal entity, terms for passengers and operators, privacy notice, jurisdiction(s), consumer-rights and transport-regulation review, tax/invoicing: **qualified legal advice required**.
## Transport integration (P0 for any real sale)
4. Authorised access to real schedules and availability from each operator (agreement + technical interface). Define the `TransportProvider` interface (search, availability, hold, confirm, cancel, ticket) behind which the current synthetic data becomes one implementation.
5. Real reservation and ticket issuance with provider confirmation; mapping of provider states to our booking/reservation states; handling provider outages and conflicting availability.
6. Replace "whole-service capacity" with provider-accurate inventory; real delay/cancellation feeds into the disruption pipeline.
7. Operator onboarding, identity verification and role management (no demo shortcuts).
## Payments (P0)
8. Payment provider selection (cost, coverage, KYC); payment intent flow replacing the simulator behind a `PaymentProvider` interface; **no card data ever touches our servers** (hosted fields / redirect).
9. Webhook endpoint with signature verification, replay protection (idempotent event ids), ordering and retry handling; reconciliation job comparing provider records with `PaymentAttempt`/`Refund`.
10. Real refunds, partial refunds, chargebacks/disputes, settlement and payouts to operators; financial reporting and audit retention rules.
## Platform hardening required before real users
11. E-mail provider + verified registration + password reset + transactional notifications (booking confirmations, disruption alerts); notification preferences.
12. MFA for operator/admin accounts; admin access restricted to trusted networks; independent penetration test; vulnerability management process.
13. Data-protection work: retention/anonymisation job, subject-access/deletion procedure, processor agreements, breach process (see docs/privacy.md).
14. Production operations: managed PostgreSQL with PITR, tested restores, multi-zone/multi-instance web, capacity planning from measured data, SLOs and on-call, status page, cost monitoring.
15. Accessibility audit with assistive-technology users (WCAG 2.1 AA target), localisation, content review.
16. Rate limiting/WAF at ingress, bot protection on registration/booking, abuse handling.
## Acceptance gate for switching the launch mode
Only when (4)-(5), (8)-(10), (11), (13) and (14) are complete **and** the full flow has been verified end-to-end with each real provider in a sandbox, then production-verified with controlled real transactions agreed with the providers.
