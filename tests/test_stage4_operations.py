"""Stage 4 operational acceptance tests. All API requests are mocked or injected."""
from datetime import datetime, timedelta
import io
import json
import pytest
from PIL import Image
from sqlalchemy import select, func


def _accounts(demo):
    return (demo.authenticate('priya@demo.com', 'Demo123!'),
            demo.authenticate('alex@demo.com', 'Demo123!'),
            demo.authenticate('maya@demo.com', 'Demo123!'))


def _new_ticket(demo):
    priya, _, _ = _accounts(demo)
    return demo.create_ticket(priya, order_id='ORD-87161', category='Product quality',
                              title='Stage four test case',
                              complaint='The material arrived cracked and I require an investigation.')


def test_stage4_tables_are_additive(demo):
    from sqlalchemy import inspect
    from supportflow.db import engine
    table_names = set(inspect(engine).get_table_names())
    for table in ('sla_events','staff_alerts','commitment_reminders','photo_inspections',
                  'photo_consents','worker_runs'):
        assert table in table_names


def test_sla_breach_creates_durable_alert_and_portal_message_exactly_once(demo):
    from supportflow.db import SessionLocal
    from supportflow.models import SLAEvent, StaffAlert, OutboxEvent, Ticket
    from supportflow.operations import run_tick, staff_alerts
    priya, agent, _ = _accounts(demo)
    tid = _new_ticket(demo)
    with SessionLocal() as db:
        ticket = db.get(Ticket,tid)
        now = ticket.first_response_due + timedelta(minutes=2)
    run_tick(now=now)
    with SessionLocal() as db:
        events = db.scalars(select(SLAEvent).where(SLAEvent.ticket_id == tid,
            SLAEvent.obligation == 'RESPONSE')).all()
        assert {e.threshold_pct for e in events} == {75,90,100}
        alert = db.scalar(select(StaffAlert).where(StaffAlert.dedupe_key == f'sla:{tid}:response'))
        assert alert and alert.severity == 'CRITICAL'
        assert db.scalar(select(func.count()).select_from(OutboxEvent).where(
            OutboxEvent.dedupe_key == f'sla:{tid}:response:breached')) == 1
    run_tick(now=now)
    with SessionLocal() as db:
        assert db.scalar(select(func.count()).select_from(SLAEvent).where(
            SLAEvent.ticket_id==tid,SLAEvent.obligation=='RESPONSE')) == 3
        assert db.scalar(select(func.count()).select_from(OutboxEvent).where(
            OutboxEvent.dedupe_key == f'sla:{tid}:response:breached')) == 1
    with pytest.raises(demo.SupportError):
        staff_alerts(priya)
    assert any(a.ticket_id == tid for a in staff_alerts(agent))


def test_acknowledge_alert_is_idempotent_and_staff_only(demo):
    from supportflow.db import SessionLocal
    from supportflow.models import StaffAlert
    from supportflow.operations import acknowledge_alert
    priya, agent, _ = _accounts(demo)
    with SessionLocal() as db:
        alert = db.scalar(select(StaffAlert).where(StaffAlert.cleared_at.is_(None)))
        assert alert is not None
        aid = alert.id
    with pytest.raises(demo.SupportError):
        acknowledge_alert(priya, aid)
    acknowledge_alert(agent, aid)
    acknowledge_alert(agent, aid)
    with SessionLocal() as db:
        row = db.get(StaffAlert, aid)
        assert row.acknowledged_by == agent.id


def test_commitment_reminders_and_customer_overdue_notice_not_repeated(demo):
    from supportflow.db import SessionLocal
    from supportflow.models import Commitment, CommitmentReminder, OutboxEvent
    from supportflow.operations import run_tick
    priya, agent, _ = _accounts(demo)
    tid = _new_ticket(demo)
    from supportflow.models import utcnow
    due = utcnow() + timedelta(hours=2)
    cid = demo.create_commitment(agent,tid,'Provide verified order tracking and customer update',due)
    run_tick(now=due - timedelta(minutes=30))
    with SessionLocal() as db:
        assert db.scalar(select(func.count()).select_from(CommitmentReminder).where(
            CommitmentReminder.commitment_id == cid,
            CommitmentReminder.event_type == 'DUE_SOON')) == 1
    run_tick(now=due + timedelta(minutes=1))
    run_tick(now=due + timedelta(minutes=1))
    with SessionLocal() as db:
        assert db.scalar(select(func.count()).select_from(CommitmentReminder).where(
            CommitmentReminder.commitment_id == cid,
            CommitmentReminder.event_type == 'OVERDUE')) == 1
        assert db.scalar(select(func.count()).select_from(OutboxEvent).where(
            OutboxEvent.dedupe_key == f'commitment:{cid}:overdue')) == 1
    demo.complete_commitment(agent,cid)
    run_tick()
    with SessionLocal() as db:
        from supportflow.models import StaffAlert
        alert=db.scalar(select(StaffAlert).where(StaffAlert.dedupe_key==f'commitment:{cid}'))
        assert alert.cleared_at is not None


