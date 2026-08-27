from packages.db_models.database import get_db

def get_db_session():
    """Dependency provider for SQLAlchemy database sessions."""
    db_gen = get_db()
    db = next(db_gen)
    try:
        yield db
    finally:
        db.close()
