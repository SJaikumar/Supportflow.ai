"""Role-checked transactional operations. No AI or payment gateway calls in Stage 2."""
from __future__ import annotations
import io
import uuid
from datetime import datetime, timedelta
from pathlib import Path
from typing import Sequence
from sqlalchemy import and_, func, select, update
from PIL import Image, UnidentifiedImageError
from .config import CATEGORIES, MAX_IMAGE_BYTES, UPLOAD_DIR
from .db import SessionLocal
from .models import (ApprovalRequest, ApprovalDecision, Attachment, AuditEvent, Commitment,
                     Customer, CustomerNote, Notification, Order, OrderEvent, OrderItem,
                     OutboxEvent, Refund, RefundEvent, PhotoConsent, SLAPolicy, SLAPolicyChange,
                     Ticket, TicketCounter, TicketLink, TicketMessage, User, EscalationAssignment, utcnow)
from .security import may_manage_tickets, may_review, verify_password
from .utils import ACTIVE_STATUSES, PRIORITY_ORDER, deadline_for


class SupportError(ValueError):
    """A user-facing validation, authorization, or workflow error."""


def get_user(user_id: int) -> User | None:
    with SessionLocal() as db:
        return db.get(User, user_id)


def authenticate(email: str, password: str) -> User | None:
    with SessionLocal() as db:
        user=db.scalar(select(User).where(User.email==email.strip().lower()))
        if user and verify_password(password,user.password_hash):
            return user
        return None


def customer_for_user(user: User) -> Customer:
    with SessionLocal() as db:
        customer=db.scalar(select(Customer).where(Customer.user_id==user.id))
        if not customer:
            raise SupportError('This account is not linked to a customer profile.')
        return customer


def customers_list(actor: User) -> list[dict]:
    if not may_manage_tickets(actor.role):
        raise SupportError('Access denied.')
    with SessionLocal() as db:
        rows=db.execute(select(Customer,User).join(User,Customer.user_id==User.id).order_by(User.name)).all()
        return [{'customer':c,'user':u} for c,u in rows]


def customer_detail(actor: User, customer_id: int) -> dict:
    if not may_manage_tickets(actor.role):
        raise SupportError('Access denied.')
    with SessionLocal() as db:
        c=db.get(Customer,customer_id)
        if not c:
            raise SupportError('Customer not found.')
        u=db.get(User,c.user_id)
        orders=db.scalars(select(Order).where(Order.customer_id==customer_id).order_by(Order.placed_at.desc())).all()
        tickets=db.scalars(select(Ticket).where(Ticket.customer_id==customer_id).order_by(Ticket.created_at.desc())).all()
        refunds=db.scalars(select(Refund).join(Ticket,Ticket.id==Refund.ticket_id).where(Ticket.customer_id==customer_id)).all()
        notes=db.scalars(select(CustomerNote).where(CustomerNote.customer_id==customer_id)
            .order_by(CustomerNote.created_at.desc())).all()
        commitments=db.scalars(select(Commitment).join(Ticket,Ticket.id==Commitment.ticket_id)
            .where(Ticket.customer_id==customer_id).order_by(Commitment.due_at.desc())).all()
        return {'customer':c,'user':u,'orders':orders,'tickets':tickets,
                'refunds':refunds,'notes':notes,'commitments':commitments,
                'insights':_customer_insights(orders,tickets,refunds)}


def orders_for_customer(actor: User, customer_id: int | None=None) -> list[dict]:
    with SessionLocal() as db:
        if actor.role=='customer':
            my=db.scalar(select(Customer).where(Customer.user_id==actor.id))
            if not my: return []
            if customer_id is not None and customer_id!=my.id:
                raise SupportError('Access denied.')
            customer_id=my.id
        elif not may_manage_tickets(actor.role):
            raise SupportError('Access denied.')
        query=select(Order,OrderItem).join(OrderItem,Order.id==OrderItem.order_id)
        if customer_id is not None:
            query=query.where(Order.customer_id==customer_id)
        results=db.execute(query.order_by(Order.placed_at.desc())).all()
        return [{'order':o,'item':item} for o,item in results]


def visible_tickets(actor: User) -> list[dict]:
    with SessionLocal() as db:
        query=select(Ticket,User.name).join(Customer,Ticket.customer_id==Customer.id).join(User,Customer.user_id==User.id)
        if actor.role=='customer':
            query=query.where(Customer.user_id==actor.id)
        elif not may_manage_tickets(actor.role):
            raise SupportError('Access denied.')
        result=db.execute(query.order_by(Ticket.created_at.desc())).all()
        data=[{'ticket':ticket,'customer_name':name,'sla':deadline_for(ticket)} for ticket,name in result]
        data.sort(key=lambda r:(r['ticket'].status not in ACTIVE_STATUSES,
            0 if r['sla']['seconds'] is not None and r['sla']['seconds']<0 else 1,
            PRIORITY_ORDER.get(r['ticket'].priority,4),
            r['sla']['seconds'] if r['sla']['seconds'] is not None else 10**10))
        return data


