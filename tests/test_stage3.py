"""Stage 3 tests run offline with injected AutoGen replies (no API spend)."""
import json
from pathlib import Path
import pytest
from sqlalchemy import inspect, select, func

from supportflow.ai.retrieval import (Passage, BM25, KnowledgeSearch,
                                     reciprocal_rank_fusion, tokens)
from supportflow.ai.rules import parse_agent_json, decide_escalation
from supportflow.ai.pipeline import redact_payment_information, compact_snapshot


def test_doc_index_and_citation_quality():
    docs=KnowledgeSearch()
    assert len(docs.passages)>=4
    result=docs.search('I received a damaged appliance. How do I request a refund?')
    assert result['mode']=='BM25 only'
    assert result['passages']
    assert any(p['filename']=='refund_policy.md' for p in result['passages'])
    assert all('#p' in p['citation'] and p['passage'] for p in result['passages'])
    assert docs.search('branded corporate gift card program') ['passages']==[]


def test_reciprocal_rank_fusion_deterministic():
    ranked=reciprocal_rank_fusion([[1,2],[2,1],[2,3]])
    assert ranked[0][0]==2
    assert len({p[0] for p in ranked})==3
    assert 'refund' in tokens('Need a refund for my order')


def test_parse_json_and_redaction():
    assert parse_agent_json('```json\n{"logged":true}\n```')['logged']
    assert parse_agent_json('{"logged":true}\nSUPPORTFLOW_LOGGED')['logged']
    with pytest.raises(ValueError):parse_agent_json('no usable json')
    assert '4111111111111111' not in redact_payment_information('My card 4111111111111111 was charged')
    assert '777777' not in redact_payment_information('otp:777777 sent')


def _fake_agent(snapshot, passages, *, low=False, cite=True, angry=False):
    ids=[passages[0]['citation']] if cite and passages else []
    return {'query_agent':json.dumps({'category':snapshot['category'],
             'urgency':'High' if angry else 'Medium','sentiment':'Angry' if angry else 'Calm','summary':'Review customer complaint'}),
         'knowledge_agent':json.dumps({'citations':ids,'finding':'Company policy located'}),
         'resolution_agent':json.dumps({'reply':'Please follow the verified policy. A reviewer will assess the case.',
              'citations':ids,'confidence':'low' if low else 'high',
              'needs_human':False,'requires_refund_or_payment_action':False}),
         'log_agent':'{"escalation_recommended":false,"escalation_reason":"","logged":true}\nSUPPORTFLOW_LOGGED'}


def test_rule_guards_high_risk_even_when_ai_claims_no_escalation():
    escalated,reasons=decide_escalation(ticket_category='Billing',ticket_priority='P1',
        complaint='My card was charged three times and I will contact a lawyer!',
        classification={'urgency':'Low'},resolution={'confidence':'high','needs_human':False},
        citations=[{'citation':'refund_policy.md#p1'}])
    assert escalated and len(reasons)>=2
    escalated,rs=decide_escalation(ticket_category='Account',ticket_priority='P3',
        complaint='Please help me access my account',classification={'urgency':'Medium'},
        resolution={'confidence':'low'},citations=[])
    assert escalated and 'No matching verified company policy' in rs


def test_run_persists_four_steps_and_only_internal_draft(demo):
    from supportflow.ai import services as ai
    from supportflow.db import engine, SessionLocal
    from supportflow.models import AIAnalysisRun,AIAnalysisStep,TicketMessage,Refund
    agent=demo.authenticate('alex@demo.com','Demo123!')
    customer=demo.authenticate('priya@demo.com','Demo123!')
    assert {'ai_analysis_runs','ai_analysis_steps'} <= set(inspect(engine).get_table_names())
    before=demo.ticket_detail(customer,'TKT-10456')
    msg_count,refund_count=len(before['messages']),len(before['refunds'])
    run_id=ai.analyze_ticket(agent,'TKT-10456',team_runner=_fake_agent,
                              override_api_key='fake-test-key')
    result=ai.latest_analysis(agent,'TKT-10456')
    assert result['run'].id==run_id and result['run'].status=='SUCCEEDED'
    assert [s.agent_name for s in result['steps']]==['query_agent','knowledge_agent','resolution_agent','log_agent']
    assert result['sources']
    after=demo.ticket_detail(customer,'TKT-10456')
    assert len(after['messages'])==msg_count
    assert len(after['refunds'])==refund_count
    with pytest.raises(demo.SupportError):ai.latest_analysis(customer,'TKT-10456')
    with pytest.raises(demo.SupportError):ai.analyze_ticket(customer,'TKT-10456',team_runner=_fake_agent,override_api_key='fake')


def test_missing_policy_forces_escalation_and_safe_draft(demo):
    from supportflow.ai import services as ai
    priya=demo.authenticate('priya@demo.com','Demo123!')
    agent=demo.authenticate('alex@demo.com','Demo123!')
    tid=demo.create_ticket(priya,order_id=None,category='Other',
        title='Enterprise custom gift card program',
        complaint='Can you design custom gift cards for 500 employees?')
    rid=ai.analyze_ticket(agent,tid,team_runner=_fake_agent,override_api_key='fake')
    result=ai.latest_analysis(agent,tid)
    assert result['run'].id==rid and result['run'].escalated
    assert result['sources']==[]
    assert 'could not verify' in result['run'].draft_response.lower()
    assert result['run'].status=='SUCCEEDED'
    assert demo.ticket_detail(priya,tid)['ticket'].status!='AWAITING_APPROVAL'


def test_pipeline_failure_is_logged_without_customer_side_effect(demo):
    from supportflow.ai import services as ai
    agent=demo.authenticate('alex@demo.com','Demo123!')
    priya=demo.authenticate('priya@demo.com','Demo123!')
    before=len(demo.ticket_detail(priya,'TKT-10456')['messages'])
    def failed(snapshot,passages):
        raise RuntimeError('secret-provider-error-text-must-not-persist')
    with pytest.raises(demo.SupportError):
        ai.analyze_ticket(agent,'TKT-10456',team_runner=failed,override_api_key='fake')
    latest=ai.latest_analysis(agent,'TKT-10456')
    assert latest['run'].status=='FAILED'
    assert 'secret-provider-error' not in latest['run'].error
    assert len(demo.ticket_detail(priya,'TKT-10456')['messages'])==before
