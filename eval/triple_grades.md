# Extraction quality: 10 random triples (seed 42)

Grades: correct / wrong / unsupported

## 1. (Payments Core) -OWNS-> (payment processor)

Chunk: `service-catalog.md#0003`

```
s the grace period and read-only rules of the Billing and Refund Policy. Talks to the payment processor; never stores full card numbers.

Owner: **Payments Core**.



### audit-log



Records security-relevant events (sign-ins, role changes, connector edits, exports) for workspaces on Business and Enterprise plans.

Owner: **Identity**.



## 2. Teams



| Team | Engineering lead | On-call channel | Working hours (Paris time) |

|---|---|---|---|

| Platform | Samuel Okafor | #oncall-platform | 24/7 rotation |

| Identity | Priya Raman | #oncall-identity | 24/7 rotation |

| Data Integrations | Tomasz Wójcik | #oncall-data-integrations | 08:00–20:00, weekdays |

| Analytics Engine | Léa Fontaine | #oncall-analytics | 24/7 rotation |

| Messaging | Inès Moreau | #oncall-messaging | 08:00–20
```

**Grade:** wrong

**Why:** Payments Core owns the ledger service, and ledger only "talks to the payment processor". The payment processor is an external party; nothing says Payments Core owns it. Wrong entity: the object should be ledger, whose heading was cut off into the previous chunk.

## 2. (KST-5031) -RAISED_BY-> (postroom)

Chunk: `support-runbook-errors.md#0008`

```
by the current Owner from **Settings → Members**.

**Escalate:** no.



## Delivery and embedding (KST-5xxx)



### KST-5031 — Scheduled report not delivered



**User sees:** the schedule shows "Last delivery failed".

**Cause:** the report was generated but the e-mail was not sent. This error is raised by postroom, the service that sends all Kestrel e-mails. A single occurrence is usually a temporary problem with a recipient's mail server.

**Support action:** check whether the recipient's address is correct and whether the next delivery succeeds. Ask the customer to check that messages from kestrel.example are not blocked by their mail filter.

**Escalate:** if the error happens on two consecutive deliveries, or for several customers on the same day, escalate to the team that owns post
```

**Grade:** correct

**Why:** The chunk says "This error is raised by postroom".

## 3. (KST-1001) -PART_OF-> (Sign-in)

Chunk: `support-runbook-errors.md#0001`

```
Escalations go to the team that owns the service involved. The owning team of each service and its on-call channel are listed in the Service Catalog.



## Severity levels



| Level | Meaning | Target first response |

|---|---|---|

| SEV-1 | Many customers cannot use Kestrel, or data is exposed | 15 minutes, page on-call |

| SEV-2 | One customer is blocked in production, no workaround | 1 hour |

| SEV-3 | Degraded behaviour with a workaround | Next business day |

| SEV-4 | Question, cosmetic issue | Normal queue |



## Sign-in (KST-1xxx)



### KST-1001 — Invalid credentials



**User sees:** "The e-mail or password is incorrect."

**Cause:** wrong password, or the user is signing in to a workspace that enforces single sign-on.

**Support action:** check whether the workspace enfo
```

**Grade:** correct

**Why:** KST-1001 is listed under the section "Sign-in (KST-1xxx)". Supported, but it describes the document structure rather than a product fact, so it adds little for retrieval.

## 4. (Samuel Okafor) -LEADS-> (Platform)

Chunk: `service-catalog.md#0003`

```
s the grace period and read-only rules of the Billing and Refund Policy. Talks to the payment processor; never stores full card numbers.

Owner: **Payments Core**.



### audit-log



Records security-relevant events (sign-ins, role changes, connector edits, exports) for workspaces on Business and Enterprise plans.

Owner: **Identity**.



## 2. Teams



| Team | Engineering lead | On-call channel | Working hours (Paris time) |

|---|---|---|---|

| Platform | Samuel Okafor | #oncall-platform | 24/7 rotation |

| Identity | Priya Raman | #oncall-identity | 24/7 rotation |

| Data Integrations | Tomasz Wójcik | #oncall-data-integrations | 08:00–20:00, weekdays |

| Analytics Engine | Léa Fontaine | #oncall-analytics | 24/7 rotation |

| Messaging | Inès Moreau | #oncall-messaging | 08:00–20
```

**Grade:** correct

**Why:** Teams table row: Platform | Samuel Okafor (Engineering lead).

## 5. (Billing and Refund Policy) -APPLIES_TO-> (Business)

Chunk: `billing-policy-2026.md#0000`

```
# Kestrel Analytics — Billing and Refund Policy



Effective date: 1 March 2026 · Policy owner: Finance · Audience: customers and support staff



This policy replaces the Billing and Refund Policy effective 1 January 2025. Requests made before 1 March 2026 are handled under the previous policy.



## 1. Scope



This policy explains how Kestrel Analytics charges for its plans, how invoices are issued, and when refunds are possible. It applies to all paid plans: Starter, Team, Business and Enterprise. Enterprise contracts may contain different terms; when they do, the contract takes precedence over this policy. Current prices are published on the Kestrel pricing page and are not repeated here.



## 2. Billing cycles



Paid plans are billed per seat, either monthly or annually. Monthly pl
```

**Grade:** correct

**Why:** "It applies to all paid plans: Starter, Team, Business and Enterprise."

## 6. (Billing and Refund Policy) -APPLIES_TO-> (Team)

Chunk: `billing-policy-2026.md#0000`

