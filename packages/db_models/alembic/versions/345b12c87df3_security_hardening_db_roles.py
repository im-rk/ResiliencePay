"""security hardening db roles

Revision ID: 345b12c87df3
Revises: 
Create Date: 2026-08-27 11:23:00.000000

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = '345b12c87df3'
down_revision = None
branch_labels = None
depends_on = None

def upgrade() -> None:
    # We apply the least privilege principle to the application role
    # Since we might be running this on a DB that doesn't have a 'resiliencepay_app' role,
    # we wrap it in a DO block to prevent failing if the role doesn't exist (like in test.db).
    op.execute("""
    DO $$ 
    BEGIN
        IF EXISTS (SELECT FROM pg_roles WHERE rolname = 'resiliencepay_app') THEN
            REVOKE DROP, TRUNCATE, ALTER ON ALL TABLES IN SCHEMA public FROM resiliencepay_app;
            REVOKE DELETE ON episodes, events, outcomes, decisions, actions FROM resiliencepay_app;
        END IF;
    END
    $$;
    """)

def downgrade() -> None:
    # Optionally restore privileges if needed
    op.execute("""
    DO $$ 
    BEGIN
        IF EXISTS (SELECT FROM pg_roles WHERE rolname = 'resiliencepay_app') THEN
            GRANT DROP, TRUNCATE, ALTER ON ALL TABLES IN SCHEMA public TO resiliencepay_app;
            GRANT DELETE ON episodes, events, outcomes, decisions, actions TO resiliencepay_app;
        END IF;
    END
    $$;
    """)
