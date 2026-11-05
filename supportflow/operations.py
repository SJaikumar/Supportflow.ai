"""Stage 4 durable SLA checks, staff alerts, and optional simulated refund processing.

Run from a separate process (python -m supportflow.worker), not Streamlit page rendering.
Only portal notifications are sent; no external email/SMS is attempted.
"""
from __future__ import annotations
from dataclasses import dataclass
from datetime import datetime, timedelta
from sqlalchemy import select, update, func
from .db import SessionLocal
from .models import (
    ApprovalRequest, AuditEvent, Commitment, CommitmentReminder, Notification,
    Order, OrderEvent, OutboxEvent, Refund, RefundEvent, SLAEvent, StaffAlert,
    Ticket, TicketMessage, WorkerRun, utcnow,
)
from .security import may_manage_tickets
from .utils import ACTIVE_STATUSES


def _alert(db, key: str, ticket_id: str, *, category: str, severity: str,
           title: str, details: str, now: datetime, commitment_id: int | None = None):
    row = db.scalar(select(StaffAlert).where(StaffAlert.dedupe_key == key))
    if row is None:
        row = StaffAlert(dedupe_key=key, ticket_id=ticket_id, category=category,
                         severity=severity, title=title, details=details,
                         updated_at=now, created_at=now, commitment_id=commitment_id)
        db.add(row)
    elif (row.severity, row.title, row.details) != (severity, title, details):
        # Never downgrade an earlier breach if a test clock or system clock moves backward.
        rank = {'WARNING': 1, 'HIGH': 2, 'CRITICAL': 3}
        if rank[severity] < rank.get(row.severity, 0):
            return row
        row.severity, row.title, row.details, row.updated_at = severity, title, details, now
        row.acknowledged_at = None   # Reopen if a new, more serious threshold occurred.
        row.acknowledged_by = None
        row.cleared_at = None
    return row


def _clear_alert(db, key: str, now: datetime):
    row = db.scalar(select(StaffAlert).where(StaffAlert.dedupe_key == key))
    if row is not None and row.cleared_at is None:
        row.cleared_at = now


def _portal_notification(db, *, key: str, ticket: Ticket, title: str, body: str, now: datetime) -> bool:
    """Notification and outbox are written together, once per natural business key."""
    if db.scalar(select(OutboxEvent.id).where(OutboxEvent.dedupe_key == key)) is not None:
        return False
    note = Notification(customer_id=ticket.customer_id, ticket_id=ticket.id,
                        title=title, body=body, created_at=now)
    db.add(note)
    db.flush()
    db.add(OutboxEvent(dedupe_key=key, customer_id=ticket.customer_id,
                       notification_id=note.id, channel='PORTAL', status='DELIVERED',
                       delivered_at=now))
    return True


def _sla_for_ticket(db, ticket: Ticket, now: datetime) -> int:
    event_count = 0
    obligations = (
        ('RESPONSE', ticket.first_response_due, ticket.first_responded_at),
        ('RESOLUTION', ticket.resolution_due, ticket.resolved_at),
    )
    for kind, due, completed_at in obligations:
        key = f'sla:{ticket.id}:{kind.lower()}'
        if completed_at is not None:
            # A late completion remains in the SLA history, even after resolution.
            if completed_at > due and db.scalar(select(SLAEvent.id).where(
                    SLAEvent.ticket_id == ticket.id, SLAEvent.obligation == kind,
                    SLAEvent.threshold_pct == 100)) is None:
                db.add(SLAEvent(ticket_id=ticket.id, obligation=kind,
                                threshold_pct=100, due_at=due, observed_at=completed_at))
                event_count += 1
            _clear_alert(db, key, now)
            continue
        if ticket.status not in ACTIVE_STATUSES:
            _clear_alert(db, key, now)
            continue
        duration = max((due - ticket.created_at).total_seconds(), 1)
        elapsed = (now - ticket.created_at).total_seconds()
        milestones = [p for p in (75, 90, 100) if elapsed * 100 >= p * duration]
        for pct in milestones:
            exists = db.scalar(select(SLAEvent.id).where(SLAEvent.ticket_id == ticket.id,
                SLAEvent.obligation == kind, SLAEvent.threshold_pct == pct))
            if exists is None:
                db.add(SLAEvent(ticket_id=ticket.id, obligation=kind,
                                threshold_pct=pct, due_at=due, observed_at=now))
                event_count += 1
        if not milestones:
            continue
        pct = max(milestones)
        severity = 'CRITICAL' if pct == 100 else ('HIGH' if pct == 90 else 'WARNING')
        prefix = 'Breached' if pct == 100 else f'{pct}% elapsed'
        _alert(db, key, ticket.id, category='SLA', severity=severity,
               title=f'{kind.title()} SLA {prefix} · {ticket.id}',
               details=f'{kind.title()} target: {due:%Y-%m-%d %H:%M} UTC', now=now)
        if pct == 100 and _portal_notification(db, key=f'sla:{ticket.id}:{kind.lower()}:breached',
                ticket=ticket, title=f'Support update · {ticket.id}',
                body='We have missed an internal support time target. Our support team has been alerted. '
                     'This is not a confirmation that your underlying issue has been resolved.', now=now):
            event_count += 1
    return event_count