def ticket_detail(actor: User, ticket_id: str) -> dict:
    with SessionLocal() as db:
        t=db.get(Ticket,ticket_id)
        if not t: raise SupportError('Ticket not found.')
        c=db.get(Customer,t.customer_id)
        if actor.role=='customer' and c.user_id!=actor.id:
            raise SupportError('You cannot access another customer’s ticket.')
        if actor.role!='customer' and not may_manage_tickets(actor.role):
            raise SupportError('Access denied.')
        u=db.get(User,c.user_id)
        order=db.get(Order,t.order_id) if t.order_id else None
        item=db.scalar(select(OrderItem).where(OrderItem.order_id==t.order_id)) if order else None
        msgs=db.scalars(select(TicketMessage).where(TicketMessage.ticket_id==t.id).order_by(TicketMessage.created_at,TicketMessage.id)).all()
        if actor.role=='customer':
            msgs=[m for m in msgs if m.visible_to_customer]
        approvals=db.scalars(select(ApprovalRequest).where(ApprovalRequest.ticket_id==t.id).order_by(ApprovalRequest.created_at.desc())).all()
        refunds=db.scalars(select(Refund).where(Refund.ticket_id==t.id).order_by(Refund.id.desc())).all()
        attachments=db.scalars(select(Attachment).where(Attachment.ticket_id==t.id)).all()
        commitments=db.scalars(select(Commitment).where(Commitment.ticket_id==t.id)
            .order_by(Commitment.due_at)).all()
        if actor.role=='customer':
            commitments=[co for co in commitments if co.customer_visible]
        # Order event notes are operational/internal. Customer-facing updates use ticket messages.
        order_events=(db.scalars(select(OrderEvent).where(OrderEvent.order_id==t.order_id)
            .order_by(OrderEvent.occurred_at.desc())).all()
            if order and actor.role!='customer' else [])
        related=db.scalars(select(TicketLink).where(
            (TicketLink.ticket_a_id==t.id)|(TicketLink.ticket_b_id==t.id))).all()
        decisions=db.scalars(select(ApprovalDecision).join(ApprovalRequest,
            ApprovalDecision.approval_id==ApprovalRequest.id).where(ApprovalRequest.ticket_id==t.id)).all()
        return {'ticket':t,'customer':c,'user':u,'order':order,'item':item,
                'messages':msgs,'approvals':approvals if actor.role!='customer' else [],
                'approval_decisions':decisions if actor.role!='customer' else [],
                'refunds':refunds,'attachments':attachments,'sla':deadline_for(t),
                'commitments':commitments,'order_events':order_events,
                'ticket_links':related if actor.role!='customer' else []}


def unread_count(actor: User) -> int:
    if actor.role!='customer':return 0
    with SessionLocal() as db:
        return db.scalar(select(func.count()).select_from(Notification).join(Customer,Notification.customer_id==Customer.id)
            .where(Customer.user_id==actor.id,Notification.read_at.is_(None))) or 0


def notifications_for_customer(actor: User) -> list[Notification]:
    if actor.role!='customer': raise SupportError('Only customer accounts have inboxes.')
    c=customer_for_user(actor)
    with SessionLocal() as db:
        return list(db.scalars(select(Notification).where(Notification.customer_id==c.id).order_by(Notification.created_at.desc())))


def mark_notification_read(actor: User, notification_id: int):
    if actor.role!='customer':raise SupportError('Access denied.')
    c=customer_for_user(actor)
    with SessionLocal.begin() as db:
        note=db.get(Notification,notification_id)
        if not note or note.customer_id!=c.id:
            raise SupportError('Notification not found.')
        if not note.read_at: note.read_at=utcnow()


def priority_for(category: str, complaint: str) -> str:
    """Explicit demo heuristics, not LLM classification."""
    text=complaint.lower()
    if category=='Billing' and any(w in text for w in ('charged twice','charged three','fraud','stolen','unauthorised','unauthorized')):
        return 'P1'
    if category in ('Product quality','Refund') and any(w in text for w in ('damaged','broken','refund','wrong product')):
        return 'P2'
    if category=='Delivery' and any(w in text for w in ('late','missing','delayed','not arrived')):
        return 'P2'
    return 'P3'


def create_ticket(actor: User, *, order_id: str | None, category: str, title: str, complaint: str,
                  uploads: Sequence[tuple[str,bytes]] = (),
                  consent_photo_ai: bool = False) -> str:
    if actor.role!='customer':raise SupportError('Only customers can create complaints in this demo.')
    if category not in CATEGORIES:raise SupportError('Choose a valid category.')
    title,complaint=title.strip(),complaint.strip()
    if len(title)<3 or len(title)>180:raise SupportError('Title must be between 3 and 180 characters.')
    if len(complaint)<12 or len(complaint)>4000:raise SupportError('Description must be 12–4,000 characters.')
    if len(uploads)>3:raise SupportError('Up to three photos per ticket.')
    validated=[]
    for name,bytes_data in uploads:
        if not bytes_data or len(bytes_data)>MAX_IMAGE_BYTES:
            raise SupportError('Images must be under 5 MB each.')
        try:
            im=Image.open(io.BytesIO(bytes_data));im.verify()
            fmt=im.format
        except (UnidentifiedImageError,OSError,ValueError):
            raise SupportError('Please upload a valid JPEG or PNG image.')
        if fmt not in ('JPEG','PNG'):
            raise SupportError('Only JPEG or PNG photos are accepted.')
        validated.append((name,bytes_data,fmt))
    saved=[]
    try:
        with SessionLocal.begin() as db:
            customer=db.scalar(select(Customer).where(Customer.user_id==actor.id))
            if not customer:raise SupportError('Customer account not found.')
            if order_id:
                order=db.get(Order,order_id)
                if not order or order.customer_id!=customer.id:
                    raise SupportError('Please select one of your own orders.')
            priority=priority_for(category,complaint)
            policy=db.get(SLAPolicy,priority)
            if not policy:raise SupportError('SLA policy not configured.')
            # Atomic counter allocation avoids a read-max/write race across submissions.
            number=db.scalar(update(TicketCounter).where(TicketCounter.key=='tickets')
                .values(last_value=TicketCounter.last_value+1)
                .returning(TicketCounter.last_value))
            if number is None:raise SupportError('Ticket numbering is unavailable.')
            tid=f'TKT-{number}'
            now=utcnow()
            db.add(Ticket(id=tid,customer_id=customer.id,order_id=order_id,title=title,complaint=complaint,
                category=category,priority=priority,status='NEW',created_at=now,updated_at=now,
                first_response_due=now+timedelta(minutes=policy.first_response_minutes),
                resolution_due=now+timedelta(minutes=policy.resolution_minutes)))
            db.flush()  # Persist ticket before FK-dependent messages, alerts and audit records.
            db.add(TicketMessage(ticket_id=tid,sender_id=actor.id,sender_kind='customer',body=complaint,created_at=now))
            db.add(Notification(customer_id=customer.id,ticket_id=tid,title=f'Request {tid} received',
                body='Your request has been recorded. Our team will review it.',created_at=now))
            for original,data,fmt in validated:
                UPLOAD_DIR.mkdir(parents=True,exist_ok=True)
                filename=f'{uuid.uuid4().hex}.{fmt.lower().replace("jpeg","jpg")}'
                path=UPLOAD_DIR/filename
                path.write_bytes(data)
                saved.append(path)
                photo=Attachment(ticket_id=tid,uploaded_by=actor.id,original_filename=Path(original).name[:200],
                    stored_filename=filename,mime_type='image/jpeg' if fmt=='JPEG' else 'image/png')
                db.add(photo);db.flush()
                if consent_photo_ai:
                    db.add(PhotoConsent(attachment_id=photo.id,customer_user_id=actor.id))
                    db.add(AuditEvent(actor_id=actor.id,ticket_id=tid,
                        event_type='PHOTO_AI_CONSENT_GRANTED',details=f'Attachment #{photo.id}'))
            # Context-only repeat-contact links are based on the same verified customer and order.
            if order_id:
                previous=db.scalars(select(Ticket).where(Ticket.customer_id==customer.id,
                    Ticket.order_id==order_id,Ticket.id!=tid).order_by(Ticket.created_at.desc()).limit(3)).all()
                for other in previous:
                    db.add(TicketLink(ticket_a_id=min(tid,other.id),ticket_b_id=max(tid,other.id),
                        relation='SAME_ORDER',linked_by=None))
            db.add(AuditEvent(actor_id=actor.id,ticket_id=tid,event_type='TICKET_CREATED',details=f'Category: {category}; priority: {priority}'))
        return tid
    except Exception:
        for p in saved:p.unlink(missing_ok=True)
        raise


