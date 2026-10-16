from datetime import datetime

from sqlalchemy import Column, DateTime, Integer, String, Text

from .database import Base

# 任务状态：in_progress=进行中，completed=已完成
TASK_STATUS_IN_PROGRESS = "in_progress"
TASK_STATUS_COMPLETED = "completed"


class Task(Base):
    __tablename__ = "tasks"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    name = Column(String(200), nullable=False)
    source_config = Column(Text, nullable=False)
    target_config = Column(Text, nullable=False)
    status = Column(String(32), nullable=False, default=TASK_STATUS_IN_PROGRESS)
    report = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)
    session_state = Column(Text, nullable=True)
