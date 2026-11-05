"""Stage 4.2: human agents may send informational drafts on escalated cases.

A financial action still requires the dedicated human approval service.
"""
import json
from sqlalchemy import select
import pytest


def _fake_team(snapshot, passages):
    cites=[passages[0]['citation']] if passages else []
    return {
        'query_agent':json.dumps({'category':snapshot['category'],
            'urgency':'Medium','sentiment':'Concerned',
            'summary':'Photo of a damaged grinder was received'}),
        'knowledge_agent':json.dumps({'citations':cites, 'finding':'Policy matches'}),
        'resolution_agent':json.dumps({'reply':'We have received the photo of the damaged grinder. '
                'Our team will review your case and update you.',
            'citations':cites, 'confidence':'medium', 'needs_human':True,
            'requires_refund_or_payment_action':False}),
        'log_agent':json.dumps({'escalation_recommended':True,
            'escalation_reason':'Customer safety concern', 'logged':True}),
    }


def test_agent_can_send_reviewed_update_on_escalated_ticket(demo):
    from supportflow.ai import services as ai
    from supportflow.db import SessionLocal
    from supportflow.models import AuditEvent, Notification
    alex=demo.authenticate('alex@demo.com','Demo123!')
    priya=demo.authenticate('priya@demo.com','Demo123!')
    tid=demo.create_ticket(priya,order_id='ORD-88241',category='Product quality',
        title='Broken grinder blade',complaint='The blade broke when I switched on the grinder.')
    run_id=ai.analyze_ticket(alex,tid,team_runner=_fake_team,override_api_key='fake-key')
    assert ai.latest_analysis(alex,tid)['run'].escalated
    before=demo.unread_count(priya)
    update='We have received your damaged-grinder photo. Our support team is reviewing your report.'
    ai.send_reviewed_ai_draft(alex,tid,run_id,update,human_reviewed=True)
    detail=demo.ticket_detail(priya,tid)
    assert detail['messages'][-1].body==update
    assert detail['ticket'].escalated
    assert detail['ticket'].status=='IN_REVIEW'
    assert detail['ticket'].first_responded_at is not None
    assert demo.unread_count(priya)==before+1
    with SessionLocal() as db:
        assert db.scalar(select(AuditEvent).where(AuditEvent.ticket_id==tid,
            AuditEvent.event_type=='REVIEWED_AI_DRAFT_SENT')) is not None
        assert db.scalar(select(Notification).where(Notification.ticket_id==tid,
            Notification.body==update[:180])) is not None


def test_restricted_action_claim_is_not_sent_directly(demo):
    from supportflow.ai import services as ai
    alex=demo.authenticate('alex@demo.com','Demo123!')
    priya=demo.authenticate('priya@demo.com','Demo123!')
    tid=demo.create_ticket(priya,order_id='ORD-88241',category='Refund',
        title='Refund request for grinder',complaint='I need a refund for this broken grinder item.')
    run_id=ai.analyze_ticket(alex,tid,team_runner=_fake_team,override_api_key='fake-key')
    before=len(demo.ticket_detail(priya,tid)['messages'])
    for claim in ('Your refund has been approved and will be processed.',
                  'We have approved a refund of Rs 2500.',
                  'We will refund the cost to your account.',
                  'Your replacement has been issued and will arrive soon.'):
        with pytest.raises(demo.SupportError,match='approval workflow'):
            ai.send_reviewed_ai_draft(alex,tid,run_id,claim,human_reviewed=True)
        with pytest.raises(demo.SupportError,match='approval workflow'):
            demo.post_ticket_message(alex,tid,claim)
    assert len(demo.ticket_detail(priya,tid)['messages'])==before


def test_review_confirmation_and_roles_are_enforced(demo):
    from supportflow.ai import services as ai
    agent=demo.authenticate('alex@demo.com','Demo123!')
    customer=demo.authenticate('priya@demo.com','Demo123!')
    tid=demo.create_ticket(customer,order_id='ORD-88241',category='Product quality',
        title='Grinder malfunction', complaint='This grinder stopped working after it was delivered.')
    run_id=ai.analyze_ticket(agent,tid,team_runner=_fake_team,override_api_key='fake-key')
    with pytest.raises(demo.SupportError,match='human review'):
        ai.send_reviewed_ai_draft(agent,tid,run_id,'We are looking into your issue.')
    with pytest.raises(demo.SupportError,match='authorized support staff'):
        ai.send_reviewed_ai_draft(customer,tid,run_id,'We are looking into your issue.',human_reviewed=True)


def test_pending_refund_authorization_remains_pending_after_update(demo):
    from supportflow.ai import services as ai
    from supportflow.db import SessionLocal
    from supportflow.models import ApprovalRequest
    agent=demo.authenticate('alex@demo.com','Demo123!')
    customer=demo.authenticate('priya@demo.com','Demo123!')
    tid=demo.create_ticket(customer,order_id='ORD-87161',category='Refund',
        title='Damaged part refund',complaint='My grinder arrived broken and I want a refund.')
    approval_id=demo.request_approval(agent,tid,50000,'We will update you after reviewing the refund request.')
    run_id=ai.analyze_ticket(agent,tid,team_runner=_fake_team,override_api_key='fake-key')
    ai.send_reviewed_ai_draft(agent,tid,run_id,
        'Thank you. Your refund request is awaiting review by our approvals team.',human_reviewed=True)
    with SessionLocal() as db:
        ap=db.get(ApprovalRequest,approval_id)
        assert ap.status=='PENDING'
    assert demo.ticket_detail(customer,tid)['ticket'].status=='AWAITING_APPROVAL'
