"""Relational data model. SQLite is the primary relational source of truth."""
from datetime import datetime, timezone
from sqlalchemy import DateTime, ForeignKey, Integer, String, Boolean, Text, UniqueConstraint
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


def utcnow() -> datetime:
    """Naive UTC for consistent cross-platform SQLite DateTime round-tripping."""
    return datetime.now(timezone.utc).replace(tzinfo=None)

class Base(DeclarativeBase):
    pass

class User(Base):
    __tablename__='users'
    id: Mapped[int] = mapped_column(primary_key=True)
    email: Mapped[str] = mapped_column(String(220), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(140))
    password_hash: Mapped[str] = mapped_column(String(200))
    role: Mapped[str] = mapped_column(String(20), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)

class Customer(Base):
    __tablename__='customers'
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey('users.id'), unique=True, index=True)
    code: Mapped[str] = mapped_column(String(30), unique=True)
    joined_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    notes: Mapped[str] = mapped_column(Text, default='')

class Order(Base):
    __tablename__='orders'
    id: Mapped[str] = mapped_column(String(30), primary_key=True)
    customer_id: Mapped[int] = mapped_column(ForeignKey('customers.id'), index=True)
    placed_at: Mapped[datetime] = mapped_column(DateTime)
    promised_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    delivered_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    status: Mapped[str] = mapped_column(String(30), default='DELIVERED')
    total_cents: Mapped[int] = mapped_column(Integer)
    currency: Mapped[str] = mapped_column(String(3), default='INR')

class OrderItem(Base):
    __tablename__='order_items'
    id: Mapped[int] = mapped_column(primary_key=True)
    order_id: Mapped[str] = mapped_column(ForeignKey('orders.id'), index=True)
    product_name: Mapped[str] = mapped_column(String(160))
    quantity: Mapped[int] = mapped_column(Integer, default=1)
    unit_price_cents: Mapped[int] = mapped_column(Integer)

class Ticket(Base):
    __tablename__='tickets'
    id: Mapped[str] = mapped_column(String(30), primary_key=True)
    customer_id: Mapped[int] = mapped_column(ForeignKey('customers.id'), index=True)
    order_id: Mapped[str | None] = mapped_column(ForeignKey('orders.id'), nullable=True)
    title: Mapped[str] = mapped_column(String(180))
    complaint: Mapped[str] = mapped_column(Text)
    category: Mapped[str] = mapped_column(String(50))
    priority: Mapped[str] = mapped_column(String(2), default='P3')
    status: Mapped[str] = mapped_column(String(40), default='NEW', index=True)
    escalated: Mapped[bool] = mapped_column(Boolean, default=False)
    owner_id: Mapped[int | None] = mapped_column(ForeignKey('users.id'), nullable=True)
    first_response_due: Mapped[datetime] = mapped_column(DateTime)
    resolution_due: Mapped[datetime] = mapped_column(DateTime)
    first_responded_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)

class TicketMessage(Base):
    __tablename__='ticket_messages'
    id: Mapped[int] = mapped_column(primary_key=True)
    ticket_id: Mapped[str] = mapped_column(ForeignKey('tickets.id'), index=True)
    sender_id: Mapped[int | None] = mapped_column(ForeignKey('users.id'), nullable=True)
    sender_kind: Mapped[str] = mapped_column(String(25))
    body: Mapped[str] = mapped_column(Text)
    visible_to_customer: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)

class ApprovalRequest(Base):
    __tablename__='approval_requests'
    id: Mapped[int] = mapped_column(primary_key=True)
    ticket_id: Mapped[str] = mapped_column(ForeignKey('tickets.id'), index=True)
    action: Mapped[str] = mapped_column(String(30), default='REFUND')
    proposed_amount_cents: Mapped[int] = mapped_column(Integer, default=0)
    draft_response: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(20), default='PENDING')
    requested_by: Mapped[int | None] = mapped_column(ForeignKey('users.id'), nullable=True)
    reviewer_id: Mapped[int | None] = mapped_column(ForeignKey('users.id'), nullable=True)
    reviewer_reason: Mapped[str] = mapped_column(Text, default='')
    approved_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

