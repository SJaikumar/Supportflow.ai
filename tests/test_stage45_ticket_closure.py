"""Stage 4.5: explicitly manage ticket lifecycle without bypassing approvals."""
import pytest
from sqlalchemy import select


def _new_case(demo, category='Account'):
    priya = demo.authenticate('priya@demo.com', 'Demo123!')
    ticket_id = demo.create_ticket(
        priya, order_id=None, category=category,
        title='Need help with my account settings',
        complaint='I need help accessing my account and verifying the new settings.',
    )
    return priya, ticket_id


def test_staff_can_resolve_close_and_customer_reply_reopens(demo):
    from supportflow.db import SessionLocal
    from supportflow.models import AuditEvent, Notification
    priya, tid = _new_case(demo)
    alex = demo.authenticate('alex@demo.com', 'Demo123!')
    before = demo.unread_count(priya)
    with pytest.raises(demo.SupportError, match='before closing'):
        demo.close_ticket(alex, tid)
    demo.resolve_ticket(alex, tid, 'The account settings have been verified and restored.')
    details = demo.ticket_detail(priya, tid)
    assert details['ticket'].status == 'RESOLVED'
    assert details['ticket'].resolved_at is not None
    assert 'verified and restored' in details['messages'][-1].body
    assert demo.unread_count(priya) == before + 1
    with pytest.raises(demo.SupportError, match='Only an active'):
        demo.resolve_ticket(alex, tid, 'Trying to resolve the same ticket again.')
    demo.close_ticket(alex, tid)
    assert demo.ticket_detail(priya, tid)['ticket'].status == 'CLOSED'
    assert demo.unread_count(priya) == before + 2
    with SessionLocal() as db:
        events = db.scalars(select(AuditEvent).where(AuditEvent.ticket_id == tid)).all()
        assert any(event.event_type == 'TICKET_RESOLVED' for event in events)
        assert any(event.event_type == 'TICKET_CLOSED' for event in events)
        notifications = db.scalars(select(Notification).where(Notification.ticket_id == tid)).all()
        assert len(notifications) >= 2
    demo.post_ticket_message(priya, tid, 'The same issue returned. Please take another look at the settings.')
    reopened = demo.ticket_detail(priya, tid)['ticket']
    assert reopened.status == 'REOPENED'
    assert reopened.resolved_at is None


def test_support_can_reopen_explicitly_and_records_reason(demo):
    priya, tid = _new_case(demo)
    alex = demo.authenticate('alex@demo.com', 'Demo123!')
    demo.resolve_ticket(alex, tid, 'The customer can now log in successfully again.')
    demo.close_ticket(alex, tid)
    with pytest.raises(demo.SupportError, match='10'):
        demo.reopen_ticket(alex, tid, 'x')
    demo.reopen_ticket(alex, tid, 'Customer reported that the error reappeared after restarting.')
    details = demo.ticket_detail(priya, tid)
    assert details['ticket'].status == 'REOPENED'
    assert any('reappeared' in msg.body for msg in details['messages'])
    with pytest.raises(demo.SupportError, match='Only resolved or closed'):
        demo.reopen_ticket(alex, tid, 'Unnecessary second reopen attempt.')


def test_customer_cannot_manage_ticket_lifecycle(demo):
    priya, tid = _new_case(demo)
    with pytest.raises(demo.SupportError, match='support staff'):
        demo.resolve_ticket(priya, tid, 'Please resolve my ticket now.')
    with pytest.raises(demo.SupportError, match='support staff'):
        demo.close_ticket(priya, tid)
    with pytest.raises(demo.SupportError, match='support staff'):
        demo.reopen_ticket(priya, tid, 'Please reopen my ticket.')
    with pytest.raises(demo.SupportError, match='[Ss]upport staff'):
        demo.ticket_action_blockers(priya, tid)


def test_pending_commitment_blocks_resolution_until_completed(demo):
    from datetime import timedelta
    from supportflow.models import utcnow
    _, tid = _new_case(demo)
    alex = demo.authenticate('alex@demo.com', 'Demo123!')
    cid = demo.create_commitment(alex, tid,
        'Call customer with a configuration confirmation', utcnow() + timedelta(hours=2))
    assert any('promises' in b for b in demo.ticket_action_blockers(alex, tid))
    with pytest.raises(demo.SupportError, match='promises'):
        demo.resolve_ticket(alex, tid, 'The configuration problem has been resolved.')
    demo.complete_commitment(alex, cid)
    demo.resolve_ticket(alex, tid, 'The configuration problem has been resolved.')
    demo.close_ticket(alex, tid)


def test_pending_approval_and_processing_refund_block_resolution(demo):
    priya = demo.authenticate('priya@demo.com', 'Demo123!')
    alex = demo.authenticate('alex@demo.com', 'Demo123!')
    maya = demo.authenticate('maya@demo.com', 'Demo123!')
    tid = demo.create_ticket(priya, order_id='ORD-87175', category='Refund',
        title='Refund for damaged appliance',
        complaint='I am requesting a refund because this appliance has a defect.')
    aid = demo.request_approval(alex, tid, 50000,
        'A refund review has been requested and remains pending human authorization.')
    with pytest.raises(demo.SupportError, match='approval'):
        demo.resolve_ticket(alex, tid, 'This product refund complaint has been resolved.')
    demo.decide_approval(maya, aid, approve=True,
        edited_message='Your refund request was approved. Our demo refund processor will now handle it.')
    with pytest.raises(demo.SupportError, match='refund'):
        demo.resolve_ticket(alex, tid, 'This product refund complaint has been resolved.')
    refund = next(r for r in demo.ticket_detail(maya, tid)['refunds'] if r.status == 'PROCESSING')
    demo.complete_simulated_refund(maya, refund.id)
    assert demo.ticket_detail(maya, tid)['ticket'].status == 'RESOLVED'
    demo.close_ticket(alex, tid)
    assert demo.ticket_detail(priya, tid)['ticket'].status == 'CLOSED'


def test_resolution_text_cannot_claim_unapproved_refund(demo):
    _, tid = _new_case(demo)
    alex = demo.authenticate('alex@demo.com', 'Demo123!')
    with pytest.raises(demo.SupportError, match='approval workflow'):
        demo.resolve_ticket(alex, tid, 'Your refund has been approved and issued.')
    assert demo.ticket_detail(alex, tid)['ticket'].status == 'NEW'
