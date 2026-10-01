"""Synchronous DB session for Celery workers.

Celery workers execute tasks in plain sync worker processes, so they use a
regular psycopg2 session instead of the FastAPI app's async engine. Both
point at the same database (see Settings.sync_database_url) and share the
same ORM models/Base.
"""

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.config import settings

sync_engine = create_engine(settings.sync_database_url, pool_pre_ping=True)
SyncSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=sync_engine)
