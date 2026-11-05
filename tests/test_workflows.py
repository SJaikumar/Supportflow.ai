"""Acceptance-level tests for Stage 1 persistence and human approval."""
import pytest


def test_demo_accounts_and_seed(demo):
    priya=demo.authenticate('priya@demo.com','Demo123!')
    assert priya and priya.role=='customer'
    assert demo.authenticate('priya@demo.com','incorrect') is None
    assert len(demo.orders_for_customer(priya))==18
    assert len(demo.visible_tickets(priya))>=7


def test_customer_cannot_see_other_customer_order_or_ticket(demo):
    priya=demo.authenticate('priya@demo.com','Demo123!')
    with pytest.raises(demo.SupportError):
        demo.ticket_detail(priya,'TKT-10455')
    with pytest.raises(demo.SupportError):
        demo.create_ticket(priya,order_id='ORD-88311',category='Delivery',title='Wrong order',complaint='This order was not delivered to me.')


def test_new_ticket_and_conversation_persist(demo):
    priya=demo.authenticate('priya@demo.com','Demo123!')
    tid=demo.create_ticket(priya,order_id='ORD-88241',category='Product quality',
        title='Damaged cover',complaint='The top cover was badly broken on delivery.')
    t=demo.ticket_detail(priya,tid)['ticket']
    assert t.category=='Product quality' and t.priority=='P2'
    assert t.status=='NEW'
    demo.post_ticket_message(priya,tid,'Can I please share another photo later?')
    from supportflow.db import SessionLocal
    # Use a fresh database session to confirm persistence, not a shared in-memory object.
    with SessionLocal() as db:
        from supportflow.models import TicketMessage
        from sqlalchemy import select
        messages=db.scalars(select(TicketMessage).where(TicketMessage.ticket_id==tid)).all()
        assert len(messages)==2


def test_human_approval_sends_message_and_notification(demo):
    priya=demo.authenticate('priya@demo.com','Demo123!')
    agent=demo.authenticate('alex@demo.com','Demo123!')
    maya=demo.authenticate('maya@demo.com','Demo123!')
    customer_unread=demo.unread_count(priya)
    request=next(x for x in demo.approvals_list(agent) if x['ticket'].id=='TKT-10456')
    aid=request['approval'].id
    with pytest.raises(demo.SupportError):
        demo.decide_approval(agent,aid,approve=True,edited_message='This is a simulated refund response.')
    demo.decide_approval(maya,aid,approve=True,edited_message='Your refund was approved. A simulated processing step is next.')
    info=demo.ticket_detail(priya,'TKT-10456')
    assert info['ticket'].status=='ACTION_PENDING'
    assert any('refund was approved' in m.body for m in info['messages'])
    assert demo.unread_count(priya)==customer_unread+1
    with pytest.raises(demo.SupportError):
        demo.decide_approval(maya,aid,approve=True,edited_message='Duplicate approval is not allowed.')
    refund=next(x for x in demo.ticket_detail(maya,'TKT-10456')['refunds'] if x.status=='PROCESSING')
    demo.complete_simulated_refund(maya,refund.id)
    assert demo.ticket_detail(priya,'TKT-10456')['ticket'].status=='RESOLVED'
    with pytest.raises(demo.SupportError):
        demo.complete_simulated_refund(maya,refund.id)


def test_approval_rejection_and_customer_notification(demo):
    raj=demo.authenticate('raj@demo.com','Demo123!')
    maya=demo.authenticate('maya@demo.com','Demo123!')
    aid=next(x['approval'].id for x in demo.approvals_list(maya) if x['ticket'].id=='TKT-10451')
    with pytest.raises(demo.SupportError):
        demo.decide_approval(maya,aid,approve=False,edited_message='After review, we cannot approve the request.')
    demo.decide_approval(maya,aid,approve=False,
        edited_message='After reviewing your order, we are not able to approve this request at this stage.',
        reason='Evidence required')
    info=demo.ticket_detail(raj,'TKT-10451')
    assert info['ticket'].status=='IN_REVIEW'
    assert any('not able to approve' in m.body for m in info['messages'])


def test_customer_history_metrics_are_grounded(demo):
    maya=demo.authenticate('maya@demo.com','Demo123!')
    priya=demo.authenticate('priya@demo.com','Demo123!')
    c=demo.customer_for_user(priya)
    info=demo.customer_detail(maya,c.id)
    assert len(info['orders'])==18
    assert len(info['tickets'])>=7
    assert len(info['refunds'])>=4


def test_photo_upload_and_authorization(demo):
    import io
    from PIL import Image
    priya=demo.authenticate('priya@demo.com','Demo123!')
    raj=demo.authenticate('raj@demo.com','Demo123!')
    data=io.BytesIO()
    Image.new('RGB',(32,32),'white').save(data,format='PNG')
    tid=demo.create_ticket(priya,order_id='ORD-87161',category='Product quality',
        title='Backpack stitching',complaint='The stitching on my backpack has come apart.',
        uploads=[('damage.png',data.getvalue())])
    details=demo.ticket_detail(priya,tid)
    assert len(details['attachments'])==1
    photo=details['attachments'][0]
    assert demo.read_attachment(priya,photo.id)==data.getvalue()
    with pytest.raises(demo.SupportError):
        demo.read_attachment(raj,photo.id)
    from supportflow.config import UPLOAD_DIR
    (UPLOAD_DIR / photo.stored_filename).unlink(missing_ok=True)


def test_duplicate_refund_total_guard(demo):
    agent=demo.authenticate('alex@demo.com','Demo123!')
    with pytest.raises(demo.SupportError):
        demo.request_approval(agent,'TKT-10456',10000,'Please authorize another refund against the same order.')
