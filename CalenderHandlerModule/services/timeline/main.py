# services/timeline/main.py
import os
from fastapi import FastAPI, Depends, HTTPException
from pydantic import BaseModel, Field
from typing import Optional, List
from datetime import datetime
from sqlalchemy import create_engine, Column, BigInteger, String, DateTime, JSON
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, Session

# ========================
# Database Configuration
# ========================
DATABASE_URL="postgresql://echoagent:echoagents@localhost:5432/echoagents"

engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

# ========================
# SQLAlchemy Model
# ========================
class Timeline(Base):
    __tablename__ = "timeline"

    id = Column(BigInteger, primary_key=True, index=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=datetime.utcnow)
    agent_name = Column(String, nullable=False)
    action_type = Column(String, nullable=False)
    payload = Column(JSON, nullable=False)
    status = Column(String, nullable=False)
    meta = Column(JSON)

# ========================
# Pydantic Models
# ========================
class TimelineCreate(BaseModel):
    agent_name: str
    action_type: str
    payload: dict
    status: str = Field(..., pattern="^(started|done|failed)$")
    meta: Optional[dict] = None

class TimelineRead(TimelineCreate):
    id: int
    created_at: datetime

    class Config:
        orm_mode = True

# ========================
# FastAPI App
# ========================
app = FastAPI(title="Timeline Service")

# Dependency for DB session
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

# Create tables if not exist
Base.metadata.create_all(bind=engine)

# ========================
# Routes
# ========================

@app.post("/timeline/events", response_model=TimelineRead)
def create_timeline(entry: TimelineCreate, db: Session = Depends(get_db)):
    db_entry = Timeline(**entry.dict())
    db.add(db_entry)
    db.commit()
    db.refresh(db_entry)
    return db_entry

@app.get("/timeline/events", response_model=List[TimelineRead])
def list_timeline(
    agent_name: Optional[str] = None,
    status: Optional[str] = None,
    limit: int = 50,
    db: Session = Depends(get_db)
):
    query = db.query(Timeline)
    if agent_name:
        query = query.filter(Timeline.agent_name == agent_name)
    if status:
        query = query.filter(Timeline.status == status)
    return query.order_by(Timeline.created_at.desc()).limit(limit).all()
