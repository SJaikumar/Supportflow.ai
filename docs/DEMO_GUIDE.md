# Instructor Demo Guide

## Prepare

1. Install dependencies, configure `.env` (if using live AI), and run Streamlit.
2. Start the SLA worker in a second terminal, or use the manual SLA check for a short demonstration.
3. Use the seeded **test-only** accounts documented in `README.md`.
4. Verify the AI API connection before presenting if the demo relies on live LLM output.

## Demo A: Customer raises a ticket

1. Sign in as `priya@demo.com`.
2. Navigate to **Create request** or **My orders → Get help**.
3. File a delivery or damaged-product complaint. Upload an image **only if you want to demonstrate image handling**. Grant image-analysis consent if you want the AI to inspect it.
4. Show the created ticket and customer-visible updates in **My tickets**.

## Demo B: AI analysis with policy citations

1. Sign in as `alex@demo.com`.
2. Open **Tickets**, select the new or existing ticket, and open **AI assistant**.
3. Choose **Run AI analysis**.
4. Explain the sequence: Query, Knowledge, Resolution, Log.
5. Show the draft and verified policy citations. Open the optional detailed agent trace if asked.
6. Choose **Use AI Draft in reply**, review/edit, and confirm before sending an informational update.

**Important:** A support agent may send an informational reply. That is **not** authorization to approve a refund or payment adjustment.

## Demo C: Human-in-the-loop

1. Choose a ticket requiring refund/payment authorization.
2. Have the support agent create an approval request.
3. Sign in as `maya@demo.com` and visit **Approvals**.
4. Edit the draft response if appropriate, then approve or reject.
5. Return to customer login to show the portal inbox notification and response.
6. If approved, demonstrate separate manual/optional simulated-refund processing and its final state.

## Demo D: Customer history and SLA

1. Sign in as Alex and open **Customer 360°** for a repeat-contact customer.
2. Show earlier tickets, orders, refunds and internal notes (staff-only).
3. Open **SLA monitor** and show warning/breach indicators, commitments and overdue work.
4. Explain that a first-response event does not mean the issue is resolved.

## Required submission screenshots

Capture real screenshots of **Resolved ticket**, **Escalated ticket**, and **Ticket Log/export**. Add at least two additional scenarios, such as the approval screen and source-backed AI answer. Use the filenames described in `screenshots/README.md`.

Do not display real API keys, passwords or personally identifiable customer data in screenshots.

## Demo E: Manual escalation, resolve, close and reopen

1. As Alex, open an active ticket; select **Escalation & assignment → Escalate / assign ticket**.
2. Assign to Maya with a clear reason.
3. As Maya, open **Escalations → Assigned to me**, acknowledge the work, and complete it with an outcome note.
4. If any refund is needed, show the **separate Approvals workflow**.
5. When all obligations are finished, return to **Ticket management**: mark resolved with a factual summary, then close.
6. Reopen with a reason to show the ticket history and audit record are retained.

For details see [Escalation and ticket controls](ESCALATION_AND_TICKETS.md).
