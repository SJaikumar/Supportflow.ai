"""Stage 2 tests: history isolation, additive schema, commitments, audit and refund ledger."""
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
import pytest
from sqlalchemy import select, func


def roles(demo):
    return (demo.authenticate('priya@demo.com','Demo123!'),
            demo.authenticate('alex@demo.com','Demo123!'),
            demo.authenticate('maya@demo.com','Demo123!'),
            demo.authenticate('admin@demo.com','Demo123!'))


def test_schema_extensions_and_idempotent_demo_seed(demo):
    from supportflow.db import engine, initialize
    from supportflow.seed import seed_stage2_examples_if_missing
    from sqlalchemy import inspect
    initialize()
    required={'ticket_counters','order_events','customer_notes','commitments','approval_decisions',
              'refund_events','outbox_events','sla_policy_changes','ticket_links','seed_markers'}
    assert required <= set(inspect(engine).get_table_names())
    assert not seed_stage2_examples_if_missing()
    assert not seed_stage2_examples_if_missing()


def test_notes_are_staff_only_and_customer_metrics_are_factual(demo):
    priya,agent,maya,admin=roles(demo)
    customer=demo.customer_for_user(priya)
    with pytest.raises(demo.SupportError):
        demo.customer_detail(priya,customer.id)
    with pytest.raises(demo.SupportError):
        demo.add_customer_note(priya,customer.id,'Try to create an internal support note.')
    marker='Stage 2: reviewed prior order-based requests, no risk determination.'
    note_id=demo.add_customer_note(agent,customer.id,marker)
    info=demo.customer_detail(maya,customer.id)
    assert any(n.id==note_id and n.text==marker for n in info['notes'])
    assert info['insights']['orders_placed']==18
    assert info['insights']['refund_orders']>=3
    assert info['insights']['eligible_delivered_orders']>0
    assert 0 <= info['insights']['refund_request_rate_pct'] <= 100


def test_commitments_are_durable_and_private_notes_not_leaked(demo):
    priya,agent,maya,_=roles(demo)
    from supportflow.models import utcnow
    public_id=demo.create_commitment(agent,'TKT-10456','Provide a confirmed update on this damaged item.',
                                     utcnow()+timedelta(hours=2),customer_visible=True)
    private_id=demo.create_commitment(agent,'TKT-10456','Check internal refund ledger during team review.',
                                     utcnow()+timedelta(hours=5),customer_visible=False)
    customer_view=demo.ticket_detail(priya,'TKT-10456')
    agent_view=demo.ticket_detail(agent,'TKT-10456')
    assert any(x.id==public_id for x in customer_view['commitments'])
    assert all(x.id!=private_id for x in customer_view['commitments'])
    assert any(x.id==private_id for x in agent_view['commitments'])
    demo.complete_commitment(agent,public_id)
    with pytest.raises(demo.SupportError):demo.complete_commitment(agent,public_id)
    assert any(x.id==public_id and x.completed_at for x in demo.ticket_detail(priya,'TKT-10456')['commitments'])
    with pytest.raises(demo.SupportError):demo.create_commitment(priya,'TKT-10456','Unauthorized promise here.',
                                                                  utcnow()+timedelta(hours=1))


def test_link_same_order_contacts_and_atomic_ticket_counter(demo):
    priya,agent,_,_=roles(demo)
    def build(i):
        return demo.create_ticket(priya,order_id='ORD-87161',category='Product quality',
            title=f'Stitching question {i}',complaint='The backpack seams need inspection and support.')
    with ThreadPoolExecutor(max_workers=3) as pool:
        ids=list(pool.map(build,range(3)))
    assert len(set(ids))==3
    assert list(map(lambda x:int(x[4:]),sorted(ids)))==sorted(int(x[4:]) for x in ids)
    prior=demo.related_tickets(agent,ids[-1])
    assert set(ids[:-1]) <= {t.id for t in prior}
    assert all(t.customer_id==demo.customer_for_user(priya).id for t in prior)
    raj=demo.authenticate('raj@demo.com','Demo123!')
    with pytest.raises(demo.SupportError):demo.related_tickets(raj,ids[-1])


