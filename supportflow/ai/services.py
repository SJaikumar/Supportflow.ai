"""Authoritative, role-restricted Stage 3 AI analysis persistence and access.

Agent outputs are reviewable internal drafts. They never automatically send a
customer message, create an approval, or authorize a refund.
"""
from __future__ import annotations
import json
import os
import uuid
import logging
from sqlalchemy import select
from supportflow.db import SessionLocal
from supportflow.models import (AIAnalysisRun, AIAnalysisStep, Ticket, AuditEvent,
                                Attachment, PhotoConsent, PhotoInspection, utcnow)
from supportflow.security import may_manage_tickets
from supportflow.services import SupportError, ticket_detail
from supportflow.ai.pipeline import compact_snapshot, initial_query, execute
from supportflow.ai.retrieval import DenseUnavailable, FaissEmbeddings, KnowledgeSearch

AGENT_ORDER=('query_agent','knowledge_agent','resolution_agent','log_agent')



def _safe_ai_failure_reason(exc: Exception) -> str:
    """Helpful user feedback without persisting arbitrary provider error bodies."""
    chain=[]
    cur=exc
    while cur is not None and len(chain)<8:
        chain.append(type(cur).__name__)
        cur=cur.__cause__
    joined=' '.join(chain)
    if 'AuthenticationError' in joined:
        return 'OpenAI rejected the API key. Check OPENAI_API_KEY in .env.'
    if 'PermissionDeniedError' in joined or 'NotFoundError' in joined:
        return 'The OpenAI account cannot access the configured model. Check SUPPORTFLOW_AI_MODEL.'
    if 'RateLimitError' in joined:
        return 'OpenAI rate limit or available quota was exceeded. Check usage/billing and retry.'
    if 'APIConnectionError' in joined or 'APITimeoutError' in joined or 'TimeoutError' in joined:
        return 'OpenAI connection or timeout problem. Check network access and retry.'
    if isinstance(exc, ValueError) and 'returned invalid JSON' in str(exc):
        return str(exc) + '. Try running the analysis again.'
    if isinstance(exc, RuntimeError) and 'did not invoke' in str(exc):
        return str(exc) + '. The agent did not complete the required tool step.'
    if isinstance(exc, RuntimeError) and 'AutoGen packages are missing' in str(exc):
        return 'Required AutoGen packages are missing. Reinstall requirements.txt.'
    return 'AutoGen analysis failed. Examine the first exception in the VS Code terminal for details.'

def _key() -> str:
    from dotenv import load_dotenv
    load_dotenv()
    return os.getenv('OPENAI_API_KEY','').strip()


def model_name() -> str:
    return os.getenv('SUPPORTFLOW_AI_MODEL','gpt-4o-mini')


def embeddings_model() -> str:
    return os.getenv('SUPPORTFLOW_EMBEDDING_MODEL','text-embedding-3-small')


def configured() -> bool:
    return bool(_key())


def retriever(*, include_dense: bool = True, key: str | None = None) -> KnowledgeSearch:
    api_key=key if key is not None else _key()
    dense=FaissEmbeddings(api_key=api_key,model=embeddings_model()) if include_dense and api_key else None
    return KnowledgeSearch(dense=dense)


def preview_policy_search(actor, query: str, *, online: bool = False) -> dict:
    if not may_manage_tickets(actor.role):raise SupportError('Only authorized support staff can inspect knowledge retrieval.')
    q=query.strip()
    if len(q)<3 or len(q)>600:raise SupportError('Use a query of 3–600 characters.')
    return retriever(include_dense=online).search(q)


def latest_analysis(actor, ticket_id: str) -> dict | None:
    if not may_manage_tickets(actor.role):raise SupportError('AI analysis is staff-only.')
    ticket_detail(actor,ticket_id)  # consistent ticket visibility rules
    with SessionLocal() as db:
        run=db.scalar(select(AIAnalysisRun).where(AIAnalysisRun.ticket_id==ticket_id)
                      .order_by(AIAnalysisRun.started_at.desc(),AIAnalysisRun.id.desc()))
        if not run:return None
        steps=db.scalars(select(AIAnalysisStep).where(AIAnalysisStep.run_id==run.id)
                         .order_by(AIAnalysisStep.step_number)).all()
        return {'run':run,'steps':steps,'classification':json.loads(run.classification_json),
                'sources':json.loads(run.citations_json),
                'escalation_reasons':json.loads(run.escalation_reasons_json)}


def batch_latest(actor, ticket_ids: list[str]) -> dict[str,AIAnalysisRun]:
    if not may_manage_tickets(actor.role):raise SupportError('Access denied.')
    if not ticket_ids:return {}
    with SessionLocal() as db:
        runs=db.scalars(select(AIAnalysisRun).where(AIAnalysisRun.ticket_id.in_(ticket_ids))
             .order_by(AIAnalysisRun.started_at.desc(),AIAnalysisRun.id.desc())).all()
        return {r.ticket_id:r for r in reversed(runs)}


