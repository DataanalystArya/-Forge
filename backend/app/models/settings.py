from datetime import datetime, timezone
from sqlalchemy import Column, String, Boolean, DateTime, Text
from app.core.database import Base


def get_utc_now() -> datetime:
    return datetime.now(timezone.utc)


class PlatformSetting(Base):
    __tablename__ = "platform_settings"

    key = Column(String(120), primary_key=True, index=True)
    value = Column(Text, nullable=True)
    is_secret = Column(Boolean, default=False)
    updated_at = Column(DateTime, default=get_utc_now, onupdate=get_utc_now)