def post_ticket_message(actor: User, ticket_id: str, body: str, *,
                        ai_run_id: str | None = None, human_reviewed: bool = False):
    """Persist a customer-visible message and notification in a single transaction.

    A support agent may send a *reviewed informational update* on an escalated
    ticket. Financial/action decisions still require the separate approver flow.
    Provenance and human-review confirmation are checked on the server, not just
    by disabling a Streamlit button.
    """
    body=body.strip()
    if not 1<=len(body)<=4000:raise SupportError('Message must be 1–4,000 characters.')
    if ai_run_id is not None and not human_reviewed:
        raise SupportError('Please confirm human review of the AI-generated message before sending it.')
    with SessionLocal.begin() as db:
        ticket=db.get(Ticket,ticket_id)
        if not ticket:raise SupportError('Ticket not found.')
        c=db.get(Customer,ticket.customer_id)
        if actor.role=='customer':
            if ai_run_id is not None:raise SupportError('Only support staff can send a reviewed AI draft.')
            if c.user_id!=actor.id:raise SupportError('Access denied.')
            kind='customer'
            if ticket.status in ('RESOLVED','CLOSED'):
                ticket.status='REOPENED';ticket.resolved_at=None
            elif ticket.status=='WAITING_CUSTOMER':
                ticket.status='IN_REVIEW'
        elif may_manage_tickets(actor.role):
            from supportflow.reply_policy import validate_informational_update
            validate_informational_update(body)
            if ai_run_id is not None:
                from supportflow.models import AIAnalysisRun
                run=db.get(AIAnalysisRun,ai_run_id)
                if not run or run.ticket_id!=ticket_id or run.status!='SUCCEEDED':
                    raise SupportError('This AI draft is unavailable or belongs to a different ticket.')
            kind='agent'
            if not ticket.first_responded_at:ticket.first_responded_at=utcnow()
            # Sending an informational update is not a customer-information request.
            # Pending escalations/approvals must remain in the appropriate queue.
            if (ticket.status in ('NEW','IN_REVIEW','REOPENED')
                    and not ticket.escalated and ai_run_id is None):
                ticket.status='WAITING_CUSTOMER'
            elif ticket.status in ('NEW','REOPENED'):
                ticket.status='IN_REVIEW'
            note=Notification(customer_id=ticket.customer_id,ticket_id=ticket_id,
                title=f'New support reply · {ticket_id}',body=body[:180])
            db.add(note);db.flush()
            db.add(OutboxEvent(dedupe_key=f'notification:{note.id}',customer_id=ticket.customer_id,
                notification_id=note.id))
        else:raise SupportError('Access denied.')
        ticket.updated_at=utcnow()
        db.add(TicketMessage(ticket_id=ticket_id,sender_id=actor.id,sender_kind=kind,body=body))
        db.add(AuditEvent(actor_id=actor.id,ticket_id=ticket_id,event_type='MESSAGE_SENT',details=kind))
        if ai_run_id is not None:
            db.add(AuditEvent(actor_id=actor.id,ticket_id=ticket_id,
                event_type='REVIEWED_AI_DRAFT_SENT',
                details=f'AI run {ai_run_id}; human-reviewed customer update; no action authorized'))


def approvals_list(actor: User) -> list[dict]:
    if not may_manage_tickets(actor.role):raise SupportError('Access denied.')
    with SessionLocal() as db:
        rows=db.execute(select(ApprovalRequest,Ticket,User.name).join(Ticket,ApprovalRequest.ticket_id==Ticket.id)
            .join(Customer,Ticket.customer_id==Customer.id).join(User,Customer.user_id==User.id)
            .order_by(ApprovalRequest.status!='PENDING',ApprovalRequest.created_at.desc())).all()
        return [{'approval':ap,'ticket':ticket,'customer_name':name} for ap,ticket,name in rows]


def request_approval(actor: User, ticket_id: str, amount_cents: int, draft: str):
    if not may_manage_tickets(actor.role):raise SupportError('Agent access required.')
    if amount_cents<=0 or not draft.strip():raise SupportError('Amount and draft response are required.')
    with SessionLocal.begin() as db:
        t=db.get(Ticket,ticket_id)
        if not t or not t.order_id:raise SupportError('A linked order is required for a refund request.')
        order=db.get(Order,t.order_id)
        if amount_cents>order.total_cents:raise SupportError('Refund cannot exceed the recorded order total.')
        reserved=db.scalar(select(func.coalesce(func.sum(Refund.amount_cents),0)).where(
            Refund.order_id==t.order_id, Refund.status.in_(['PENDING_APPROVAL','PROCESSING','COMPLETED']))) or 0
        if reserved+amount_cents>order.total_cents:
            raise SupportError('This order already has refunds or pending requests that would exceed its total.')
        if db.scalar(select(ApprovalRequest).where(ApprovalRequest.ticket_id==ticket_id,ApprovalRequest.status=='PENDING')):
            raise SupportError('A pending approval already exists for this ticket.')
        ap=ApprovalRequest(ticket_id=ticket_id,action='REFUND',proposed_amount_cents=amount_cents,
            draft_response=draft.strip(),requested_by=actor.id,status='PENDING')
        db.add(ap);db.flush()
        refund=Refund(ticket_id=ticket_id,order_id=t.order_id,amount_cents=amount_cents,
            approval_id=ap.id,status='PENDING_APPROVAL')
        db.add(refund);db.flush()
        db.add(RefundEvent(refund_id=refund.id,status='PENDING_APPROVAL',
            description='Approval requested',actor_id=actor.id))
        t.status='AWAITING_APPROVAL';t.escalated=True;t.updated_at=utcnow()
        db.add(AuditEvent(actor_id=actor.id,ticket_id=ticket_id,event_type='APPROVAL_REQUESTED',details=f'Approval #{ap.id}'))
        return ap.id