def photo_context_for_ticket(actor, ticket_id: str) -> dict:
    """Server-authoritative attachment status and optionally inspected evidence.

    Text agents do not receive original image bytes or unconsented image content.
    A successful inspection is only shared while the customer still consents.
    """
    if not may_manage_tickets(actor.role):
        raise SupportError('Photo analysis context is staff-only.')
    ticket_detail(actor, ticket_id)
    with SessionLocal() as db:
        photos = db.scalars(select(Attachment).where(Attachment.ticket_id == ticket_id)
                            .order_by(Attachment.id)).all()
        findings = []
        consented = 0
        for image in photos:
            if db.get(PhotoConsent, image.id) is None:
                continue
            consented += 1
            observation = db.scalar(select(PhotoInspection).where(
                PhotoInspection.attachment_id == image.id,
                PhotoInspection.status == 'SUCCEEDED').order_by(
                    PhotoInspection.completed_at.desc(), PhotoInspection.id.desc()))
            if observation is None:
                continue
            try:
                info = json.loads(observation.observations_json or '{}')
            except (ValueError, TypeError):
                continue
            findings.append({
                'attachment_id': image.id,
                'summary': str(info.get('summary') or '')[:700],
                'visible_signs': [str(x)[:200] for x in info.get('visible_signs', [])
                                  if isinstance(x, str)][:5],
                'uncertainties': str(info.get('uncertainties') or '')[:400],
                'evidence_type': 'AI visual description; not verified defect or refund entitlement',
            })
        return {
            'attached_count': len(photos),
            'consented_count': consented,
            'inspected_count': len(findings),
            'pending_inspection_count': max(0, consented-len(findings)),
            'awaiting_consent_count': len(photos)-consented,
            'observations': findings,
        }


def analyze_ticket(actor, ticket_id: str, *, team_runner=None, search_engine=None,
                   override_api_key: str | None = None, on_step=None) -> str:
    """Start an AI run, execute outside the DB transaction, persist result atomically.

    Tests can inject a fake team, but the UI path invokes a real AutoGen team.
    """
    if not may_manage_tickets(actor.role):raise SupportError('Only support staff can run AI analysis.')
    record=ticket_detail(actor,ticket_id)
    key=override_api_key if override_api_key is not None else _key()
    if not key:
        raise SupportError('Set OPENAI_API_KEY in your .env file to run the four AutoGen agents.')
    snapshot=compact_snapshot(record)
    snapshot["photo_evidence"] = photo_context_for_ticket(actor, ticket_id)
    run_id=str(uuid.uuid4())
    with SessionLocal.begin() as db:
        db.add(AIAnalysisRun(id=run_id,ticket_id=ticket_id,initiated_by=actor.id,
            status='RUNNING',model=model_name()))
    try:
        kb=search_engine if search_engine is not None else retriever(key=key)
        policy_result=kb.search(initial_query(snapshot))
        outcome=execute(snapshot,policy_result,api_key=key,model=model_name(),team_runner=team_runner,on_step=on_step)
        with SessionLocal.begin() as db:
            run=db.get(AIAnalysisRun,run_id)
            run.status='SUCCEEDED'
            run.retrieval_mode=outcome['retrieval_mode']
            run.classification_json=json.dumps(outcome['classification'],ensure_ascii=False)
            run.citations_json=json.dumps(outcome['sources'],ensure_ascii=False)
            run.draft_response=outcome['draft_response']
            run.confidence=outcome['confidence']
            run.escalated=outcome['escalated']
            run.escalation_reasons_json=json.dumps(outcome['escalation_reasons'],ensure_ascii=False)
            run.completed_at=utcnow()
            for i,name in enumerate(AGENT_ORDER,1):
                db.add(AIAnalysisStep(run_id=run_id,step_number=i,agent_name=name,
                    output_json=json.dumps(outcome['agent_outputs'][name],ensure_ascii=False)))
            t=db.get(Ticket,ticket_id)
            if outcome['escalated']:
                t.escalated=True
                if t.status in ('NEW','REOPENED'):
                    t.status='IN_REVIEW'  # NOT AWAITING_APPROVAL without a real ApprovalRequest
                t.updated_at=utcnow()
            db.add(AuditEvent(ticket_id=ticket_id,actor_id=actor.id,
                event_type='AI_ANALYSIS_COMPLETED',
                details=f'Run {run_id}; verified sources: {len(outcome["sources"])}; '
                        f'escalated: {outcome["escalated"]}; no customer message sent'))
    except Exception as exc:
        reason=_safe_ai_failure_reason(exc)
        # The terminal retains the traceback; the database stores only a safe hint.
        logging.getLogger('supportflow.ai').error(
            'AI analysis %s failed: %s (%s)',run_id,reason,type(exc).__name__,exc_info=True)
        with SessionLocal.begin() as db:
            run=db.get(AIAnalysisRun,run_id)
            run.status='FAILED'
            run.error=reason
            run.completed_at=utcnow()
            db.add(AuditEvent(ticket_id=ticket_id,actor_id=actor.id,event_type='AI_ANALYSIS_FAILED',
                              details=f'Run {run_id} failed ({type(exc).__name__})'))
        raise SupportError('AI analysis failed: '+reason) from exc
    return run_id


def send_reviewed_ai_draft(actor, ticket_id: str, run_id: str, edited_reply: str,
                           *, human_reviewed: bool = False) -> None:
    """Staff may send a reviewed customer update even when the case is escalated.

    The informational reply does not approve refunds, resolve the ticket, or
    close an approval. Explicit staff confirmation and server-side action-claim
    validation protect the dedicated approval workflow.
    """
    if not may_manage_tickets(actor.role):
        raise SupportError('AI replies can only be sent by authorized support staff.')
    from supportflow.services import post_ticket_message
    post_ticket_message(actor,ticket_id,edited_reply,
                        ai_run_id=run_id,human_reviewed=human_reviewed)
