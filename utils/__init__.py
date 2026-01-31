from sqlalchemy.orm import sessionmaker
from sqlalchemy import create_engine
from urllib.parse import quote_plus
from . import sql_config
from .sql_config import username, password, host, port, database

encoded_password = quote_plus(password)
db_url = f"mysql+pymysql://{username}:{encoded_password}@{host}:{port}/{database}"
engine = create_engine(db_url)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

def db_session():
    return SessionLocal()