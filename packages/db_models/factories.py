import factory
from factory.alchemy import SQLAlchemyModelFactory
from packages.db_models.database import SessionLocal
from packages.db_models.models import (
    Merchant, Customer, OptOut, Episode, Event,
    Diagnosis, Decision, GateCheck, Action, Outcome,
    CauseCategory, Arm
)

class BaseFactory(SQLAlchemyModelFactory):
    class Meta:
        sqlalchemy_session = SessionLocal()
        sqlalchemy_session_persistence = 'commit'

class MerchantFactory(BaseFactory):
    class Meta:
        model = Merchant
    
    name = factory.Faker('company')
    razorpay_key_id = factory.Faker('pystr_format', string_format='rzp_test_??????')
    vertical = factory.Iterator(['saas_subscription', 'd2c', 'b2b_receivables'])

class CustomerFactory(BaseFactory):
    class Meta:
        model = Customer
    
    merchant_id = factory.SubFactory(MerchantFactory)
    external_ref = factory.Faker('uuid4')
    segment = factory.Iterator(['new', 'returning_low_value', 'returning_high_value', 'churn_risk'])
    locale = 'en-IN'

class OptOutFactory(BaseFactory):
    class Meta:
        model = OptOut
    
    customer_id = factory.SubFactory(CustomerFactory)
    scope = 'all_recovery_comms'
    reason = factory.Faker('sentence')

class EpisodeFactory(BaseFactory):
    class Meta:
        model = Episode
    
    merchant_id = factory.SelfAttribute('customer_id.merchant_id')
    customer_id = factory.SubFactory(CustomerFactory)
    episode_type = 'subscription_charge_failed'
    original_amount = factory.Faker('random_int', min=10000, max=500000) # 100 to 5000 INR
    currency = 'INR'
    status = 'open'

class EventFactory(BaseFactory):
    class Meta:
        model = Event
    
    episode_id = factory.SubFactory(EpisodeFactory)
    event_type = 'payment.failed'
    gateway_error_code = 'BAD_REQUEST_ERROR'
    retry_count_so_far = 0

class DiagnosisFactory(BaseFactory):
    class Meta:
        model = Diagnosis
    
    event_id = factory.SubFactory(EventFactory)
    cause_category = 'insufficient_funds'
    confidence = 0.95
    method = 'rule_based'

class DecisionFactory(BaseFactory):
    class Meta:
        model = Decision
    
    event_id = factory.SubFactory(EventFactory)
    chosen_arm = 'retry_short_delay'
    context_bucket = 'sub_fail_insufficient_funds_new'

class GateCheckFactory(BaseFactory):
    class Meta:
        model = GateCheck
    
    decision_id = factory.SubFactory(DecisionFactory)
    result = 'passed'

class ActionFactory(BaseFactory):
    class Meta:
        model = Action
    
    decision_id = factory.SubFactory(DecisionFactory)
    arm_name = 'retry_short_delay'
    simulated = False
    status = 'scheduled'

class OutcomeFactory(BaseFactory):
    class Meta:
        model = Outcome
    
    action_id = factory.SubFactory(ActionFactory)
    result = 'recovered'
    amount_recovered = factory.SelfAttribute('action_id.decision_id.event_id.episode_id.original_amount')
    reward = 1.0
