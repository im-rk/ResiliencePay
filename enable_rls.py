import os
import sys

sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))
from packages.db_models.database import engine
from sqlalchemy import text

def enable_rls():
    print("Connecting to database to enable Row Level Security (RLS)...")
    
    with engine.begin() as conn:
        # Get all tables in the public schema
        result = conn.execute(text("""
            SELECT tablename 
            FROM pg_tables 
            WHERE schemaname = 'public';
        """))
        
        tables = [row[0] for row in result]
        
        if not tables:
            print("No tables found in public schema!")
            return
            
        print(f"Found {len(tables)} tables. Enabling RLS...")
        
        for table in tables:
            print(f" -> Enabling RLS on {table}...")
            # Execute ALTER TABLE ... ENABLE ROW LEVEL SECURITY
            conn.execute(text(f'ALTER TABLE "{table}" ENABLE ROW LEVEL SECURITY;'))
            
        print("\nSUCCESS: Row Level Security has been enabled on all public tables.")
        print("This completely blocks the Supabase REST API from unauthenticated access,")
        print("while allowing the backend SQLAlchemy connection to continue working normally.")

if __name__ == "__main__":
    enable_rls()
