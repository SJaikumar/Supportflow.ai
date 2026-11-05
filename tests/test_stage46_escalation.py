"""Stage 4.6 — durable staff handoffs, distinct from AI flags and refund approval."""
import pytest
from sqlalchemy import inspect, select


def _users(demo):
    return tuple(demo.authenticate(email, 'Demo123!') for email in (
        'priya@demo.com', 'alex@demo.com', 'maya@demo.com', 'admin@demo.com'))


def _ticket(demo, priya):
    return demo.create_ticket(priya, order_id=None, category='Account',
        title='Urgent account recovery support',
        complaint='I still cannot sign in and need a specialist to review my account.')


def test_escalation_table_and_existing_ai_flags_visible(demo):
    from supportflow.db import engine
    priya, alex, maya, admin = _users(demo)
    assert 'escalation_assignments' in inspect(engine).get_table_names()
    queued = demo.escalation_queue(alex)
    assert any(r['ticket'].id == 'TKT-10455' and r['assignment'] is None
               for r in queued)  # seeded AI-like flag, no named recipient
    with pytest.raises(demo.SupportError, match='Staff-only'):
        demo.escalation_queue(priya)


def test_agent_creates_audited_handoff_to_maya_customer_sees_safe_notice(demo):
    from supportflow.db import SessionLocal
    from supportflow.models import AuditEvent, EscalationAssignment, ApprovalRequest
    priya, alex, maya, admin = _users(demo)
    tid = _ticket(demo, priya)
    assert maya.id in [u.id for u in demo.escalation_targets(alex)]
    assert alex.id not in [u.id for u in demo.escalation_targets(alex)]
    with pytest.raises(demo.SupportError):
        demo.escalate_ticket(priya, tid, maya.id, 'Customer requires account review.')
    with pytest.raises(demo.SupportError):
        demo.escalate_ticket(alex, tid, priya.id, 'Customer requires account review.')
    with pytest.raises(demo.SupportError, match='10'):
        demo.escalate_ticket(alex, tid, maya.id, 'short')
    before = demo.unread_count(priya)
    esc_id = demo.escalate_ticket(alex, tid, maya.id,
        'Multiple failed verification attempts; request a specialist account review.')
    assert demo.unread_count(priya) == before + 1
    with SessionLocal() as db:
        e = db.get(EscalationAssignment, esc_id)
        assert e.status == 'OPEN' and e.assigned_to == maya.id and e.ticket_id == tid
        events = db.scalars(select(AuditEvent).where(AuditEvent.ticket_id == tid)).all()
        assert any(event.event_type == 'ESCALATION_ASSIGNED' for event in events)
        approvals = db.scalars(select(ApprovalRequest).where(ApprovalRequest.ticket_id == tid)).all()
        assert approvals == []  # routing is not a refund approval
    assert demo.ticket_detail(priya, tid)['ticket'].escalated is True
    customer_notes = demo.notifications_for_customer(priya)
    latest = next(note for note in customer_notes if note.ticket_id == tid)
    assert 'specialist support' in latest.body
    assert 'verification attempts' not in latest.body
    with pytest.raises(demo.SupportError, match='already has'):
        demo.escalate_ticket(alex, tid, admin.id, 'A second simultaneous escalation is not permitted.')


def test_only_recipient_or_admin_can_acknowledge_reassign_and_finish(demo):
    priya, alex, maya, admin = _users(demo)
    tid = _ticket(demo, priya)
    eid = demo.escalate_ticket(alex, tid, maya.id,
        'Please review account verification and provide the appropriate next steps.')
    with pytest.raises(demo.SupportError, match='assignee'):
        demo.acknowledge_escalation(alex, eid)
    with pytest.raises(demo.SupportError, match='assignee'):
        demo.complete_escalation(alex, eid, 'I believe the review is complete now.')
    demo.acknowledge_escalation(maya, eid)
    with pytest.raises(demo.SupportError, match='Only a new'):
        demo.acknowledge_escalation(maya, eid)
    with pytest.raises(demo.SupportError, match='assignee'):
        demo.reassign_escalation(alex, eid, admin.id,
            'Please reassign this case to an available administrator.')
    demo.reassign_escalation(maya, eid, alex.id,
        'Verification completed; agent Alex will communicate the final steps.')
    hist = demo.escalation_history(maya, tid)
    assert hist[0]['record'].status == 'OPEN'
    assert hist[0]['assignee'].id == alex.id
    demo.acknowledge_escalation(alex, eid)
    demo.complete_escalation(alex, eid,
        'Account verification finished and support steps have been returned to the agent.')
    assert demo.ticket_detail(alex, tid)['ticket'].status == 'NEW'
    assert demo.ticket_detail(alex, tid)['ticket'].escalated is False
    with pytest.raises(demo.SupportError, match='No active'):
        demo.complete_escalation(alex, eid, 'Repeated completion must fail without side effects.')
    demo.resolve_ticket(alex, tid, 'The user can sign in with their verified access settings.')
    demo.close_ticket(alex, tid)
    assert demo.ticket_detail(priya, tid)['ticket'].status == 'CLOSED'


def test_active_escalation_blocks_resolution_and_pending_promise_blocks_completion(demo):
    from datetime import timedelta
    from supportflow.models import utcnow
    priya, alex, maya, admin = _users(demo)
    tid = _ticket(demo, priya)
    eid = demo.escalate_ticket(alex, tid, maya.id,
        'Please investigate the repeated account access errors before closing.')
    with pytest.raises(demo.SupportError, match='human escalation'):
        demo.resolve_ticket(alex, tid, 'The account problem has already been resolved.')
    promise_id = demo.create_commitment(alex, tid,
        'Provide an account verification update to the customer', utcnow()+timedelta(hours=2))
    with pytest.raises(demo.SupportError, match='promises'):
        demo.complete_escalation(maya, eid, 'The account investigation was completed successfully.')
    demo.complete_commitment(alex, promise_id)
    demo.complete_escalation(maya, eid, 'The account investigation was completed and documented.')
    demo.resolve_ticket(alex, tid, 'All account recovery steps are now completed.')


def test_approved_refund_still_requires_separate_approver(demo):
    priya, alex, maya, admin = _users(demo)
    tid = demo.create_ticket(priya, order_id='ORD-87175', category='Refund',
        title='Refund escalation authorization test',
        complaint='The desk light stopped working and I request a refund review.')
    eid = demo.escalate_ticket(alex, tid, maya.id,
        'Refund requested for defective item; finance approval must remain separate.')
    assert demo.ticket_detail(maya, tid)['approvals'] == []
    approval_id = demo.request_approval(alex, tid, 20000,
        'We have sent the request for human refund review. No refund has been authorized yet.')
    with pytest.raises(demo.SupportError, match='approval'):
        demo.complete_escalation(maya, eid, 'The refund decision is still waiting for approval.')
    with pytest.raises(demo.SupportError):
        demo.decide_approval(alex, approval_id, approve=True,
            edited_message='I approve a refund without proper authorization.')


def test_escalation_ui_has_menu_page_and_manual_ticket_action(demo):
    from pathlib import Path
    root = Path(__file__).resolve().parent.parent
    app = (root/'app.py').read_text()
    agent = (root/'supportflow/views/agent.py').read_text()
    assert "'Escalations': st.Page(agent.escalations" in app
    assert "visible = ['Dashboard', 'All tickets', 'Escalations'" in app
    assert "['All','Active','Escalated','Resolved']" in agent
    assert 'Escalate & assign' in agent
    assert 'Acknowledge escalation' in agent
    assert 'Complete escalation' in agent