def _test_photo():
    buffer=io.BytesIO()
    Image.new('RGB',(80,80),(239,239,239)).save(buffer,format='PNG')
    return buffer.getvalue()


def test_photo_inspection_requires_consent_and_human_role(demo):
    from supportflow.photo import grant_photo_consent, inspect_photo, photo_details
    from supportflow.db import SessionLocal
    from supportflow.models import PhotoInspection
    priya, agent, _ = _accounts(demo)
    raj = demo.authenticate('raj@demo.com','Demo123!')
    tid=demo.create_ticket(priya,order_id='ORD-87161',category='Product quality',
        title='Cracked component with image',complaint='The product appears to have a crack near the base.',
        uploads=[('item.png',_test_photo())])
    photo=photo_details(agent,tid)[0]
    attachment_id=photo['attachment'].id
    assert not photo['consented']
    with pytest.raises(demo.SupportError):
        inspect_photo(agent,attachment_id,inspector=lambda b: {'summary':'looks cracked'})
    with pytest.raises(demo.SupportError):
        grant_photo_consent(raj,attachment_id)
    grant_photo_consent(priya,attachment_id)
    with pytest.raises(demo.SupportError):
        inspect_photo(priya,attachment_id,inspector=lambda b: {'summary':'looks cracked'})
    did=inspect_photo(agent,attachment_id,inspector=lambda b: {
        'summary':'A crack appears visible along the cover edge.',
        'visible_signs':['A dark linear separation'],
        'uncertainties':'Photo cannot establish cause or time of damage.',
        'human_review_required':False})
    with SessionLocal() as db:
        report=db.get(PhotoInspection,did)
        data=json.loads(report.observations_json)
        assert report.status=='SUCCEEDED'
        assert data['human_review_required'] is True
        assert 'refund' in data['caveat']
    # A customer can read their own photos but not staff-only model findings.
    assert photo_details(priya,tid)[0]['inspections']==[]
    from supportflow.config import UPLOAD_DIR
    (UPLOAD_DIR/photo['attachment'].stored_filename).unlink(missing_ok=True)


def test_photo_optin_during_ticket_submission(demo):
    from supportflow.photo import photo_details, revoke_photo_consent
    from supportflow.config import UPLOAD_DIR
    priya,_,_=_accounts(demo)
    tid=demo.create_ticket(priya,order_id='ORD-87161',category='Product quality',
        title='Scratched product photo',complaint='I found scratches on the delivered item, please examine.',
        uploads=[('test.png',_test_photo())],consent_photo_ai=True)
    item=photo_details(priya,tid)[0]
    assert item['consented'] is True
    revoke_photo_consent(priya,item['attachment'].id)
    assert photo_details(priya,tid)[0]['consented'] is False
    (UPLOAD_DIR/item['attachment'].stored_filename).unlink(missing_ok=True)


def test_background_simulated_refund_requires_human_approval(demo):
    from supportflow.operations import run_tick
    from supportflow.db import SessionLocal
    from supportflow.models import Refund, Ticket, OutboxEvent
    priya,agent,maya = _accounts(demo)
    tid=_new_ticket(demo)
    aid=demo.request_approval(agent,tid,5000,
        'Your refund request is being sent for human approval and review.')
    run_tick(process_refunds=True,refund_delay_seconds=0)
    with SessionLocal() as db:
        refund=db.scalar(select(Refund).where(Refund.approval_id==aid))
        assert refund.status=='PENDING_APPROVAL'
    demo.decide_approval(maya,aid,approve=True,
        edited_message='Your refund is approved and will be completed in the SupportFlow simulation.')
    # Without the auto-refund flag, no automated refund executes.
    run_tick(process_refunds=False)
    with SessionLocal() as db:
        assert db.scalar(select(Refund).where(Refund.approval_id==aid)).status=='PROCESSING'
    run_tick(process_refunds=True,refund_delay_seconds=0)
    run_tick(process_refunds=True,refund_delay_seconds=0)
    with SessionLocal() as db:
        refund=db.scalar(select(Refund).where(Refund.approval_id==aid))
        assert refund.status=='COMPLETED'
        ticket=db.get(Ticket,tid)
        assert ticket.status=='RESOLVED'
        assert db.scalar(select(func.count()).select_from(OutboxEvent).where(
            OutboxEvent.dedupe_key==f'refund:{refund.id}:complete')) == 1


def test_worker_run_health_is_staff_only(demo):
    from supportflow.operations import worker_health, run_tick
    priya,agent,_=_accounts(demo)
    with pytest.raises(demo.SupportError):
        worker_health(priya)
    run_tick()
    report=worker_health(agent)
    assert report['last_run'].status=='SUCCEEDED'