class Refund(Base):
    __tablename__='refunds'
    id: Mapped[int] = mapped_column(primary_key=True)
    ticket_id: Mapped[str] = mapped_column(ForeignKey('tickets.id'), index=True)
    order_id: Mapped[str] = mapped_column(ForeignKey('orders.id'), index=True)
    approval_id: Mapped[int | None] = mapped_column(ForeignKey('approval_requests.id'), unique=True, nullable=True)
    amount_cents: Mapped[int] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(30), default='REQUESTED')
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    processed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

class Notification(Base):
    __tablename__='notifications'
    id: Mapped[int] = mapped_column(primary_key=True)
    customer_id: Mapped[int] = mapped_column(ForeignKey('customers.id'), index=True)
    ticket_id: Mapped[str | None] = mapped_column(ForeignKey('tickets.id'), nullable=True)
    title: Mapped[str] = mapped_column(String(180))
    body: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    read_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

class SLAPolicy(Base):
    __tablename__='sla_policies'
    priority: Mapped[str] = mapped_column(String(2), primary_key=True)
    first_response_minutes: Mapped[int] = mapped_column(Integer)
    resolution_minutes: Mapped[int] = mapped_column(Integer)

class Attachment(Base):
    __tablename__='attachments'
    id: Mapped[int] = mapped_column(primary_key=True)
    ticket_id: Mapped[str] = mapped_column(ForeignKey('tickets.id'), index=True)
    uploaded_by: Mapped[int] = mapped_column(ForeignKey('users.id'))
    original_filename: Mapped[str] = mapped_column(String(200))
    stored_filename: Mapped[str] = mapped_column(String(80))
    mime_type: Mapped[str] = mapped_column(String(40))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)

class AuditEvent(Base):
    __tablename__='audit_events'
    id: Mapped[int] = mapped_column(primary_key=True)
    actor_id: Mapped[int | None] = mapped_column(ForeignKey('users.id'), nullable=True)
    ticket_id: Mapped[str | None] = mapped_column(ForeignKey('tickets.id'), nullable=True)
    event_type: Mapped[str] = mapped_column(String(70), index=True)
    details: Mapped[str] = mapped_column(Text, default='')
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


# Stage 2 additions are new tables only: existing Stage 1.2 SQLite files remain readable.
class TicketCounter(Base):
    __tablename__ = 'ticket_counters'
    key: Mapped[str] = mapped_column(String(40), primary_key=True)
    last_value: Mapped[int] = mapped_column(Integer, nullable=False)


