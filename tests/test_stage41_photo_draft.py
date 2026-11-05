"""Image-aware text drafts and direct-send restrictions (no network/API spend)."""
import io
import json
import pytest
from PIL import Image

from supportflow.ai.pipeline import reconcile_photo_draft


def png_bytes():
    image=Image.new('RGB', (20,20), 'white')
    stream=io.BytesIO()
    image.save(stream, format='PNG')
    return stream.getvalue()


def fake_team(snapshot,passages):
    ids=[passages[0]['citation']] if passages else []
    return {
        'query_agent':json.dumps({'category':snapshot['category'],
           'urgency':'Low','sentiment':'Neutral','summary':'Customer needs help'}),
        'knowledge_agent':json.dumps({'citations':ids,'finding':'Relevant policy found'}),
        'resolution_agent':json.dumps({
            'reply':'Please attach a photo of the damaged product to proceed.',
            'citations':ids,'confidence':'high','needs_human':False,
            'requires_refund_or_payment_action':False}),
        'log_agent':json.dumps({'escalation_recommended':False,
            'escalation_reason':'','logged':True}),
    }


def test_reconcile_does_not_request_existing_initial_photo():
    existing={'attached_count':1,'inspected_count':0}
    result=reconcile_photo_draft('You have to attach the image before we can help.',existing)
    assert 'attach the image' not in result.lower()
    assert 'already attached' in result.lower()
    assert 'awaiting review' in result.lower()
    assert reconcile_photo_draft('Please upload a photo.', {'attached_count':0}) == 'Please upload a photo.'
    assert 'additional' in reconcile_photo_draft('Can you upload an additional photo of the label?', existing)


def test_existing_unconsented_image_is_mentioned_without_exposing_content(demo):
    from supportflow.ai import services as ai
    from supportflow.photo import photo_details
    from supportflow.config import UPLOAD_DIR
    customer=demo.authenticate('priya@demo.com','Demo123!')
    staff=demo.authenticate('alex@demo.com','Demo123!')
    tid=demo.create_ticket(customer,order_id='ORD-87161',category='Product quality',
        title='Image already included',complaint='I uploaded a photo of my broken item and need your help.',
        uploads=[('damage.png',png_bytes())],consent_photo_ai=False)
    snapshots=[]
    def runner(snapshot, passages):
        snapshots.append(snapshot)
        return fake_team(snapshot,passages)
    try:
        run_id=ai.analyze_ticket(staff,tid,team_runner=runner,override_api_key='fake-key')
        detail=ai.latest_analysis(staff,tid)
        assert detail['run'].id==run_id
        evidence=snapshots[0]['photo_evidence']
        assert evidence['attached_count']==1
        assert evidence['inspected_count']==0
        assert evidence['awaiting_consent_count']==1
        assert evidence['observations']==[]
        assert 'already attached' in detail['run'].draft_response.lower()
        assert 'please attach' not in detail['run'].draft_response.lower()
        with pytest.raises(demo.SupportError):
            ai.photo_context_for_ticket(customer,tid)
    finally:
        for item in photo_details(staff,tid):
            (UPLOAD_DIR/item['attachment'].stored_filename).unlink(missing_ok=True)


def test_visual_inspection_feeds_existing_photo_context_only_with_active_consent(demo):
    from supportflow.ai import services as ai
    from supportflow.photo import photo_details, inspect_photo, revoke_photo_consent
    from supportflow.config import UPLOAD_DIR
    customer=demo.authenticate('priya@demo.com','Demo123!')
    staff=demo.authenticate('alex@demo.com','Demo123!')
    tid=demo.create_ticket(customer,order_id='ORD-87161',category='Product quality',
        title='Visual damage inspection',complaint='I attached the cracked product photo for review.',
        uploads=[('crack.png',png_bytes())],consent_photo_ai=True)
    attachment=photo_details(staff,tid)[0]['attachment']
    try:
        inspect_photo(staff,attachment.id,inspector=lambda _: {
            'summary':'The outer panel appears cracked',
            'visible_signs':['Linear separation visible along edge'],
            'uncertainties':'Cause and damage timing not verifiable'})
        evidence=ai.photo_context_for_ticket(staff,tid)
        assert evidence['attached_count']==1 and evidence['inspected_count']==1
        assert 'appears cracked' in evidence['observations'][0]['summary']
        assert 'damage timing not verifiable' in evidence['observations'][0]['uncertainties']
        revoke_photo_consent(customer,attachment.id)
        evidence_after=ai.photo_context_for_ticket(staff,tid)
        assert evidence_after['attached_count']==1
        assert evidence_after['inspected_count']==0
        assert evidence_after['observations']==[]
    finally:
        (UPLOAD_DIR/attachment.stored_filename).unlink(missing_ok=True)


def test_escalated_ai_draft_cannot_be_sent_directly(demo):
    from supportflow.ai import services as ai
    staff=demo.authenticate('alex@demo.com','Demo123!')
    customer=demo.authenticate('priya@demo.com','Demo123!')
    tid=demo.create_ticket(customer,order_id='ORD-87161',category='Refund',
        title='Refund approval required',complaint='Please consider my refund request after review.')
    run_id=ai.analyze_ticket(staff,tid,team_runner=fake_team,override_api_key='fake-key')
    detail=ai.latest_analysis(staff,tid)
    assert detail['run'].escalated
    before=len(demo.ticket_detail(customer,tid)['messages'])
    with pytest.raises(demo.SupportError, match='human review'):
        ai.send_reviewed_ai_draft(staff,tid,run_id,'We have reviewed your damaged item.')
    assert len(demo.ticket_detail(customer,tid)['messages'])==before
