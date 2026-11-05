"""Presentation helpers and SLA calculations."""
from __future__ import annotations
from datetime import datetime, timezone
from html import escape
try:
    from zoneinfo import ZoneInfo
    ZONE = ZoneInfo('Asia/Bangkok')
except (ImportError, Exception):
    ZONE = timezone.utc

PRIORITY_ORDER = {'P1':0,'P2':1,'P3':2,'P4':3}
ACTIVE_STATUSES = {'NEW','IN_REVIEW','AWAITING_APPROVAL','ACTION_PENDING','WAITING_CUSTOMER','REOPENED'}


def display_time(value: datetime | None, concise: bool=True) -> str:
    if value is None:
        return '—'
    local = value.replace(tzinfo=timezone.utc).astimezone(ZONE)
    return local.strftime('%d %b, %I:%M %p') if concise else local.strftime('%d %b %Y, %I:%M %p')


def money(cents: int, currency: str='INR') -> str:
    code = '₹' if currency == 'INR' else f'{currency} '
    return f'{code}{cents/100:,.2f}'


def label_status(value: str) -> str:
    return value.replace('_',' ').title()


def deadline_for(ticket, now: datetime | None=None):
    """Compute the actionable next SLA, without pausing on approval or waiting states."""
    now = now or datetime.now(timezone.utc).replace(tzinfo=None)
    if ticket.status in {'RESOLVED','CLOSED'}:
        return {'label':'Completed','remaining':'—','tone':'success','due':None,'seconds':None}
    if not ticket.first_responded_at:
        due = ticket.first_response_due
        label = 'First response'
    else:
        due = ticket.resolution_due
        label = 'Resolution'
    seconds = int((due-now).total_seconds())
    abs_min = abs(seconds)//60
    if abs_min >= 60:
        left = f'{abs_min//60}h {abs_min%60}m'
    else:
        left = f'{abs_min}m'
    remaining = f'Overdue {left}' if seconds < 0 else f'{left} left'
    # Demo: mark <= 25% of a standard four-hour period as near deadline
    tone = 'danger' if seconds < 0 else ('warning' if seconds <= 60*60 else 'info')
    return {'label': label, 'remaining':remaining, 'tone':tone, 'due':due,'seconds':seconds}


def safe(text) -> str:
    return escape(str(text or ''), quote=True)