class OrderEvent(Base):
    __tablename__ = 'order_events'
    id: Mapped[int] = mapped_column(primary_key=True)
    order_id: Mapped[str] = mapped_column(ForeignKey('orders.id'), index=True)
    event_type: Mapped[str] = mapped_column(String(55))
    description: Mapped[str] = mapped_column(Text)
    actor_id: Mapped[int | None] = mapped_column(ForeignKey('users.id'), nullable=True)
    occurred_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class CustomerNote(Base):
    __tablename__ = 'customer_notes'
    id: Mapped[int] = mapped_column(primary_key=True)
    customer_id: Mapped[int] = mapped_column(ForeignKey('customers.id'), index=True)
    author_id: Mapped[int] = mapped_column(ForeignKey('users.id'))
    text: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class Commitment(Base):
    __tablename__ = 'commitments'
    id: Mapped[int] = mapped_column(primary_key=True)
    ticket_id: Mapped[str] = mapped_column(ForeignKey('tickets.id'), index=True)
    description: Mapped[str] = mapped_column(String(400))
    owner_id: Mapped[int] = mapped_column(ForeignKey('users.id'))
    created_by: Mapped[int] = mapped_column(ForeignKey('users.id'))
    due_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    customer_visible: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class ApprovalDecision(Base):
    __tablename__ = 'approval_decisions'
    id: Mapped[int] = mapped_column(primary_key=True)
    approval_id: Mapped[int] = mapped_column(ForeignKey('approval_requests.id'), unique=True, index=True)
    reviewer_id: Mapped[int] = mapped_column(ForeignKey('users.id'))
    outcome: Mapped[str] = mapped_column(String(20))
    reason: Mapped[str] = mapped_column(Text, default='')
    final_customer_message: Mapped[str] = mapped_column(Text)
    decided_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class RefundEvent(Base):
    __tablename__ = 'refund_events'
    id: Mapped[int] = mapped_column(primary_key=True)
    refund_id: Mapped[int] = mapped_column(ForeignKey('refunds.id'), index=True)
    status: Mapped[str] = mapped_column(String(30))
    description: Mapped[str] = mapped_column(String(400))
    actor_id: Mapped[int | None] = mapped_column(ForeignKey('users.id'), nullable=True)
    occurred_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class TicketLink(Base):
    __tablename__ = 'ticket_links'
    __table_args__ = (UniqueConstraint('ticket_a_id','ticket_b_id', name='uq_ticket_pair'),)
    id: Mapped[int] = mapped_column(primary_key=True)
    ticket_a_id: Mapped[str] = mapped_column(ForeignKey('tickets.id'), index=True)
    ticket_b_id: Mapped[str] = mapped_column(ForeignKey('tickets.id'), index=True)
    relation: Mapped[str] = mapped_column(String(35), default='RELATED')
    linked_by: Mapped[int | None] = mapped_column(ForeignKey('users.id'), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class OutboxEvent(Base):
    """Durable record of a customer portal delivery; email/SMS belongs to a later stage."""
    __tablename__ = 'outbox_events'
    id: Mapped[int] = mapped_column(primary_key=True)
    dedupe_key: Mapped[str] = mapped_column(String(140), unique=True, index=True)
    customer_id: Mapped[int] = mapped_column(ForeignKey('customers.id'))
    notification_id: Mapped[int] = mapped_column(ForeignKey('notifications.id'))
    channel: Mapped[str] = mapped_column(String(30), default='PORTAL')
    status: Mapped[str] = mapped_column(String(30), default='DELIVERED')
    delivered_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class SLAPolicyChange(Base):
    __tablename__ = 'sla_policy_changes'
    id: Mapped[int] = mapped_column(primary_key=True)
    priority: Mapped[str] = mapped_column(String(2), index=True)
    old_first_response_minutes: Mapped[int] = mapped_column(Integer)
    old_resolution_minutes: Mapped[int] = mapped_column(Integer)
    new_first_response_minutes: Mapped[int] = mapped_column(Integer)
    new_resolution_minutes: Mapped[int] = mapped_column(Integer)
    actor_id: Mapped[int] = mapped_column(ForeignKey('users.id'))
    changed_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class SeedMarker(Base):
    __tablename__ = 'seed_markers'
    code: Mapped[str] = mapped_column(String(80), primary_key=True)
    seeded_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)

# Stage 3: additive tables. They do not change or drop existing Stage 2 records.
class AIAnalysisRun(Base):
    __tablename__ = 'ai_analysis_runs'
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    ticket_id: Mapped[str] = mapped_column(ForeignKey('tickets.id'), index=True)
    initiated_by: Mapped[int] = mapped_column(ForeignKey('users.id'))
    status: Mapped[str] = mapped_column(String(20), default='RUNNING')
    model: Mapped[str] = mapped_column(String(100), default='gpt-4o-mini')
    retrieval_mode: Mapped[str] = mapped_column(String(60), default='Pending')
    classification_json: Mapped[str] = mapped_column(Text, default='{}')
    citations_json: Mapped[str] = mapped_column(Text, default='[]')
    draft_response: Mapped[str] = mapped_column(Text, default='')
    confidence: Mapped[str] = mapped_column(String(20), default='unknown')
    escalated: Mapped[bool] = mapped_column(Boolean, default=False)
    escalation_reasons_json: Mapped[str] = mapped_column(Text, default='[]')
    error: Mapped[str] = mapped_column(String(400), default='')
    started_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class AIAnalysisStep(Base):
    __tablename__ = 'ai_analysis_steps'
    id: Mapped[int] = mapped_column(primary_key=True)
    run_id: Mapped[str] = mapped_column(ForeignKey('ai_analysis_runs.id'), index=True)
    step_number: Mapped[int] = mapped_column(Integer)
    agent_name: Mapped[str] = mapped_column(String(30))
    output_json: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)

