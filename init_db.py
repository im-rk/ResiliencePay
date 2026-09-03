import sys
import os

sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))
from packages.db_models.database import engine
from packages.db_models.database import Base
from packages.db_models.models import *

print("Creating all tables in the database...")
Base.metadata.create_all(engine)
print("Tables created successfully!")