def decide_approval(actor: User, approval_id: int, *, approve: bool, edited_message: str, reason: str=''):
    if not may_review(actor.role):raise SupportError('Only approvers and administrators can decide refunds.')
    edited_message=edited_message.strip();reason=reason.strip()
    if len(edited_message)<10 or len(edited_message)>4000:raise SupportError('Please provide a customer-ready message (10–4,000 characters).')
    if not approve and not reason:raise SupportError('A rejection reason is required.')
    with SessionLocal.begin() as db:
        ap=db.get(ApprovalRequest,approval_id)
        if not ap:raise SupportError('Approval request not found.')
        # State-checked update prevents double decisions and duplicate notifications on repeated clicks.
        now=utcnow();new_status='APPROVED' if approve else 'REJECTED'
        changed=db.execute(update(ApprovalRequest).where(ApprovalRequest.id==approval_id,ApprovalRequest.status=='PENDING')
            .values(status=new_status,reviewer_id=actor.id,reviewer_reason=reason,
                    approved_message=edited_message,reviewed_at=now))
        if changed.rowcount!=1:raise SupportError('This approval has already been decided. Refresh the page.')
        t=db.get(Ticket,ap.ticket_id)
        t.status='ACTION_PENDING' if approve else 'IN_REVIEW'
        t.updated_at=now
        if not t.first_responded_at:t.first_responded_at=now
        refund=db.scalar(select(Refund).where(Refund.approval_id==approval_id))
        # Old seed records have an unlinked refund request; link only the exact ticket's pending record.
        if refund is None:
            refund=db.scalar(select(Refund).where(Refund.ticket_id==ap.ticket_id,Refund.status=='PENDING_APPROVAL'))
            if refund:refund.approval_id=approval_id
        if refund:
            refund.status='PROCESSING' if approve else 'REJECTED'
            db.add(RefundEvent(refund_id=refund.id,status=refund.status,
                description=f'Human decision #{approval_id}',actor_id=actor.id,occurred_at=now))
        db.add(ApprovalDecision(approval_id=approval_id,reviewer_id=actor.id,outcome=new_status,
            reason=reason,final_customer_message=edited_message,decided_at=now))
        db.add(TicketMessage(ticket_id=t.id,sender_id=actor.id,sender_kind='agent',body=edited_message,created_at=now))
        note=Notification(customer_id=t.customer_id,ticket_id=t.id,
            title=f'Refund {"approved" if approve else "review update"} · {t.id}',body=edited_message[:350],created_at=now)
        db.add(note);db.flush()
        db.add(OutboxEvent(dedupe_key=f'approval:{approval_id}:decision',customer_id=t.customer_id,
            notification_id=note.id,delivered_at=now))
        db.add(AuditEvent(actor_id=actor.id,ticket_id=t.id,event_type='APPROVAL_APPROVED' if approve else 'APPROVAL_REJECTED',
            details=f'Approval #{approval_id}; amount {ap.proposed_amount_cents}; note: {reason}'))


def complete_simulated_refund(actor: User, refund_id: int):
    if not may_review(actor.role):raise SupportError('Approver access required.')
    with SessionLocal.begin() as db:
        refund=db.get(Refund,refund_id)
        if not refund:raise SupportError('Refund not found.')
        changed=db.execute(update(Refund).where(Refund.id==refund_id,Refund.status=='PROCESSING')
            .values(status='COMPLETED',processed_at=utcnow()))
        if changed.rowcount!=1:raise SupportError('Only a processing refund can be completed.')
        ticket=db.get(Ticket,refund.ticket_id)
        order=db.get(Order,refund.order_id)
        # Aggregate all completed refunds rather than only the latest refund amount.
        completed_total=db.scalar(select(func.coalesce(func.sum(Refund.amount_cents),0))
            .where(Refund.order_id==order.id,Refund.status=='COMPLETED')) or 0
        if completed_total >= order.total_cents:
            order.status='REFUNDED'
            db.add(OrderEvent(order_id=order.id,event_type='REFUNDED',
                description='Full order value refunded in demo',actor_id=actor.id))
        db.add(RefundEvent(refund_id=refund.id,status='COMPLETED',
            description='Simulated refund completed; no real payment',actor_id=actor.id))
        ticket.status='RESOLVED';ticket.resolved_at=utcnow();ticket.updated_at=utcnow()
        db.add(TicketMessage(ticket_id=ticket.id,sender_id=actor.id,sender_kind='agent',
            body='Your refund has now been completed in the SupportFlow demo. No real payment was made.'))
        note=Notification(customer_id=ticket.customer_id,ticket_id=ticket.id,
            title=f'Simulated refund completed · {ticket.id}',body='Your simulated refund is marked completed. No real payment was made.')
        db.add(note);db.flush()
        db.add(OutboxEvent(dedupe_key=f'refund:{refund.id}:complete',customer_id=ticket.customer_id,
            notification_id=note.id))
        db.add(AuditEvent(actor_id=actor.id,ticket_id=ticket.id,event_type='SIMULATED_REFUND_COMPLETED',
            details=f'Refund #{refund.id}; amount {refund.amount_cents}'))


def sla_policies():
    with SessionLocal() as db:
        return list(db.scalars(select(SLAPolicy).order_by(SLAPolicy.priority)))


