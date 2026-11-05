"""Conservative content checks for regular staff-to-customer updates.

These checks do not authorize or execute financial actions. They only prevent
obvious unapproved-action claims from being sent through the regular reply
composer. Refund authorization always happens via decide_approval().
"""
from __future__ import annotations
import re

# Bounded, same-sentence patterns avoid unnecessarily blocking discussions of
# refund *requests*. This is an extra guard, not an LLM-based safety guarantee.
_ACTION = r'(?:refund|reimburs\w*|payment|chargeback|replacement|compensation|store\s+credit)'
_OUTCOME = r'(?:approved|authorized|authorised|issued|processed|completed|initiated|executed|paid|refunded|reimbursed|granted)'
_VERBAL_CLAIMS = (
    re.compile(r'\b(?:your|the|a)\s+'+_ACTION+r'\b[^.!?\n]{0,85}\b'+_OUTCOME+r'\b',re.I),
    re.compile(r'\b(?:we|I)\s+(?:have|had|will|shall|already|are\s+going\s+to)\s+'
               +_OUTCOME+r'\b[^.!?\n]{0,85}\b'+_ACTION+r'\b',re.I),
    re.compile(r'\b(?:we|I)\s+(?:will|shall|have|already)\s+(?:refund|reimburse|compensate)\b',re.I),
    re.compile(r'\b'+_ACTION+r'\b[^.!?\n]{0,75}\b(?:will\s+be|has\s+been|was\s+just|is\s+now)\s+'
               +_OUTCOME+r'\b',re.I),
)


def validate_informational_update(body: str) -> None:
    """Disallow apparent refund/compensation authorizations in ordinary replies.

    A human agent can acknowledge an escalated case and tell the customer what
    is being reviewed. Only an authorized approver can perform the decision.
    """
    from supportflow.services import SupportError
    if any(pattern.search(body) for pattern in _VERBAL_CLAIMS):
        raise SupportError(
            'This message appears to promise or confirm a refund, payment, or replacement action. '
            'Use the human approval workflow for that decision. You can still send a factual '
            'status update, such as "Your request is under review."'
        )
