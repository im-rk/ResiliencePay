from packages.db_models.models import GateCheck

def record_gate_check(db_session, decision_id, result: "GateResult") -> GateCheck:
    """Every evaluation is recorded, pass or block — this table is the
    queryable evidence for 'bounded and gated.' See DATABASE_DESIGN.md
    section 3, point 3."""
    check = GateCheck(
        decision_id=decision_id,
        result="passed" if result.passed else "blocked",
        rule_triggered=result.rule_triggered,
    )
    db_session.add(check)
    db_session.commit()
    return check

def get_active_promise(db_session, episode_id):
    from packages.db_models.models import PromiseToPay
    return db_session.query(PromiseToPay).filter_by(
        episode_id=episode_id, 
        status="active"
    ).first()