def audit_for_ticket(actor: User,ticket_id: str):
    if not may_manage_tickets(actor.role):raise SupportError('Access denied.')
    with SessionLocal() as db:
        return list(db.scalars(select(AuditEvent).where(AuditEvent.ticket_id==ticket_id).order_by(AuditEvent.created_at.desc())))


def read_attachment(actor: User, attachment_id: int) -> bytes:
    with SessionLocal() as db:
        at=db.get(Attachment,attachment_id)
        if not at:raise SupportError('Attachment not found.')
        t=db.get(Ticket,at.ticket_id)
        c=db.get(Customer,t.customer_id)
        if actor.role=='customer' and c.user_id!=actor.id:raise SupportError('Access denied.')
        if actor.role!='customer' and not may_manage_tickets(actor.role):raise SupportError('Access denied.')
        path=UPLOAD_DIR/at.stored_filename
        if not path.is_file():raise SupportError('Attachment file is missing.')
        return path.read_bytes()


# ------------------------------------------------------------
# Stage 2: customer history, operational commitments, and audit
# ------------------------------------------------------------
def _customer_insights(orders: list[Order], tickets: list[Ticket], refunds: list[Refund]) -> dict:
    """Descriptive service metrics only: these are never a fraud score."""
    eligible_ids={o.id for o in orders if o.delivered_at is not None}
    requested_ids={r.order_id for r in refunds}
    count=len(eligible_ids & requested_ids)
    groups={}
    for ticket in tickets:
        if ticket.order_id:
            groups.setdefault(ticket.order_id,[]).append(ticket.id)
    repeat={order:ids for order,ids in groups.items() if len(ids)>1}
    completed=sum(r.status=='COMPLETED' for r in refunds)
    completed_cents=sum(r.amount_cents for r in refunds if r.status=='COMPLETED')
    return {
        'orders_placed':len(orders),'tickets_raised':len(tickets),
        'refund_orders':len(requested_ids),'eligible_delivered_orders':len(eligible_ids),
        'eligible_orders_with_refund_requests':count,
        'refund_request_rate_pct':round(count/len(eligible_ids)*100,1) if eligible_ids else None,
        'refunds_completed':completed,'completed_refund_cents':completed_cents,
        'active_tickets':sum(t.status in ACTIVE_STATUSES for t in tickets),
        'repeat_order_ticket_ids':repeat,
    }


def add_customer_note(actor: User, customer_id: int, text: str) -> int:
    """Internal agent-only note, never displayed to the customer or included in AI prompts."""
    if not may_manage_tickets(actor.role):raise SupportError('Staff access required.')
    text=text.strip()
    if not 10<=len(text)<=2000:raise SupportError('Note must contain 10–2,000 characters.')
    with SessionLocal.begin() as db:
        if not db.get(Customer,customer_id):raise SupportError('Customer not found.')
        note=CustomerNote(customer_id=customer_id,author_id=actor.id,text=text)
        db.add(note);db.flush()
        db.add(AuditEvent(actor_id=actor.id,event_type='CUSTOMER_NOTE_ADDED',
            details=f'Customer {customer_id}; note #{note.id}'))
        return note.id


def add_order_event(actor: User, order_id: str, event_type: str, description: str) -> int:
    """Record a factual order event without changing the order fulfillment state."""
    if not may_manage_tickets(actor.role):raise SupportError('Staff access required.')
    event_type=event_type.strip().upper().replace(' ','_')
    description=description.strip()
    if event_type not in {'INVESTIGATION_OPENED','CARRIER_UPDATE','DELIVERY_CONFIRMED',
                          'CUSTOMER_CONTACTED','QUALITY_INSPECTION','OTHER'}:
        raise SupportError('Unsupported order event type.')
    if not 5<=len(description)<=400:raise SupportError('Description must be 5–400 characters.')
    with SessionLocal.begin() as db:
        if not db.get(Order,order_id):raise SupportError('Order not found.')
        event=OrderEvent(order_id=order_id,event_type=event_type,description=description,actor_id=actor.id)
        db.add(event);db.flush()
        db.add(AuditEvent(actor_id=actor.id,event_type='ORDER_EVENT_ADDED',
            details=f'Order {order_id}; event #{event.id}; type {event_type}'))
        return event.id


def create_commitment(actor: User, ticket_id: str, description: str, due_at: datetime,
                      *, customer_visible: bool=True) -> int:
    """Persist a promise with an owner. Background reminders are a Stage 4 task."""
    if not may_manage_tickets(actor.role):raise SupportError('Staff access required.')
    description=description.strip()
    if not 10<=len(description)<=400:raise SupportError('Commitment must contain 10–400 characters.')
    if due_at.tzinfo is not None:
        from datetime import timezone
        due_at=due_at.astimezone(timezone.utc).replace(tzinfo=None)
    now=utcnow()
    if due_at<=now or due_at>now+timedelta(days=365):
        raise SupportError('Promise deadline must be in the next 365 days.')
    with SessionLocal.begin() as db:
        ticket=db.get(Ticket,ticket_id)
        if not ticket:raise SupportError('Ticket not found.')
        commitment=Commitment(ticket_id=ticket_id,description=description,owner_id=actor.id,
            created_by=actor.id,due_at=due_at,customer_visible=customer_visible)
        db.add(commitment);db.flush()
        db.add(AuditEvent(actor_id=actor.id,ticket_id=ticket_id,event_type='COMMITMENT_CREATED',
            details=f'Commitment #{commitment.id}; due UTC {due_at.isoformat()}'))
        if customer_visible:
            note=Notification(customer_id=ticket.customer_id,ticket_id=ticket_id,
                title=f'Update promised · {ticket_id}',body=description)
            db.add(note);db.flush()
            db.add(OutboxEvent(dedupe_key=f'commitment:{commitment.id}:created',
                customer_id=ticket.customer_id,notification_id=note.id))
        return commitment.id


