# Human escalation, refund approval, and ticket closure

## Why these are separate

An **AI escalation flag** requests staff attention but has no owner until someone assigns it. A **human escalation assignment** identifies a responsible person and follows its own workflow. A **refund approval** is a separate restricted authorization. Sending a customer update, acknowledging an escalation, or writing an AI draft is not a refund approval and does not close the ticket.

## Role permissions (demo)

| Role | Escalation options | Refund authority |
| --- | --- | --- |
| Customer | Can submit/reply/reopen through ticket conversation; cannot assign internal staff | No |
| Alex (agent) | Escalate to an approver/admin; can send reviewed customer updates | No |
| Maya (approver) | Acknowledge/complete assigned work, reassign per permissions | Authorized for approval workflow |
| Admin | Can review and reassign escalations | Administrative workflow permissions |
| Four AutoGen agents | Recommend escalation; do not select a human owner automatically | No |

## Manual escalation demo

1. Log in as Alex → **All Tickets** → open an active ticket.
2. **Escalation & assignment** → **Escalate / assign ticket**.
3. Choose Maya, enter a specific reason, and save.
4. Log in as Maya → **Escalations** → **Assigned to me**.
5. Open the ticket and **Acknowledge escalation**. Investigate, reply or use the **Approvals** workflow if a refund needs authorization.
6. Enter an outcome to **Complete escalation**. The ticket stays open until genuinely resolved.

## Resolving, closing and reopening

1. Open a ticket as authorized staff → **Ticket management**.
2. **Mark resolved** with a factual summary **only when the issue is actually addressed**.
3. **Close ticket** after confirming no pending escalation, approval, refund or customer promise.
4. **Reopen ticket** with a reason when follow-up is necessary. A customer reply to a closed ticket also reopens it.
5. Check the ticket audit trail and the customer's portal notifications.

Unfinished escalations and other pending obligations must block premature resolution/closure. Reference [Ticket Lifecycle](TICKET_LIFECYCLE.md) and [Stage 4.6 Upgrade Guide](../UPGRADE_TO_STAGE4_6.md).
