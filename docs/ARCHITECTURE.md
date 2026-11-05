# Architecture and Data Flow

## Main components

| Layer | Location | Role |
| --- | --- | --- |
| UI entry point | `app.py` | Streamlit role-based navigation and app initialization |
| Customer portal | `supportflow/views/customer.py` | Complaints, order history, messages, photo attachments |
| Agent portal | `supportflow/views/agent.py` | Ticket queue, AI analysis, approvals, Customer 360°, SLA monitor |
| SQL persistence | `supportflow/db.py`, `supportflow/models.py`, `supportflow/services.py` | SQLite, SQLAlchemy models, structured record updates |
| Multi-agent orchestrator | `supportflow/ai/pipeline.py` | Sequential AutoGen Query → Knowledge → Resolution → Log |
| Retrieval | `supportflow/ai/retrieval.py` | Sample-policy retrieval, semantic/lexical ranking and citations |
| Escalation rules | `supportflow/ai/rules.py`, `supportflow/reply_policy.py` | Validated decisions and restrictions on customer responses |
| Named human escalations | `supportflow/services.py`, `supportflow/models.py`, `supportflow/views/agent.py` | Role-restricted assignment, acknowledge/reassign/complete, audit history |
| Analysis service | `supportflow/ai/services.py` | AI run lifecycle and audit records |
| SLA/refund operations | `supportflow/operations.py`, `supportflow/worker.py` | Deadline checks, notifications, opt-in simulated refund processing |
| Product photos | `supportflow/photo.py` | Consented optional image analysis |

## Four-agent orchestration

1. **Query Agent** extracts complaint category, urgency, sentiment and summary.
2. **Knowledge Agent** calls a policy retrieval tool and returns verified supporting citations.
3. **Resolution Agent** drafts a grounded, empathetic reply and flags sensitive actions.
4. **Log Agent** stages a structured log/escalation recommendation; the Python service verifies and persists records.

In the supplied code, the Python application coordinates the agents **sequentially** and validates the outputs. LLM-generated text cannot bypass deterministic authorization checks.

## Customer-to-human flow

```text
Customer opens ticket + optional photo
  └─ SQLite ticket + customer-visible message
      └─ Staff runs AutoGen analysis
          ├─ policy evidence / grounded draft / agent trace
          ├─ Agent edits and sends factual update (review confirmed)
          └─ Sensitive action → approval request
              └─ Authorized approver edits, approves or rejects
                  └─ customer portal message + notification
                      └─ optional demo refund processing after approval
```

Approval and refund **completion** are different states. A customer may be updated without the underlying issue being marked resolved.

## Data controls

- Ticket and order lookup is bound to authenticated account identity.
- AI policy citations should point to source documents, not invented rules.
- Sensitive payment details are redacted before external LLM calls where detected.
- Uploaded photo AI inspection requires customer consent and a staff-triggered action.
- Logs preserve agent recommendations and human decisions for auditability.
- The SLA worker is a separate process, not a persistent Streamlit browser task.

## Deployment limitations

The bundle targets **local demo use**. Public deployment requires secure identity provisioning, disabling shared demo credentials, database hardening, secrets management, back-ups, attachment security, operational monitoring and load testing.

## Manual escalation and closing lifecycle

`ticket.escalated` indicates risk/attention, but a separate escalation assignment record identifies the responsible human. The escalation inbox shows **Assigned to me**, **All active**, and **Needs assignment**. The assignee acknowledges and completes a handoff independently of the refund approval workflow. Pending assignments, approvals, refund actions and customer promises prevent premature closure. See [Escalation and Ticket Controls](ESCALATION_AND_TICKETS.md).