def _commitment_for_ticket(db, commitment: Commitment, ticket: Ticket, now: datetime) -> int:
    key = f'commitment:{commitment.id}'
    if commitment.completed_at is not None:
        _clear_alert(db, key, now)
        return 0
    event_type = ('OVERDUE' if now >= commitment.due_at else
                  'DUE_SOON' if commitment.due_at - now <= timedelta(minutes=60) else None)
    if event_type is None:
        return 0
    existing = db.scalar(select(CommitmentReminder.id).where(
        CommitmentReminder.commitment_id == commitment.id,
        CommitmentReminder.event_type == event_type))
    created = 0
    if existing is None:
        db.add(CommitmentReminder(commitment_id=commitment.id,
                                  event_type=event_type, emitted_at=now))
        created += 1
    severity = 'CRITICAL' if event_type == 'OVERDUE' else 'WARNING'
    _alert(db, key, ticket.id, category='PROMISE', severity=severity,
           title=('Missed customer promise' if event_type == 'OVERDUE' else 'Upcoming customer promise'),
           details=f'{commitment.description} · due {commitment.due_at:%Y-%m-%d %H:%M} UTC',
           now=now, commitment_id=commitment.id)
    if event_type == 'OVERDUE' and commitment.customer_visible:
        if _portal_notification(db, key=f'commitment:{commitment.id}:overdue',
                 ticket=ticket, title=f'Update overdue · {ticket.id}',
                 body='We have missed the promised update time for: '+commitment.description+'. '
                      'The support team has been notified. We are not claiming the action is completed.', now=now):
            created += 1
    return created


def _process_refund(db, refund: Refund, now: datetime) -> int:
    """Optional simulated payment processor. No external payments; idempotent state transition."""
    ap = db.get(ApprovalRequest, refund.approval_id) if refund.approval_id else None
    if ap is None or ap.status != 'APPROVED':
        return 0
    changed = db.execute(update(Refund).where(Refund.id == refund.id, Refund.status == 'PROCESSING')
                        .values(status='COMPLETED', processed_at=now))
    if changed.rowcount != 1:
        return 0
    ticket = db.get(Ticket, refund.ticket_id)
    order = db.get(Order, refund.order_id)
    total_completed = db.scalar(select(func.coalesce(func.sum(Refund.amount_cents), 0)).where(
        Refund.order_id == order.id, Refund.status == 'COMPLETED')) or 0
    if total_completed >= order.total_cents:
        order.status = 'REFUNDED'
        db.add(OrderEvent(order_id=order.id, event_type='REFUNDED',
                          description='Entire order value refunded in simulation', occurred_at=now))
    db.add(RefundEvent(refund_id=refund.id, status='COMPLETED',
                       description='Background simulated refund completed; no real money moved',
                       occurred_at=now))
    ticket.status, ticket.resolved_at, ticket.updated_at = 'RESOLVED', now, now
    db.add(TicketMessage(ticket_id=ticket.id, sender_kind='system',
        body='Your simulated refund is now marked completed. No real payment was processed.', created_at=now))
    _portal_notification(db, key=f'refund:{refund.id}:complete', ticket=ticket,
        title=f'Simulated refund completed · {ticket.id}',
        body='Your simulated refund has been marked complete. No real payment was made.', now=now)
    db.add(AuditEvent(ticket_id=ticket.id, event_type='SIMULATED_REFUND_COMPLETED',
                      details=f'Automated simulation for refund #{refund.id}', created_at=now))
    return 1


