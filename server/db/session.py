"""DB 연결. 다른 코드는 여기 engine / SessionLocal 을 가져다 쓴다."""

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.core.config import settings

engine = create_engine(settings.database_url)
SessionLocal = sessionmaker(engine)