def complete_commitment(actor: User, commitment_id: int) -> None:
    if not may_manage_tickets(actor.role):raise SupportError('Staff access required.')
    with SessionLocal.begin() as db:
        now=utcnow()
        changed=db.execute(update(Commitment).where(Commitment.id==commitment_id,
            Commitment.completed_at.is_(None)).values(completed_at=now))
        if changed.rowcount!=1:raise SupportError('Commitment not found or already completed.')
        promise=db.get(Commitment,commitment_id)
        ticket=db.get(Ticket,promise.ticket_id)
        db.add(AuditEvent(actor_id=actor.id,ticket_id=ticket.id,event_type='COMMITMENT_COMPLETED',
            details=f'Commitment #{promise.id}'))
        if promise.customer_visible:
            note=Notification(customer_id=ticket.customer_id,ticket_id=ticket.id,
                title=f'Promised update completed · {ticket.id}',body=promise.description)
            db.add(note);db.flush()
            db.add(OutboxEvent(dedupe_key=f'commitment:{promise.id}:completed',
                customer_id=ticket.customer_id,notification_id=note.id))


def related_tickets(actor: User, ticket_id: str) -> list[Ticket]:
    """Return verified same-customer tickets linked for operational context."""
    record=ticket_detail(actor,ticket_id)  # Enforces customer ownership.
    with SessionLocal() as db:
        links=db.scalars(select(TicketLink).where((TicketLink.ticket_a_id==ticket_id)|
            (TicketLink.ticket_b_id==ticket_id))).all()
        ids=[link.ticket_b_id if link.ticket_a_id==ticket_id else link.ticket_a_id for link in links]
        return list(db.scalars(select(Ticket).where(Ticket.id.in_(ids),
            Ticket.customer_id==record['ticket'].customer_id).order_by(Ticket.created_at.desc()))) if ids else []


def update_sla_policy(actor: User, priority: str, response_minutes: int, resolution_minutes: int) -> None:
    """Admin changes apply to subsequently created tickets; existing due dates remain snapshotted."""
    if actor.role!='admin':raise SupportError('Only administrators can update SLA policies.')
    if not isinstance(response_minutes,int) or not isinstance(resolution_minutes,int):
        raise SupportError('Deadlines must be whole minutes.')
    if not (1<=response_minutes<=resolution_minutes<=60*24*30):
        raise SupportError('Require 1 ≤ response ≤ resolution ≤ 30 days.')
    with SessionLocal.begin() as db:
        policy=db.get(SLAPolicy,priority)
        if not policy:raise SupportError('Unknown priority.')
        db.add(SLAPolicyChange(priority=priority,
            old_first_response_minutes=policy.first_response_minutes,
            old_resolution_minutes=policy.resolution_minutes,
            new_first_response_minutes=response_minutes,new_resolution_minutes=resolution_minutes,
            actor_id=actor.id))
        policy.first_response_minutes=response_minutes
        policy.resolution_minutes=resolution_minutes
        db.add(AuditEvent(actor_id=actor.id,event_type='SLA_POLICY_UPDATED',
            details=f'{priority}: response {response_minutes}m, resolution {resolution_minutes}m'))


def refund_history(actor: User, refund_id: int) -> list[RefundEvent]:
    """Read-only event ledger with the same customer authorization as ticket details."""
    with SessionLocal() as db:
        refund=db.get(Refund,refund_id)
        if refund is None:raise SupportError('Refund not found.')
        ticket=ticket_detail(actor,refund.ticket_id)
        if ticket['ticket'].customer_id is None:raise SupportError('Ticket not found.')
        return list(db.scalars(select(RefundEvent).where(RefundEvent.refund_id==refund_id)
            .order_by(RefundEvent.occurred_at,RefundEvent.id)))


# ------------------------------------------------------------
# Stage 4.5: explicit ticket resolution, closure, and reopening
# ------------------------------------------------------------
def _ticket_action_blockers(db, ticket_id: str) -> list[str]:
    """Business actions that must finish before a case may be resolved or closed."""
    blocked = []
    if db.scalar(select(EscalationAssignment.id).where(
            EscalationAssignment.ticket_id == ticket_id,
            EscalationAssignment.status.in_(['OPEN', 'ACKNOWLEDGED']))) is not None:
        blocked.append('A human escalation is still assigned and open.')
    if db.scalar(select(ApprovalRequest.id).where(
            ApprovalRequest.ticket_id == ticket_id,
            ApprovalRequest.status == 'PENDING')) is not None:
        blocked.append('A human approval is still pending.')
    if db.scalar(select(Refund.id).where(
            Refund.ticket_id == ticket_id,
            Refund.status.in_(['REQUESTED', 'PENDING_APPROVAL', 'APPROVED', 'PROCESSING']))) is not None:
        blocked.append('A refund request has not finished processing.')
    if db.scalar(select(Commitment.id).where(
            Commitment.ticket_id == ticket_id,
            Commitment.completed_at.is_(None))) is not None:
        blocked.append('One or more customer promises are still open.')
    return blocked


def ticket_action_blockers(actor: User, ticket_id: str) -> list[str]:
    """Display safe reasons for disabled ticket actions; mutations still recheck."""
    if not may_manage_tickets(actor.role):
        raise SupportError('Support staff access required.')
    with SessionLocal() as db:
        if not db.get(Ticket, ticket_id):
            raise SupportError('Ticket not found.')
        return _ticket_action_blockers(db, ticket_id)


def _notify_ticket_transition(db, ticket: Ticket, *, title: str, body: str):
    note = Notification(customer_id=ticket.customer_id, ticket_id=ticket.id,
                        title=title, body=body)
    db.add(note)
    db.flush()
    db.add(OutboxEvent(dedupe_key=f'notification:{note.id}',
                       customer_id=ticket.customer_id, notification_id=note.id))


