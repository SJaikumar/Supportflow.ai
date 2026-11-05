"""Human-reviewed image observation. Never authorizes a refund or diagnoses damage cause."""
from __future__ import annotations
import base64
import io
import json
import os
from PIL import Image, UnidentifiedImageError
from sqlalchemy import select
from .config import UPLOAD_DIR
from .db import SessionLocal
from .models import (Attachment, AuditEvent, Customer, PhotoConsent,
                     PhotoInspection, Ticket, utcnow)
from .security import may_manage_tickets
from .services import SupportError


def grant_photo_consent(actor, attachment_id: int) -> None:
    if actor.role != 'customer':
        raise SupportError('Only the customer can authorize photo inspection.')
    with SessionLocal.begin() as db:
        attachment = db.get(Attachment, attachment_id)
        if not attachment:
            raise SupportError('Attachment not found.')
        ticket = db.get(Ticket, attachment.ticket_id)
        customer = db.get(Customer, ticket.customer_id)
        if customer.user_id != actor.id:
            raise SupportError('You cannot authorize another customer’s photos.')
        if db.get(PhotoConsent, attachment_id) is None:
            db.add(PhotoConsent(attachment_id=attachment_id, customer_user_id=actor.id))
            db.add(AuditEvent(actor_id=actor.id, ticket_id=ticket.id,
                event_type='PHOTO_AI_CONSENT_GRANTED', details=f'Attachment #{attachment_id}'))


def revoke_photo_consent(actor, attachment_id: int) -> None:
    """Withdraw permission for future AI transmissions. Existing audits remain for accountability."""
    if actor.role != 'customer':
        raise SupportError('Only the customer can withdraw photo consent.')
    with SessionLocal.begin() as db:
        attachment = db.get(Attachment, attachment_id)
        if not attachment:
            raise SupportError('Attachment not found.')
        ticket = db.get(Ticket, attachment.ticket_id)
        customer = db.get(Customer, ticket.customer_id)
        if customer.user_id != actor.id:
            raise SupportError('You cannot change another customer’s photo consent.')
        existing = db.get(PhotoConsent, attachment_id)
        if existing:
            db.delete(existing)
            db.add(AuditEvent(actor_id=actor.id, ticket_id=ticket.id,
                              event_type='PHOTO_AI_CONSENT_WITHDRAWN',
                              details=f'Attachment #{attachment_id}'))


def photo_details(actor, ticket_id: str) -> list[dict]:
    from .services import ticket_detail
    record = ticket_detail(actor, ticket_id)  # ownership + role check
    with SessionLocal() as db:
        items = []
        for attachment in record['attachments']:
            consent = db.get(PhotoConsent, attachment.id)
            runs = list(db.scalars(select(PhotoInspection).where(
                PhotoInspection.attachment_id == attachment.id).order_by(
                PhotoInspection.created_at.desc(), PhotoInspection.id.desc())))
            items.append({'attachment': attachment, 'consented': consent is not None,
                          'inspections': runs if actor.role != 'customer' else []})
        return items


def _model_observe(image: bytes, *, model: str) -> dict:
    from openai import OpenAI
    key = os.getenv('OPENAI_API_KEY', '').strip()
    if not key:
        raise SupportError('OPENAI_API_KEY not configured; photo inspection is unavailable.')
    result = OpenAI(api_key=key, timeout=40).chat.completions.create(
        model=model,
        response_format={'type': 'json_object'},
        messages=[
            {'role': 'system', 'content': (
                'You are a product support image-description assistant. '
                'Describe only observable visual features and possible physical defects. '
                'Do not infer when damage occurred, who is responsible, or warranty/refund eligibility. '
                'Reply with JSON object keys summary (string), visible_signs (array of strings), '
                'uncertainties (string), human_review_required (true).')},
            {'role': 'user', 'content': [
                {'type': 'text', 'text': 'Describe the visible product condition cautiously. Do not identify people.'},
                {'type': 'image_url', 'image_url': {
                    'url': 'data:image/jpeg;base64,' + base64.b64encode(image).decode('ascii'),
                    'detail': 'low'}}
            ]},
        ],
    )
    raw = result.choices[0].message.content or '{}'
    return json.loads(raw)


def inspect_photo(actor, attachment_id: int, *, inspector=None, model: str | None = None) -> int:
    """Staff-triggered analysis. Human authorization still required for any action.

    An injected inspector callable permits offline tests without external model calls.
    """
    if not may_manage_tickets(actor.role):
        raise SupportError('Only authorized staff can inspect images.')
    with SessionLocal() as db:
        attachment = db.get(Attachment, attachment_id)
        if attachment is None:
            raise SupportError('Photo not found.')
        if db.get(PhotoConsent, attachment_id) is None:
            raise SupportError('Customer consent is required before AI photo inspection.')
        ticket_id = attachment.ticket_id
        filename = attachment.stored_filename
    path = UPLOAD_DIR / filename
    if not path.is_file():
        raise SupportError('Original attachment file is unavailable.')
    try:
        with Image.open(path) as img:
            if img.width * img.height > 25_000_000:
                raise SupportError('Photo dimensions exceed the safe inspection limit.')
            img = img.convert('RGB')
            img.thumbnail((1024, 1024))
            stream = io.BytesIO()
            img.save(stream, format='JPEG', quality=82)
            scrubbed_image = stream.getvalue()  # normalizes format; strips EXIF metadata
    except (OSError, UnidentifiedImageError) as exc:
        raise SupportError('Could not decode the photo for inspection.') from exc
    model = model or os.getenv('SUPPORTFLOW_VISION_MODEL', 'gpt-4o-mini')
    with SessionLocal.begin() as db:
        run = PhotoInspection(attachment_id=attachment_id, initiated_by=actor.id,
                              model=model, status='RUNNING')
        db.add(run)
        db.flush()
        run_id = run.id
    try:
        raw = (inspector(scrubbed_image) if inspector is not None
               else _model_observe(scrubbed_image, model=model))
        if not isinstance(raw, dict):
            raise ValueError('Inspector output must be a JSON object')
        observation = {
            'summary': str(raw.get('summary') or 'No reliable visible observation.')[:1300],
            'visible_signs': [str(x)[:250] for x in raw.get('visible_signs', []) if isinstance(x, str)][:8],
            'uncertainties': str(raw.get('uncertainties') or 'Visual inspection alone cannot establish cause.')[:800],
            'human_review_required': True,
            'caveat': 'Visual observations only; not a defect verdict or refund authorization.',
        }
        with SessionLocal.begin() as db:
            r = db.get(PhotoInspection, run_id)
            r.status = 'SUCCEEDED'
            r.observations_json = json.dumps(observation, ensure_ascii=False)
            r.completed_at = utcnow()
            db.add(AuditEvent(actor_id=actor.id, ticket_id=ticket_id,
                              event_type='PHOTO_INSPECTION_COMPLETED', details=f'Inspection #{run_id}'))
    except Exception as exc:
        with SessionLocal.begin() as db:
            r = db.get(PhotoInspection, run_id)
            r.status = 'FAILED'
            r.error = f'{type(exc).__name__}: Could not complete image analysis.'[:300]
            r.completed_at = utcnow()
            db.add(AuditEvent(actor_id=actor.id, ticket_id=ticket_id,
                              event_type='PHOTO_INSPECTION_FAILED', details=f'Inspection #{run_id}'))
        # The underlying exception is intentionally not stored in the customer-facing DB.
        raise SupportError(f'Photo inspection failed ({type(exc).__name__}). Check your model access and connection.') from exc
    return run_id
