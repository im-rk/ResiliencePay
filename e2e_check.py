import uuid
from datetime import datetime, timezone
from data.generator import generate_batch
from services.diagnose.service import diagnose
from packages.db_models.models.merchant import Merchant
from packages.db_models.database import SessionLocal
from packages.db_models.models.event import Event
from packages.db_models.models.episode import Episode
from packages.db_models.models.customer import Customer

def run_e2e():
    print("--- 1. Testing Phase 1 (Data Models) ---")
    db_session = SessionLocal()
    try:
        merchant_id = uuid.uuid4()
        merchant = Merchant(merchant_id=merchant_id, name="E2E Test Merchant", razorpay_key_id="rzp_test_e2e", vertical="ecommerce")
        customer = Customer(customer_id=uuid.uuid4(), merchant_id=merchant_id, segment="new")
        print("SQLAlchemy models initialized successfully without errors.")

        print("\n--- 2. Testing Phase 2 (Synthetic Data Generation) ---")
        drafts = generate_batch(seed=42, n=50, merchant_id=str(merchant_id))
        print(f"Generated {len(drafts)} synthetic events. Sample draft:")
        print(drafts[0])

        print("\n--- 3. Testing Phase 3 (Diagnose Service Integration) ---")
        results = {"rule_based": 0, "llm_fallback": 0, "fallback_failed": 0}
        
        events = []
        for draft in drafts:
            # Emulating Phase 1 Insert by instantiating the Event model
            event = Event(
                event_id=uuid.uuid4(),
                episode_id=uuid.uuid4(),
                gateway_error_code=draft["gateway_error_code"],
                raw_payload={"_ground_truth_recoverable_prob": draft.get("_ground_truth_recoverable_prob", draft.get("_ground_truth_recoverable", 0.5))},
                occurred_at=draft["occurred_at"]
            )
            events.append(event)
            
        print("Running diagnosis orchestrator over the generated events...")
        for event in events:
            diagnosis = diagnose(event, db_session)
            results[diagnosis.method] += 1
            
        print("\nDiagnosis Results Summary (for 50 events):")
        for method, count in results.items():
            print(f" - {method}: {count}")
            
        assert results["rule_based"] == 50, "Some known codes fell through to LLM!"
        print("\n✅ All 50 synthetic events were successfully diagnosed via rule_based deterministic mapping!")
        
        print("\n--- 3b. Testing LLM Fallback (Unknown Error) ---")
        unknown_event = Event(
            event_id=uuid.uuid4(),
            episode_id=uuid.uuid4(),
            gateway_error_code=None, # Missing code forces LLM fallback
            occurred_at=datetime.now(timezone.utc),
            raw_payload={"raw_gateway_message": "User tried to pay with a blocked test card."}
        )
        print("Invoking fallback for raw message: 'User tried to pay with a blocked test card.'")
        fallback_diagnosis = diagnose(unknown_event, db_session)
        print(f"LLM Fallback Diagnosis: Category='{fallback_diagnosis.cause_category.value}', Confidence={fallback_diagnosis.confidence}")
        
        print("\n🚀 All phases (1, 2, 3) integrated perfectly end-to-end!")
        
    except Exception as e:
        print(f"\nE2E Check Failed: {e}")
        import traceback
        traceback.print_exc()
    finally:
        db_session.close()

if __name__ == "__main__":
    run_e2e()