def test_admin_sla_policy_is_versioned_and_only_new_tickets_change(demo):
    priya,agent,maya,admin=roles(demo)
    original=demo.ticket_detail(priya,'TKT-10096')['ticket'].first_response_due
    with pytest.raises(demo.SupportError):demo.update_sla_policy(agent,'P3',20,120)
    demo.update_sla_policy(admin,'P3',20,120)
    tid=demo.create_ticket(priya,order_id=None,category='Account',title='Cannot access account',
                           complaint='Login works on desktop but not on my mobile device.')
    ticket=demo.ticket_detail(priya,tid)['ticket']
    assert ticket.priority=='P3'
    assert (ticket.first_response_due-ticket.created_at).total_seconds()==20*60
    assert (ticket.resolution_due-ticket.created_at).total_seconds()==120*60
    assert demo.ticket_detail(priya,'TKT-10096')['ticket'].first_response_due==original
    from supportflow.db import SessionLocal
    from supportflow.models import SLAPolicyChange
    with SessionLocal() as db:
        assert db.scalar(select(func.count()).select_from(SLAPolicyChange)) >= 1


def test_approval_decision_refund_history_and_outbox_are_transactional(demo):
    priya,agent,maya,_=roles(demo)
    tid=demo.create_ticket(priya,order_id='ORD-87161',category='Refund',
                           title='Backpack refund review',
                           complaint='The backpack stitching appears broken and I request a refund.')
    aid=demo.request_approval(agent,tid,50000,
        'We will review and process a simulated partial refund when approved.')
    before=demo.unread_count(priya)
    demo.decide_approval(maya,aid,approve=True,
        edited_message='A partial simulated refund of ₹500 is approved and is being processed.')
    record=demo.ticket_detail(maya,tid)
    assert len(record['approval_decisions'])==1
    assert record['approval_decisions'][0].outcome=='APPROVED'
    refund=record['refunds'][0]
    assert refund.status=='PROCESSING'
    assert demo.unread_count(priya)==before+1
    with pytest.raises(demo.SupportError):
        demo.decide_approval(maya,aid,approve=True,edited_message='Repeated approval is not valid.')
    events=demo.refund_history(maya,refund.id)
    assert [x.status for x in events]==['PENDING_APPROVAL','PROCESSING']
    demo.complete_simulated_refund(maya,refund.id)
    assert [x.status for x in demo.refund_history(priya,refund.id)]==[
        'PENDING_APPROVAL','PROCESSING','COMPLETED']
    from supportflow.db import SessionLocal
    from supportflow.models import OutboxEvent,Order,ApprovalDecision
    with SessionLocal() as db:
        assert db.scalar(select(func.count()).select_from(OutboxEvent).where(
            OutboxEvent.dedupe_key==f'approval:{aid}:decision'))==1
        assert db.scalar(select(func.count()).select_from(OutboxEvent).where(
            OutboxEvent.dedupe_key==f'refund:{refund.id}:complete'))==1
        assert db.get(Order,'ORD-87161').status != 'REFUNDED' # Partial refund only
        assert db.scalar(select(func.count()).select_from(ApprovalDecision).where(
            ApprovalDecision.approval_id==aid))==1


def test_order_event_validation_and_staff_access(demo):
    priya,agent,_,_=roles(demo)
    with pytest.raises(demo.SupportError):
        demo.add_order_event(priya,'ORD-88102','CARRIER_UPDATE','Courier investigated delay')
    event_id=demo.add_order_event(agent,'ORD-88102','CARRIER_UPDATE',
                                   'Demo courier record indicates an investigation is in progress.')
    staff=demo.ticket_detail(agent,'TKT-10398')
    cust=demo.ticket_detail(priya,'TKT-10398')
    assert any(ev.id==event_id for ev in staff['order_events'])
    assert not cust['order_events']
