"""Non-LLM escalation gates and validated agent-result parsing."""
from __future__ import annotations
import json
import re

IMPORTANT = re.compile(r'\b(fraud|scam|chargeback|charged (?:twice|three times|multiple times)|unauthori[sz]ed|stolen card|lawsuit|lawyer|legal action|court|bank dispute|dispute|threat|unsafe|fire|smoke|explod|injur|electrocution)\b',re.I)
FURIOUS = re.compile(r'\b(furious|enraged|outraged|extremely angry|very angry|unacceptable|disgusted)\b',re.I)


def parse_agent_json(text: str) -> dict:
    """Read a JSON object; strip markdown fences and the log-agent stop token."""
    if not isinstance(text,str):raise ValueError('Agent response was not text')
    text=text.replace('SUPPORTFLOW_LOGGED','').strip()
    if text.startswith('```'):
        text=re.sub(r'^```(?:json)?\s*','',text,flags=re.I)
        text=re.sub(r'\s*```$','',text).strip()
    try: value=json.loads(text)
    except json.JSONDecodeError as exc:raise ValueError('Agent did not return a JSON object') from exc
    if not isinstance(value,dict):raise ValueError('Agent JSON must be an object')
    return value


def decide_escalation(*, ticket_category: str, ticket_priority: str, complaint: str,
                      classification: dict, resolution: dict, citations: list[dict]) -> tuple[bool,list[str]]:
    """Conservative escalation decision. LLM output cannot bypass these gates."""
    reasons=[]
    category=ticket_category.strip().lower()
    text=(complaint or '')
    if ticket_priority=='P1' or str(classification.get('urgency','')).lower() in ('high','critical'):
        reasons.append('High urgency')
    if category in ('refund','billing') or bool(resolution.get('requires_refund_or_payment_action')):
        reasons.append('Refund/payment action requires human authorization')
    if IMPORTANT.search(text):reasons.append('Sensitive complaint / dispute / safety or legal terms')
    if FURIOUS.search(text) or str(classification.get('sentiment','')).lower() in ('very angry','furious','extremely angry'):
        reasons.append('Customer expresses serious frustration')
    if not citations:reasons.append('No matching verified company policy')
    if str(resolution.get('confidence','')).lower() not in ('high','medium'):
        reasons.append('Low or unknown answer confidence')
    if resolution.get('needs_human') is True:reasons.append('AI flagged human review')
    return bool(reasons), list(dict.fromkeys(reasons))


def validated_outcome(*, ticket_category: str, ticket_priority: str, complaint: str,
                      replies: dict[str,str], allowed_citations: list[dict]) -> dict:
    needed={'query_agent','knowledge_agent','resolution_agent','log_agent'}
    if set(replies)!=needed:raise ValueError('All four distinct AutoGen agents must finish')
    parsed={key:parse_agent_json(value) for key,value in replies.items()}
    q=parsed['query_agent']
    r=parsed['resolution_agent']
    response=r.get('reply','')
    if not isinstance(response,str) or not response.strip():
        raise ValueError('Resolution Agent did not produce a reply')
    approved_sources={p['citation'] for p in allowed_citations}
    requested_sources=r.get('citations',[])
    if not isinstance(requested_sources,list):requested_sources=[]
    cited=[p for p in allowed_citations if p['citation'] in requested_sources]
    if not cited:
        response=('Thank you for contacting support. We could not verify a policy-based answer '
                  'for your request. A member of our team will review your case and follow up.')
    escalated,reasons=decide_escalation(ticket_category=ticket_category,ticket_priority=ticket_priority,
        complaint=complaint,classification=q,resolution=r,citations=cited)
    return {'classification':{'category':str(q.get('category',ticket_category))[:70],
                'urgency':str(q.get('urgency','unknown'))[:25],
                'sentiment':str(q.get('sentiment','unknown'))[:40],
                'summary':str(q.get('summary',''))[:700]},
            'draft_response':response[:3500],
            'confidence':str(r.get('confidence','low')).lower()[:20],
            'sources':cited,
            'escalated':escalated,
            'escalation_reasons':reasons,
            'agent_outputs':parsed}
