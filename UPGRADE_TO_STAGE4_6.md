# SupportFlow AI — Stage 4.6: Human Escalation and Assignment

Stage 4.6 adds a **manual human escalation workflow**, in addition to the existing AI escalation flag and the separate refund approval workflow.

## What changed

- New **Escalations** menu item for agent, approver and admin accounts.
- **All Tickets → Status → Escalated** filter, including tickets flagged by AI and not yet assigned.
- **Open ticket → Escalation & assignment → Escalate / assign ticket** action.
- Explicit assignee and reason; new **escalation_assignments** SQLite table.
- **Assigned to me**, **All active**, and **Needs assignment** escalation views.
- Assignee/Admin actions to **Acknowledge**, **Reassign** and **Complete** the escalation with an audit record.
- A generic notification appears in the customer's portal inbox, without exposing confidential internal notes.
- An unfinished assigned escalation blocks manual resolve/close. The actual refund approval and completion remain separate.

## Role responsibilities

| Role | May escalate or reroute to | Notes |
|---|---|---|
| Customer | None | Can reply or reopen a ticket, but not choose internal staff |
| Agent (Alex) | Approver (Maya), Administrator | Can send reviewed customer updates, but cannot approve refunds |
| Approver (Maya) | Agent (Alex), Administrator | Can decide refund approvals independently of escalation status |
| Administrator | Other Agents / Approvers / Administrators | May acknowledge or reroute any assigned escalation |
| AI analysis | No human assignee is automatically chosen | The ticket appears under **Needs assignment** until a staff member routes it |

The currently assigned person (or an admin) may acknowledge, reassign or complete an active escalation. Completing an escalation requires a note and does **not** automatically resolve or close the ticket.

## Recommended install: small patch

1. Stop Streamlit and the SLA worker.
2. Back up your current working project (and any private data you wish to keep).
3. Extract the Stage 4.6 **Patch** ZIP into the existing project folder containing `app.py`. Allow matching source files to be replaced.
4. **Keep** `.env`, `.venv`, and `data/` unchanged. Do not overwrite them with test copies.
5. Install no new packages — `requirements.txt` remains the same.
6. In your activated virtual environment:

```powershell
python -m pytest -q
python -m streamlit run app.py
```

7. Restart the SLA worker in a second terminal if you use it:

```powershell
python -m supportflow.worker --interval 60
```

The app's startup initialization adds only the new `escalation_assignments` table/index to an existing Stage 4.5 SQLite database. It does not delete or reset your ticket records.

## End-to-end demonstration

1. Log in as **Alex**. Open **All Tickets**, select an active ticket, and find **Escalation & assignment** on the right.
2. Select **Maya Rao (Approver)**, enter a clear escalation reason, and click **Escalate & assign**.
3. Sign in as **Maya**, open **Escalations → Assigned to me**, then open the ticket and **Acknowledge escalation**.
4. If the escalation involves a refund, go to the separate **Approvals** area to authorize or reject that refund. Merely acknowledging an escalation does not authorize it.
5. Once relevant approvals, refunds, and promises are completed, **Complete escalation** with an outcome note.
6. The ticket remains active until a support agent explicitly **Mark resolved** and subsequently **Close ticket**.
7. Check **Audit history** for each handoff event, and the customer **Inbox** for the generic specialist-review notice.

## Important limitations

- This is a role-based demo, not enterprise identity management. User creation is seeded; no production LDAP/SSO integration.
- AI-flagged tickets are placed in **Needs assignment**; they do not automatically select a person.
- Notifications are internal portal records, not live email/SMS/WhatsApp messages.
- The UI must be visually verified on your Windows/Streamlit installation; tests cover the database and source-level UI contracts.

## GitHub submission

If you've already pushed Stage 4.5, add Stage 4.6 files to the same repo, retain `requirements.txt`, update screenshots to include the new escalations view, and avoid committing `.env`, `.venv` or `data/`.
