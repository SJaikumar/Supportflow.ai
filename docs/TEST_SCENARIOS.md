# Test Scenarios and Expected Outcomes

These scenarios follow the supplied course assignment. Expected behavior depends on the fictional policies in `knowledge_base/` and verified order records. Live AI output may vary; validate the factual result and escalation rather than exact wording.

| # | Complaint / situation | Expected result |
| --- | --- | --- |
| 1 | “Where is my order? It was supposed to arrive yesterday.” | Shipping classification; answer from shipping policy plus verified order facts; non-risky case may be resolved when appropriate |
| 2 | “I want to return the shoes I bought last week. How do I get a refund?” | Return/refund steps and policy window; request for actual refund action requires human approval |
| 3 | “I forgot my password and can't log in.” | Account/login policy and reset guidance; no invented reset link |
| 4 | “The blender I received is broken. Can I get a replacement?” | Product quality / refund classification; policy-backed steps; human approval for restricted actions |
| 5 | “You charged my card three times! Fix this now or I'm contacting my bank and a lawyer.” | Billing, high urgency / dispute, escalated for authorized human handling |
| 6 | “Do you sell custom-branded gift cards for a company of 500?” | No unsupported policy claims; honestly state the gap; escalate |
| 7 | Damaged product photo already attached | AI acknowledges it is attached and does not request the identical initial image again |
| 8 | Photo attached without consent | File is visible for manual review; AI image inspection is not performed |
| 9 | AI drafted a response on an escalated case | Human agent can review and send informational update, but cannot approve a refund by sending text |
| 10 | Approver approves or rejects a refund request | Decision is persisted and customer receives a reviewed message; simulated processing is separate |
| 11 | Deadline exceeded | SLA event and staff queue signal are visible, without duplicate alerts on repeat checks |
| 12 | Customer opens a different customer's ticket URL | Access denied or only own ticket visible |

| 13 | Alex assigns an escalation to Maya | Named assignment persisted; appears under Maya's “Assigned to me” |
| 14 | Maya acknowledges, reassigns or completes assigned escalation | Role checks enforced; audit log records changes |
| 15 | Staff tries to close unresolved assigned escalation | Closure refused until escalation completed |
| 16 | Staff resolves and closes a routine ticket | Summary required, status and customer portal updated |
| 17 | Customer replies to closed ticket | Ticket reopens with history preserved |

## Automated checks

```powershell
python -m pytest -q
```

## Manual browser verification

- Login and role-specific navigation work; login page does not list passwords.
- Customers cannot see internal staff notes or other customers' records.
- AI answer cites the real policy passage and agent trace can be inspected.
- Human approval workflow returns a notification to the correct customer.
- Ticket list, orders and message rows have no overlapping typography at your target browser width.
- SLA worker can be started and stopped independently of the UI.
- Ticket CSV download opens in spreadsheet software.

## Screenshots

Add evidence under `screenshots/` after a successful run. Screenshots should show actual app state, not a static design mockup.
