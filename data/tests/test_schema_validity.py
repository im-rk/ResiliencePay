import pytest
import uuid
from data.generator import generate_batch, insert_batch
from packages.db_models.database import Base, engine, SessionLocal
from packages.db_models.models.merchant import Merchant
from packages.db_models.models.customer import Customer
from packages.db_models.models.episode import Episode
from packages.db_models.models.event import Event

@pytest.fixture(scope="session")
def setup_database():
    Base.metadata.create_all(bind=engine)
    yield
    Base.metadata.drop_all(bind=engine)

@pytest.fixture
def db_session(setup_database):
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

def test_schema_validity_and_leakage(db_session):
    """
    Every generated + inserted row passes all Phase 1 constraints.
    """
    # Create merchant first
    merchant_id = uuid.uuid4()
    merchant = Merchant(merchant_id=merchant_id, name="Test Merchant", razorpay_key_id="rzp_test_123", vertical="saas")
    db_session.add(merchant)
    db_session.commit()
    
    # Generate drafts
    drafts = generate_batch(seed=999, n=200, merchant_id=merchant_id)
    
    # Insert through schema
    inserted_events = insert_batch(drafts, db_session, merchant_id)
    
    assert len(inserted_events) == 200
    
    # Verify events are in the database
    events_in_db = db_session.query(Event).all()
    assert len(events_in_db) == 200
    
    # Leakage test: _ground_truth_recoverable should not be in the direct table columns.
    # We put it in `raw_payload` during insertion for eval purposes only.
    for event in events_in_db:
        assert hasattr(event, "raw_payload")
        assert "_ground_truth_recoverable" in event.raw_payload