# Stage 4: additive operational tables. No migration of earlier ticket/order rows.
class SLAEvent(Base):
    """One audit event per ticket, SLA obligation and elapsed threshold."""
    __tablename__ = 'sla_events'
    __table_args__ = (UniqueConstraint('ticket_id', 'obligation', 'threshold_pct', name='uq_sla_milestone'),)
    id: Mapped[int] = mapped_column(primary_key=True)
    ticket_id: Mapped[str] = mapped_column(ForeignKey('tickets.id'), index=True)
    obligation: Mapped[str] = mapped_column(String(20))  # RESPONSE / RESOLUTION
    threshold_pct: Mapped[int] = mapped_column(Integer)
    due_at: Mapped[datetime] = mapped_column(DateTime)
    observed_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class StaffAlert(Base):
    """Persistent actionable alert, distinct from the customer's portal inbox."""
    __tablename__ = 'staff_alerts'
    id: Mapped[int] = mapped_column(primary_key=True)
    dedupe_key: Mapped[str] = mapped_column(String(150), unique=True, index=True)
    ticket_id: Mapped[str] = mapped_column(ForeignKey('tickets.id'), index=True)
    commitment_id: Mapped[int | None] = mapped_column(ForeignKey('commitments.id'), nullable=True)
    category: Mapped[str] = mapped_column(String(25))
    severity: Mapped[str] = mapped_column(String(15), default='WARNING')
    title: Mapped[str] = mapped_column(String(180))
    details: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    acknowledged_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    acknowledged_by: Mapped[int | None] = mapped_column(ForeignKey('users.id'), nullable=True)
    cleared_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class CommitmentReminder(Base):
    __tablename__ = 'commitment_reminders'
    __table_args__ = (UniqueConstraint('commitment_id', 'event_type', name='uq_commitment_reminder'),)
    id: Mapped[int] = mapped_column(primary_key=True)
    commitment_id: Mapped[int] = mapped_column(ForeignKey('commitments.id'), index=True)
    event_type: Mapped[str] = mapped_column(String(20))  # DUE_SOON, OVERDUE
    emitted_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class PhotoInspection(Base):
    __tablename__ = 'photo_inspections'
    id: Mapped[int] = mapped_column(primary_key=True)
    attachment_id: Mapped[int] = mapped_column(ForeignKey('attachments.id'), index=True)
    initiated_by: Mapped[int] = mapped_column(ForeignKey('users.id'))
    status: Mapped[str] = mapped_column(String(20), default='RUNNING')
    model: Mapped[str] = mapped_column(String(100), default='gpt-4o-mini')
    observations_json: Mapped[str] = mapped_column(Text, default='{}')
    error: Mapped[str] = mapped_column(String(300), default='')
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class WorkerRun(Base):
    __tablename__ = 'worker_runs'
    id: Mapped[int] = mapped_column(primary_key=True)
    started_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    status: Mapped[str] = mapped_column(String(20), default='RUNNING')
    event_count: Mapped[int] = mapped_column(Integer, default=0)
    error: Mapped[str] = mapped_column(String(400), default='')

class PhotoConsent(Base):
    """Customer opt-in required before a photo is sent to an external vision model."""
    __tablename__ = 'photo_consents'
    attachment_id: Mapped[int] = mapped_column(ForeignKey('attachments.id'), primary_key=True)
    customer_user_id: Mapped[int] = mapped_column(ForeignKey('users.id'))
    granted_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class EscalationAssignment(Base):
    """Human routing event; AI escalation flags are retained separately on Ticket."""
    __tablename__ = 'escalation_assignments'
    id: Mapped[int] = mapped_column(primary_key=True)
    ticket_id: Mapped[str] = mapped_column(ForeignKey('tickets.id'), index=True)
    raised_by: Mapped[int] = mapped_column(ForeignKey('users.id'))
    assigned_to: Mapped[int] = mapped_column(ForeignKey('users.id'), index=True)
    reason: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(20), default='OPEN', index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    acknowledged_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    completion_note: Mapped[str] = mapped_column(Text, default='')