def resolve_ticket(actor: User, ticket_id: str, resolution_note: str) -> None:
    """Agent confirms issue is actually resolved (not merely that a reply was sent)."""
    if not may_manage_tickets(actor.role):
        raise SupportError('Only support staff can resolve tickets.')
    resolution_note = resolution_note.strip()
    if not 10 <= len(resolution_note) <= 1000:
        raise SupportError('Resolution note must contain 10–1,000 characters.')
    from .reply_policy import validate_informational_update
    validate_informational_update(resolution_note)
    with SessionLocal.begin() as db:
        ticket = db.get(Ticket, ticket_id)
        if not ticket:
            raise SupportError('Ticket not found.')
        if ticket.status not in ACTIVE_STATUSES:
            raise SupportError('Only an active ticket can be marked resolved.')
        blockers = _ticket_action_blockers(db, ticket_id)
        if blockers:
            raise SupportError('Cannot resolve: ' + ' '.join(blockers))
        now = utcnow()
        changed = db.execute(update(Ticket).where(
            Ticket.id == ticket_id, Ticket.status == ticket.status).values(
            status='RESOLVED', resolved_at=now, updated_at=now))
        if changed.rowcount != 1:
            raise SupportError('Ticket status changed; refresh before resolving.')
        message = 'Our support team has marked this request as resolved. ' + resolution_note
        db.add(TicketMessage(ticket_id=ticket_id, sender_id=actor.id,
                             sender_kind='agent', body=message))
        db.add(AuditEvent(actor_id=actor.id, ticket_id=ticket_id,
                          event_type='TICKET_RESOLVED', details=resolution_note))
        _notify_ticket_transition(db, ticket,
            title=f'Your support request was resolved · {ticket_id}', body=message[:400])


def close_ticket(actor: User, ticket_id: str) -> None:
    """Close a resolved ticket; no pending customer obligation may be discarded."""
    if not may_manage_tickets(actor.role):
        raise SupportError('Only support staff can close tickets.')
    with SessionLocal.begin() as db:
        ticket = db.get(Ticket, ticket_id)
        if ticket is None:
            raise SupportError('Ticket not found.')
        if ticket.status != 'RESOLVED':
            raise SupportError('Mark the ticket Resolved before closing it.')
        blockers = _ticket_action_blockers(db, ticket_id)
        if blockers:
            raise SupportError('Cannot close: ' + ' '.join(blockers))
        now = utcnow()
        changed = db.execute(update(Ticket).where(
            Ticket.id == ticket_id, Ticket.status == 'RESOLVED').values(
            status='CLOSED', updated_at=now))
        if changed.rowcount != 1:
            raise SupportError('Ticket status changed; refresh before closing.')
        db.add(AuditEvent(actor_id=actor.id, ticket_id=ticket_id,
                          event_type='TICKET_CLOSED', details='Closed after resolution'))
        _notify_ticket_transition(db, ticket,
            title=f'Support request closed · {ticket_id}',
            body='Your resolved request is now closed. Reply to this ticket if the issue returns.')


def reopen_ticket(actor: User, ticket_id: str, reason: str) -> None:
    """Support staff can explicitly reopen resolved or closed cases."""
    if not may_manage_tickets(actor.role):
        raise SupportError('Only support staff can reopen tickets.')
    reason = reason.strip()
    if not 10 <= len(reason) <= 1000:
        raise SupportError('Reopening reason must contain 10–1,000 characters.')
    with SessionLocal.begin() as db:
        ticket = db.get(Ticket, ticket_id)
        if ticket is None:
            raise SupportError('Ticket not found.')
        if ticket.status not in {'RESOLVED', 'CLOSED'}:
            raise SupportError('Only resolved or closed tickets can be reopened.')
        previous = ticket.status
        now = utcnow()
        changed = db.execute(update(Ticket).where(
            Ticket.id == ticket_id, Ticket.status == previous).values(
            status='REOPENED', resolved_at=None, updated_at=now))
        if changed.rowcount != 1:
            raise SupportError('Ticket status changed; refresh before reopening.')
        db.add(AuditEvent(actor_id=actor.id, ticket_id=ticket_id,
                          event_type='TICKET_REOPENED', details=reason))
        message = 'Your support request has been reopened: ' + reason
        db.add(TicketMessage(ticket_id=ticket_id, sender_id=actor.id,
                             sender_kind='agent', body=message))
        _notify_ticket_transition(db, ticket,
            title=f'Support request reopened · {ticket_id}', body=message[:400])


# ------------------------------------------------------------
# Stage 4.6: explicit staff escalation routing (separate from refund authorization)
# ------------------------------------------------------------
_ACTIVE_ESCALATIONS = ('OPEN', 'ACKNOWLEDGED')
_ESCALATION_TARGETS = {
    'agent': ('approver', 'admin'),
    'approver': ('agent', 'admin'),
    'admin': ('agent', 'approver', 'admin'),
}


def escalation_targets(actor: User) -> list[User]:
    """Return authorized human destinations for this actor, never customers or self."""
    if not may_manage_tickets(actor.role):
        raise SupportError('Only support staff may route escalations.')
    with SessionLocal() as db:
        allowed = _ESCALATION_TARGETS.get(actor.role, ())
        return list(db.scalars(select(User).where(
            User.role.in_(allowed), User.id != actor.id).order_by(User.name)))


def escalation_history(actor: User, ticket_id: str) -> list[dict]:
    if not may_manage_tickets(actor.role):
        raise SupportError('Staff-only escalation history.')
    with SessionLocal() as db:
        if db.get(Ticket, ticket_id) is None:
            raise SupportError('Ticket not found.')
        results = db.scalars(select(EscalationAssignment).where(
            EscalationAssignment.ticket_id == ticket_id)
            .order_by(EscalationAssignment.created_at.desc(), EscalationAssignment.id.desc())).all()
        return [{'record': e, 'assignee': db.get(User, e.assigned_to),
                 'raised_by': db.get(User, e.raised_by)} for e in results]


def escalation_queue(actor: User) -> list[dict]:
    """Assigned cases plus AI-flagged tickets not yet routed to a human."""
    if not may_manage_tickets(actor.role):
        raise SupportError('Staff-only escalation queue.')
    with SessionLocal() as db:
        active = list(db.scalars(select(EscalationAssignment).where(
            EscalationAssignment.status.in_(_ACTIVE_ESCALATIONS))
            .order_by(EscalationAssignment.created_at.desc(), EscalationAssignment.id.desc())))
        assigned_ticket_ids = {e.ticket_id for e in active}
        unassigned = list(db.scalars(select(Ticket).where(
            Ticket.escalated.is_(True), Ticket.status.notin_(['RESOLVED', 'CLOSED']))
            .order_by(Ticket.created_at.desc())))
        rows = [{'ticket': db.get(Ticket, e.ticket_id), 'assignment': e,
                 'assignee': db.get(User, e.assigned_to)} for e in active]
        rows += [{'ticket': t, 'assignment': None, 'assignee': None}
                 for t in unassigned if t.id not in assigned_ticket_ids]
        return rows