def run_tick(*, now: datetime | None = None, process_refunds: bool = False,
             refund_delay_seconds: int = 60) -> dict:
    """Perform one deterministic, restart-safe sweep.

    `now` is supplied by tests; production runs use utcnow(). Do not set a synthetic
    clock to send real notices to customers. The only delivery channel is local PORTAL.
    """
    now = now or utcnow()
    if now.tzinfo is not None:
        from datetime import timezone
        now = now.astimezone(timezone.utc).replace(tzinfo=None)
    count = 0
    with SessionLocal.begin() as db:
        run = WorkerRun(started_at=now, status='RUNNING')
        db.add(run)
        db.flush()
        for t in db.scalars(select(Ticket).order_by(Ticket.id)).all():
            count += _sla_for_ticket(db, t, now)
        for commitment, ticket in db.execute(select(Commitment, Ticket).join(
                Ticket, Commitment.ticket_id == Ticket.id)).all():
            count += _commitment_for_ticket(db, commitment, ticket, now)
        if process_refunds:
            threshold = now - timedelta(seconds=max(0, refund_delay_seconds))
            queued = db.scalars(select(Refund).join(
                ApprovalRequest, Refund.approval_id == ApprovalRequest.id).where(
                Refund.status == 'PROCESSING', ApprovalRequest.status == 'APPROVED',
                ApprovalRequest.reviewed_at <= threshold)).all()
            for refund in queued:
                count += _process_refund(db, refund, now)
        run.event_count = count
        run.status = 'SUCCEEDED'
        run.finished_at = now
        run_id = run.id
    return {'run_id': run_id, 'events': count, 'at': now.isoformat(), 'status': 'SUCCEEDED'}


def staff_alerts(actor, *, include_cleared: bool = False) -> list[StaffAlert]:
    if not may_manage_tickets(actor.role):
        from .services import SupportError
        raise SupportError('Staff-only alerts.')
    with SessionLocal() as db:
        query = select(StaffAlert)
        if not include_cleared:
            query = query.where(StaffAlert.cleared_at.is_(None))
        return list(db.scalars(query.order_by(StaffAlert.acknowledged_at.is_not(None),
            StaffAlert.severity.asc(), StaffAlert.updated_at.desc())))


def acknowledge_alert(actor, alert_id: int):
    from .services import SupportError
    if not may_manage_tickets(actor.role):
        raise SupportError('Staff-only alerts.')
    with SessionLocal.begin() as db:
        alert = db.get(StaffAlert, alert_id)
        if alert is None:
            raise SupportError('Alert not found.')
        if alert.acknowledged_at is None:
            alert.acknowledged_at = utcnow()
            alert.acknowledged_by = actor.id
            db.add(AuditEvent(actor_id=actor.id, ticket_id=alert.ticket_id,
                event_type='STAFF_ALERT_ACKNOWLEDGED', details=f'Alert #{alert_id}'))


def worker_health(actor) -> dict:
    from .services import SupportError
    if not may_manage_tickets(actor.role):
        raise SupportError('Staff-only status.')
    with SessionLocal() as db:
        last = db.scalar(select(WorkerRun).order_by(WorkerRun.started_at.desc(), WorkerRun.id.desc()))
        open_alerts = db.scalar(select(func.count()).select_from(StaffAlert).where(
            StaffAlert.cleared_at.is_(None), StaffAlert.acknowledged_at.is_(None))) or 0
        promises = db.scalar(select(func.count()).select_from(Commitment).where(
            Commitment.completed_at.is_(None), Commitment.due_at < utcnow())) or 0
        return {'last_run': last, 'unacknowledged': open_alerts, 'overdue_promises': promises}
