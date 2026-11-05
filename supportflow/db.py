"""SQLAlchemy database configuration. Use one short-lived session per operation."""
from __future__ import annotations
from sqlalchemy import create_engine, event, select
from sqlalchemy.orm import sessionmaker
from .config import DB_PATH
from .models import Base, Ticket, TicketCounter

DB_PATH.parent.mkdir(parents=True, exist_ok=True)
engine = create_engine(f'sqlite:///{DB_PATH.as_posix()}', connect_args={'check_same_thread': False, 'timeout': 20}, future=True)

@event.listens_for(engine, 'connect')
def set_sqlite_pragmas(connection, record):
    cursor = connection.cursor()
    cursor.execute('PRAGMA foreign_keys=ON')
    cursor.execute('PRAGMA busy_timeout=20000')
    cursor.execute('PRAGMA journal_mode=WAL')
    cursor.close()

SessionLocal = sessionmaker(bind=engine, expire_on_commit=False)

def initialize():
    """Add Stage 2 tables without dropping or modifying Stage 1 data."""
    Base.metadata.create_all(engine)
    with SessionLocal.begin() as session:
        if session.get(TicketCounter, 'tickets') is None:
            existing = session.scalars(select(Ticket.id)).all()
            last = max([10456] + [int(t.split('-')[-1]) for t in existing
                                  if t.startswith('TKT-') and t[4:].isdigit()])
            session.add(TicketCounter(key='tickets', last_value=last))
