# Ticket lifecycle — Stage 4.5

SupportFlow distinguishes a **response sent** from a **ticket resolved** and a **ticket closed**. Sending an informational AI-assisted reply never automatically closes the ticket.

## Staff workflow

1. Log in with a seeded `agent`, `approver` or `admin` account.
2. Open **All tickets**, then select a ticket.
3. Use **Ticket management** near the top of the right-hand panel:
   - **Mark resolved**: for an active case once the actual issue is complete. Requires a factual 10–1,000 character resolution summary, which becomes customer-visible.
   - **Close ticket**: for a case currently marked `RESOLVED`; requires explicit confirmation.
   - **Reopen ticket**: for a `RESOLVED` or `CLOSED` case; requires a 10–1,000 character reason.
4. Status transitions and reasons are persisted to the audit trail; customers see portal notifications.
5. Customers can reopen an already resolved/closed case simply by sending a new reply on the same ticket.

## Closure safeguards

- Customers cannot trigger staff-only resolve/close/reopen actions directly.
- Manual resolution and closure are blocked by any pending human approval, refund still being requested/processed, or unfinished customer commitment.
- A reviewed AI message is not proof the underlying support request was resolved.
- These are **state changes only**: no real refund or delivery action is performed by closing a ticket.
- Original SLA timestamps are retained when a ticket reopens. Reopening currently does not start a fresh SLA obligation; that would require a later versioned SLA rule, to avoid overwriting historical commitments.

## Test instructions

1. As Alex, create or open a routine active case with no pending actions. Enter a resolution note and click **Mark resolved**.
2. Confirm the customer receives a resolved notification and the ticket status becomes `RESOLVED`.
3. Check the confirmation and click **Close ticket**. Status becomes `CLOSED`, and the customer receives a closure notification.
4. Choose **Reopen ticket** with a reason. The ticket returns to the active queue and the change is audited.
5. Try marking a ticket with pending refund approval as resolved; the action must be blocked.
6. As the customer, reply to a closed ticket; it must reopen without deleting its conversation history.

Regression: `python -m pytest -q`.