```
# Kestrel Analytics — Billing and Refund Policy



Effective date: 1 March 2026 · Policy owner: Finance · Audience: customers and support staff



This policy replaces the Billing and Refund Policy effective 1 January 2025. Requests made before 1 March 2026 are handled under the previous policy.



## 1. Scope



This policy explains how Kestrel Analytics charges for its plans, how invoices are issued, and when refunds are possible. It applies to all paid plans: Starter, Team, Business and Enterprise. Enterprise contracts may contain different terms; when they do, the contract takes precedence over this policy. Current prices are published on the Kestrel pricing page and are not repeated here.



## 2. Billing cycles



Paid plans are billed per seat, either monthly or annually. Monthly pl
```

**Grade:** correct

**Why:** Same sentence: the policy applies to the Team plan.

## 7. (Priya Raman) -LEADS-> (Identity)

Chunk: `service-catalog.md#0003`

```
s the grace period and read-only rules of the Billing and Refund Policy. Talks to the payment processor; never stores full card numbers.

Owner: **Payments Core**.



### audit-log



Records security-relevant events (sign-ins, role changes, connector edits, exports) for workspaces on Business and Enterprise plans.

Owner: **Identity**.



## 2. Teams



| Team | Engineering lead | On-call channel | Working hours (Paris time) |

|---|---|---|---|

| Platform | Samuel Okafor | #oncall-platform | 24/7 rotation |

| Identity | Priya Raman | #oncall-identity | 24/7 rotation |

| Data Integrations | Tomasz Wójcik | #oncall-data-integrations | 08:00–20:00, weekdays |

| Analytics Engine | Léa Fontaine | #oncall-analytics | 24/7 rotation |

| Messaging | Inès Moreau | #oncall-messaging | 08:00–20
```

**Grade:** correct

**Why:** Teams table row: Identity | Priya Raman (Engineering lead).

## 8. (KST-5038) -ESCALATES_TO-> (postroom)

Chunk: `support-runbook-errors.md#0009`

```
s, or for several customers on the same day, escalate to the team that owns postroom, as SEV-2.



### KST-5038 — Embed token expired



**User sees:** an embedded dashboard shows "This link has expired".

**Cause:** the embed token passed by the customer's application is older than its lifetime (24 hours by default).

**Support action:** the customer's server must request a new token before the old one expires. On Business and Enterprise, the lifetime can be raised up to 30 days.

**Escalate:** no.



## Billing (KST-6xxx)



### KST-6002 — Payment declined



**User sees:** "Your payment was declined."

**Cause:** the card was refused by the bank: insufficient funds, expired card, or a security block.

**Support action:** ask the Owner to update the payment method before the next automat
```

**Grade:** wrong

**Why:** The chunk says "Escalate: no" for KST-5038. The postroom sentence at the top of the chunk belongs to KST-5031 and was cut by the chunk boundary, so the LLM attached it to the wrong error code.

## 9. (Léa Fontaine) -LEADS-> (Analytics Engine)

Chunk: `service-catalog.md#0003`

```
s the grace period and read-only rules of the Billing and Refund Policy. Talks to the payment processor; never stores full card numbers.

Owner: **Payments Core**.



### audit-log



Records security-relevant events (sign-ins, role changes, connector edits, exports) for workspaces on Business and Enterprise plans.

Owner: **Identity**.



## 2. Teams



| Team | Engineering lead | On-call channel | Working hours (Paris time) |

|---|---|---|---|

| Platform | Samuel Okafor | #oncall-platform | 24/7 rotation |

| Identity | Priya Raman | #oncall-identity | 24/7 rotation |

| Data Integrations | Tomasz Wójcik | #oncall-data-integrations | 08:00–20:00, weekdays |

| Analytics Engine | Léa Fontaine | #oncall-analytics | 24/7 rotation |

| Messaging | Inès Moreau | #oncall-messaging | 08:00–20
```

**Grade:** correct

**Why:** Teams table row: Analytics Engine | Léa Fontaine (Engineering lead).

## 10. (Identity) -OWNS-> (audit-log)

Chunk: `service-catalog.md#0003`

```
s the grace period and read-only rules of the Billing and Refund Policy. Talks to the payment processor; never stores full card numbers.

Owner: **Payments Core**.



### audit-log



Records security-relevant events (sign-ins, role changes, connector edits, exports) for workspaces on Business and Enterprise plans.

Owner: **Identity**.



## 2. Teams



| Team | Engineering lead | On-call channel | Working hours (Paris time) |

|---|---|---|---|

| Platform | Samuel Okafor | #oncall-platform | 24/7 rotation |

| Identity | Priya Raman | #oncall-identity | 24/7 rotation |

| Data Integrations | Tomasz Wójcik | #oncall-data-integrations | 08:00–20:00, weekdays |

| Analytics Engine | Léa Fontaine | #oncall-analytics | 24/7 rotation |

| Messaging | Inès Moreau | #oncall-messaging | 08:00–20
```

**Grade:** correct

**Why:** "Owner: Identity" under the audit-log heading.

## Counts

correct: 8 / wrong: 2 / unsupported: 0

## Notes

- Both wrong triples come from chunk boundaries (800 characters). In #1 the `### ledger` heading is in the previous chunk; in #8 the end of the KST-5031 section spills into the KST-5038 chunk. The extractor only sees one chunk at a time.
- Cost of #8: a question about KST-5038 follows KST-5038 → postroom → Messaging and pulls chunks that suggest escalating to Messaging, while the correct answer is "do not escalate".
- Sample bias: 5 of the 10 triples come from the same chunk (`service-catalog.md#0003`, the teams table). Table rows are easy to extract, so 8/10 is probably optimistic for prose chunks.