def _validate_target(db, actor: User, target_id: int) -> User:
    destination = db.get(User, target_id)
    allowed = _ESCALATION_TARGETS.get(actor.role, ())
    if (destination is None or destination.id == actor.id
            or destination.role not in allowed):
        raise SupportError('Choose another authorized staff member for escalation.')
    return destination


def escalate_ticket(actor: User, ticket_id: str, assignee_id: int, reason: str) -> int:
    """Create a durable human handoff with an internal reason and customer-safe notice."""
    if not may_manage_tickets(actor.role):
        raise SupportError('Only support staff may escalate tickets.')
    reason = reason.strip()
    if not 10 <= len(reason) <= 2000:
        raise SupportError('Provide an escalation reason (10–2,000 characters).')
    with SessionLocal.begin() as db:
        ticket = db.get(Ticket, ticket_id)
        if ticket is None:
            raise SupportError('Ticket not found.')
        if ticket.status in {'RESOLVED', 'CLOSED'}:
            raise SupportError('Reopen this ticket before escalating it.')
        dest = _validate_target(db, actor, int(assignee_id))
        existing = db.scalar(select(EscalationAssignment.id).where(
            EscalationAssignment.ticket_id == ticket_id,
            EscalationAssignment.status.in_(_ACTIVE_ESCALATIONS)))
        if existing is not None:
            raise SupportError('This ticket already has an active human escalation. Use Reassign.')
        now = utcnow()
        record = EscalationAssignment(ticket_id=ticket_id, raised_by=actor.id,
            assigned_to=dest.id, reason=reason, status='OPEN', created_at=now)
        db.add(record)
        db.flush()
        ticket.escalated = True
        ticket.owner_id = dest.id
        ticket.updated_at = now
        db.add(AuditEvent(ticket_id=ticket_id, actor_id=actor.id,
            event_type='ESCALATION_ASSIGNED',
            details=f'Escalation #{record.id} assigned to {dest.name} ({dest.role}); reason: {reason}'))
        # Customer sees no internal escalation notes or private staff details.
        _notify_ticket_transition(db, ticket,
            title=f'Your support request is under specialist review · {ticket_id}',
            body='We have referred your request to a specialist support colleague. '
                 'Your support ticket remains open while we investigate.')
        return record.id


def reassign_escalation(actor: User, escalation_id: int, target_id: int, reason: str) -> None:
    """The current recipient or admin may reroute the same open escalation."""
    if not may_manage_tickets(actor.role):
        raise SupportError('Support staff access required.')
    reason = reason.strip()
    if not 10 <= len(reason) <= 1000:
        raise SupportError('Explain the reassignment (10–1,000 characters).')
    with SessionLocal.begin() as db:
        assignment = db.get(EscalationAssignment, escalation_id)
        if not assignment or assignment.status not in _ACTIVE_ESCALATIONS:
            raise SupportError('Active escalation not found.')
        if actor.role != 'admin' and actor.id != assignment.assigned_to:
            raise SupportError('Only the assignee or administrator may reassign this escalation.')
        dest = _validate_target(db, actor, int(target_id))
        if dest.id == assignment.assigned_to:
            raise SupportError('The escalation is already assigned to this person.')
        previous = db.get(User, assignment.assigned_to)
        assignment.assigned_to = dest.id
        assignment.status = 'OPEN'
        assignment.acknowledged_at = None
        ticket = db.get(Ticket, assignment.ticket_id)
        ticket.owner_id = dest.id
        ticket.updated_at = utcnow()
        db.add(AuditEvent(actor_id=actor.id, ticket_id=ticket.id,
            event_type='ESCALATION_REASSIGNED',
            details=f'Escalation #{assignment.id}: {previous.name} → {dest.name}; {reason}'))


def acknowledge_escalation(actor: User, escalation_id: int) -> None:
    if not may_manage_tickets(actor.role):
        raise SupportError('Support staff access required.')
    with SessionLocal.begin() as db:
        rec = db.get(EscalationAssignment, escalation_id)
        if not rec or rec.status != 'OPEN':
            raise SupportError('Only a new escalation can be acknowledged.')
        if actor.role != 'admin' and actor.id != rec.assigned_to:
            raise SupportError('Only the assignee or administrator can acknowledge this case.')
        rec.status, rec.acknowledged_at = 'ACKNOWLEDGED', utcnow()
        db.add(AuditEvent(actor_id=actor.id, ticket_id=rec.ticket_id,
            event_type='ESCALATION_ACKNOWLEDGED', details=f'Escalation #{rec.id} accepted for review'))


def complete_escalation(actor: User, escalation_id: int, note: str) -> None:
    """Finish the human routing record; NEVER approve a refund or close a ticket."""
    if not may_manage_tickets(actor.role):
        raise SupportError('Support staff access required.')
    note = note.strip()
    if not 10 <= len(note) <= 2000:
        raise SupportError('Provide an escalation outcome (10–2,000 characters).')
    with SessionLocal.begin() as db:
        rec = db.get(EscalationAssignment, escalation_id)
        if not rec or rec.status not in _ACTIVE_ESCALATIONS:
            raise SupportError('No active escalation to complete.')
        if actor.role != 'admin' and actor.id != rec.assigned_to:
            raise SupportError('Only the assignee or administrator can complete this escalation.')
        blockers = _ticket_action_blockers(db, rec.ticket_id)
        blockers = [b for b in blockers if 'human escalation is still assigned' not in b]
        if blockers:
            raise SupportError('Cannot finish escalation: ' + ' '.join(blockers))
        rec.status = 'COMPLETED'
        rec.completed_at = utcnow()
        rec.completion_note = note
        ticket = db.get(Ticket, rec.ticket_id)
        ticket.escalated = False
        ticket.updated_at = utcnow()
        db.add(AuditEvent(actor_id=actor.id, ticket_id=ticket.id,
            event_type='ESCALATION_COMPLETED', details=f'Escalation #{rec.id}: {note}'))
        # No automatic RESOLVED state; the support agent must record actual resolution separately.
