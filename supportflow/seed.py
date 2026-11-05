"""Repeat-safe seed data for offline demonstration. No real customer data."""
from datetime import datetime, timedelta
from sqlalchemy import select, func
from .db import SessionLocal, initialize
from .models import (User, Customer, Order, OrderItem, Ticket, TicketMessage,
                     ApprovalRequest, Refund, Notification, SLAPolicy, AuditEvent, utcnow)
from .security import hash_password

DEMO_PASSWORD = 'Demo123!'
DEMO_ACCOUNTS = [
    ('priya@demo.com','Priya Sharma','customer'),
    ('raj@demo.com','Raj Mehta','customer'),
    ('neha@demo.com','Neha Gupta','customer'),
    ('alex@demo.com','Alex Morgan','agent'),
    ('maya@demo.com','Maya Rao','approver'),
    ('admin@demo.com','SupportFlow Admin','admin'),
]

POLICIES = {'P1':(15,240), 'P2':(60,480), 'P3':(240,1440), 'P4':(480,2880)}


def seed_if_empty():
    initialize()
    with SessionLocal.begin() as db:
        if db.scalar(select(func.count()).select_from(User)):
            return False
        now=utcnow()
        users={}
        for email,name,role in DEMO_ACCOUNTS:
            person=User(email=email,name=name,role=role,password_hash=hash_password(DEMO_PASSWORD),created_at=now-timedelta(days=270))
            db.add(person);db.flush();users[email]=person
        customers={}
        for i,email in enumerate(['priya@demo.com','raj@demo.com','neha@demo.com'],start=1007):
            u=users[email]
            customer=Customer(user_id=u.id,code=f'CUST-{i}',joined_at=now-timedelta(days=350-i%7*20))
            db.add(customer);db.flush();customers[email]=customer
        for priority,(fr,res) in POLICIES.items():
            db.add(SLAPolicy(priority=priority,first_response_minutes=fr,resolution_minutes=res))

        order_specs = [
            ('ORD-88241','priya@demo.com','Mixer Grinder',249900,'DELIVERED',8,4,3),
            ('ORD-88102','priya@demo.com','Wireless Headphones',379900,'DELIVERY_DELAYED',8,2,None),
            ('ORD-87219','priya@demo.com','Coffee Maker',499900,'REFUNDED',24,19,18),
            ('ORD-87215','priya@demo.com','Kitchen Blender',219900,'REFUNDED',75,71,69),
            ('ORD-87180','priya@demo.com','Ceramic Dinner Set',149900,'REFUNDED',107,101,99),
            ('ORD-87175','priya@demo.com','LED Desk Light',129900,'DELIVERED',128,123,122),
            ('ORD-87161','priya@demo.com','Travel Backpack',199900,'DELIVERED',144,137,136),
            ('ORD-87144','priya@demo.com','Cotton Bedsheet',189900,'DELIVERED',162,158,156),
            ('ORD-87120','priya@demo.com','Water Bottle',79900,'DELIVERED',183,179,177),
            ('ORD-87092','priya@demo.com','Electric Kettle',249900,'DELIVERED',195,191,190),
            ('ORD-87082','priya@demo.com','Lunch Box',89900,'DELIVERED',207,203,200),
            ('ORD-87071','priya@demo.com','Keyboard',259900,'DELIVERED',221,214,211),
            ('ORD-87062','priya@demo.com','Notebook Set',59900,'DELIVERED',239,235,233),
            ('ORD-87041','priya@demo.com','Phone Stand',49900,'DELIVERED',257,254,252),
            ('ORD-87021','priya@demo.com','Yoga Mat',119900,'DELIVERED',265,260,259),
            ('ORD-87015','priya@demo.com','Power Adapter',149900,'DELIVERED',271,267,265),
            ('ORD-87011','priya@demo.com','Desk Organizer',109900,'DELIVERED',282,278,276),
            ('ORD-87001','priya@demo.com','Storage Boxes',199900,'DELIVERED',294,290,288),
            ('ORD-88311','raj@demo.com','Smart Watch',699900,'DELIVERED',5,3,2),
            ('ORD-88312','raj@demo.com','Running Shoes',329900,'DELIVERED',9,6,4),
            ('ORD-88313','raj@demo.com','Bluetooth Speaker',279900,'DELIVERED',20,16,15),
            ('ORD-88314','raj@demo.com','Backpack',209900,'DELIVERED',44,40,38),
            ('ORD-88315','raj@demo.com','Phone Case',79900,'DELIVERED',68,64,61),
            ('ORD-88401','neha@demo.com','Air Fryer',899900,'DELIVERED',8,5,4),
            ('ORD-88402','neha@demo.com','Toaster',189900,'DELIVERED',25,20,19),
            ('ORD-88403','neha@demo.com','Glass Storage Set',129900,'DELIVERED',52,48,46),
        ]
        orders={}
        for order_id,email,product,cents,status,placed,promised,delivered in order_specs:
            order=Order(id=order_id,customer_id=customers[email].id,placed_at=now-timedelta(days=placed),
                promised_at=now-timedelta(days=promised) if promised is not None else None,
                delivered_at=now-timedelta(days=delivered) if delivered is not None else None,
                status=status,total_cents=cents,currency='INR')
            db.add(order);db.add(OrderItem(order_id=order_id,product_name=product,quantity=1,unit_price_cents=cents))
            orders[order_id]=order
        db.flush()

        ticket_specs = [
            # id, owner, order, category, priority, status, days ago, title, complaint, escalated
            ('TKT-10456','priya@demo.com','ORD-88241','Product quality','P2','AWAITING_APPROVAL',0,'Damaged mixer grinder','My mixer grinder arrived damaged. I have sent photos and would like a refund.',True),
            ('TKT-10455','raj@demo.com','ORD-88311','Billing','P1','IN_REVIEW',0,'Duplicate payment charged','I was charged three times for my watch. Please investigate urgently.',True),
            ('TKT-10451','raj@demo.com','ORD-88312','Refund','P1','AWAITING_APPROVAL',0,'Refund decision pending','My shoes do not fit; I need an update about my refund.',True),
            ('TKT-10448','neha@demo.com','ORD-88401','Product quality','P2','IN_REVIEW',0,'Wrong product delivered','I ordered an air fryer but received a different product.',True),
            ('TKT-10398','priya@demo.com','ORD-88102','Delivery','P2','IN_REVIEW',1,'Delivery arrived late','My headphones were due two days ago. Where is the delivery?',False),
            ('TKT-10277','priya@demo.com','ORD-87219','Refund','P3','RESOLVED',16,'Refund status inquiry','Has the refund for my coffee maker been processed?',False),
            ('TKT-10221','priya@demo.com','ORD-87215','Product quality','P3','RESOLVED',62,'Damaged kitchen blender','The blender stopped working after one use.',False),
            ('TKT-10188','priya@demo.com','ORD-87180','Refund','P3','RESOLVED',93,'Incorrect item returned','I received the wrong colour of the dinner set.',False),
            ('TKT-10155','priya@demo.com','ORD-87175','Delivery','P3','RESOLVED',120,'Delivery confirmation','Can you confirm the delivery status?',False),
            ('TKT-10096','priya@demo.com',None,'Account','P4','RESOLVED',198,'Password reset help','I could not sign into my account.',False),
            ('TKT-10437','neha@demo.com','ORD-88402','Delivery','P2','IN_REVIEW',0,'Order delivery delayed','My toaster has not arrived yet.',False),
            ('TKT-10300','raj@demo.com','ORD-88313','Other','P4','RESOLVED',13,'Product question','Does the speaker include a charging cable?',False),
        ]
        for id,email,order_id,category,priority,status,age,title,complaint,escalated in ticket_specs:
            created=now-timedelta(days=age,hours=1 if age==0 else 0)
            first_mins,res_mins=POLICIES[priority]
            first_responded = created + timedelta(minutes=min(first_mins//2,20)) if status=='RESOLVED' else None
            # Give a few active tickets imminent clocks, and one breached
            if id=='TKT-10456': created=now-timedelta(minutes=30)
            if id=='TKT-10455': created=now-timedelta(minutes=35)
            if id=='TKT-10451': created=now-timedelta(minutes=12)
            if id=='TKT-10448': created=now-timedelta(minutes=40)
            if id=='TKT-10437': created=now-timedelta(minutes=55)
            ticket=Ticket(id=id, customer_id=customers[email].id, order_id=order_id, category=category,
                title=title,complaint=complaint,priority=priority,status=status,escalated=escalated,
                first_response_due=created+timedelta(minutes=first_mins),resolution_due=created+timedelta(minutes=res_mins),
                created_at=created,updated_at=created,first_responded_at=first_responded,
                resolved_at=created+timedelta(hours=3) if status=='RESOLVED' else None,
                owner_id=users['alex@demo.com'].id if status!='RESOLVED' else None)
            db.add(ticket)
            db.add(TicketMessage(ticket_id=id,sender_id=users[email].id,sender_kind='customer',
                body=complaint,visible_to_customer=True,created_at=created))
            if status=='RESOLVED':
                db.add(TicketMessage(ticket_id=id,sender_id=users['alex@demo.com'].id,
                    sender_kind='agent',body='Your support request has been reviewed and resolved. Thank you for contacting us.',
                    visible_to_customer=True,created_at=created+timedelta(hours=1)))
        db.flush()
        db.add(ApprovalRequest(ticket_id='TKT-10456',action='REFUND',proposed_amount_cents=249900,
            draft_response='I am sorry the mixer grinder arrived damaged. We have reviewed your request and approved a refund of ₹2,499.00. This is a simulated refund and will be marked complete once processing finishes.',
            status='PENDING',created_at=now-timedelta(minutes=17)))
        db.add(ApprovalRequest(ticket_id='TKT-10451',action='REFUND',proposed_amount_cents=329900,
            draft_response='We have reviewed the returned shoes and approved your refund of ₹3,299.00. We will notify you when simulated processing is complete.',
            status='PENDING',created_at=now-timedelta(minutes=8)))
        db.add(Refund(ticket_id='TKT-10456',order_id='ORD-88241',amount_cents=249900,status='PENDING_APPROVAL',created_at=now-timedelta(minutes=17)))
        db.add(Refund(ticket_id='TKT-10451',order_id='ORD-88312',amount_cents=329900,status='PENDING_APPROVAL',created_at=now-timedelta(minutes=8)))
        for tid,oid,amt in [('TKT-10277','ORD-87219',499900),('TKT-10221','ORD-87215',219900),('TKT-10188','ORD-87180',149900)]:
            db.add(Refund(ticket_id=tid,order_id=oid,amount_cents=amt,status='COMPLETED',processed_at=now-timedelta(days=20),created_at=now-timedelta(days=30)))
        priya=customers['priya@demo.com']
        db.add(Notification(customer_id=priya.id,ticket_id='TKT-10456',title='Your damage report is under review',
            body='Our support team is reviewing your mixer grinder request.',created_at=now-timedelta(minutes=10)))
        db.add(Notification(customer_id=priya.id,ticket_id='TKT-10398',title='Delivery investigation opened',
            body='We are checking the status of your headphones.',created_at=now-timedelta(hours=4)))
    return True

if __name__=='__main__':
    print('Demo seed initialized' if seed_if_empty() else 'Demo seed already present')


def seed_stage2_examples_if_missing() -> bool:
    """Add realistic Stage 2 example history to new OR existing Stage 1 demo DBs once.

    Does not reset or overwrite customer-created tickets, customer messages, or decisions.
    All inserted records are labeled as simulated. A separate marker keeps it idempotent.
    """
    from .models import (ApprovalDecision, Commitment, CustomerNote, OrderEvent,
                         RefundEvent, SeedMarker)
    initialize()
    with SessionLocal.begin() as db:
        if db.get(SeedMarker,'stage2_demo_examples'):
            return False
        users={u.email:u for u in db.scalars(select(User)).all()}
        if not {'alex@demo.com','priya@demo.com','maya@demo.com'} <= users.keys():
            return False
        agent=users['alex@demo.com']
        priya=db.scalar(select(Customer).where(Customer.user_id==users['priya@demo.com'].id))
        if priya:
            db.add(CustomerNote(customer_id=priya.id,author_id=agent.id,
                text='Demo note: previous product-quality and refund requests exist. Review each linked order and the supporting evidence independently.'))
        if db.get(Order,'ORD-88241'):
            db.add(OrderEvent(order_id='ORD-88241',event_type='DELIVERED',
                description='Simulated delivery completed; a product-quality complaint followed.'))
        if db.get(Order,'ORD-88102'):
            db.add(OrderEvent(order_id='ORD-88102',event_type='DELAY_REPORTED',
                description='Simulated delivery overdue; delivery investigation requested.'))
        if db.get(Ticket,'TKT-10398'):
            db.add(Commitment(ticket_id='TKT-10398',description='Provide the next simulated delivery investigation update',
                owner_id=agent.id,created_by=agent.id,due_at=utcnow()+timedelta(hours=2),
                customer_visible=True))
        # Older Stage 1 sample refunds were created before the corresponding approval IDs.
        for ap in db.scalars(select(ApprovalRequest).where(ApprovalRequest.status=='PENDING')).all():
            existing=db.scalar(select(Refund).where(Refund.approval_id==ap.id))
            if not existing:
                unlinked=db.scalar(select(Refund).where(Refund.ticket_id==ap.ticket_id,
                    Refund.approval_id.is_(None),Refund.status=='PENDING_APPROVAL'))
                if unlinked:
                    unlinked.approval_id=ap.id
        for refund in db.scalars(select(Refund)).all():
            # Starting point for the immutable Stage 2 event ledger.
            db.add(RefundEvent(refund_id=refund.id,status=refund.status,
                description='Stage 2 history snapshot of simulated refund status'))
        db.add(SeedMarker(code='stage2_demo_examples'))
        return True
