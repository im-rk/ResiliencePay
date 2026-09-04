import os
from sqlalchemy import create_engine, MetaData
from sqlalchemy.orm import declarative_base, sessionmaker
from dotenv import load_dotenv

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./resiliencepay.db")

def create_resilient_engine():
    try:
        if DATABASE_URL.startswith("postgres"):
            eng = create_engine(DATABASE_URL, connect_args={"connect_timeout": 2}, pool_pre_ping=True)
            with eng.connect() as conn:
                pass
            return eng
    except Exception:
        pass
    
    # Fallback to local SQLite
    sqlite_url = "sqlite:///./resiliencepay.db"
    return create_engine(sqlite_url, connect_args={"check_same_thread": False})

engine = create_resilient_engine()
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

metadata = MetaData()
Base = declarative_base(metadata=metadata)

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
