"""
Database Schemas for Saturnalia

Each Pydantic model represents a MongoDB collection. Collection name is the
lowercase class name.
"""
from pydantic import BaseModel, Field, EmailStr
from typing import Optional, List
from datetime import datetime

class User(BaseModel):
    name: str = Field(..., description="Full name")
    email: EmailStr = Field(..., description="Email address")
    avatar_url: Optional[str] = Field(None, description="Profile image URL")
    college: Optional[str] = Field(None, description="College/department")
    points: int = Field(0, ge=0, description="Gamification points total")
    streak_days: int = Field(0, ge=0, description="Consecutive daily check-ins")

class Event(BaseModel):
    title: str = Field(..., description="Event title")
    description: Optional[str] = Field(None, description="Event details")
    category: Optional[str] = Field(None, description="Music, Tech, Sports, etc.")
    venue: str = Field(..., description="Where it happens")
    start_time: datetime = Field(..., description="Start datetime (ISO)")
    end_time: datetime = Field(..., description="End datetime (ISO)")
    organizers: Optional[List[str]] = Field(default_factory=list)

class Alert(BaseModel):
    title: str
    message: str
    severity: str = Field("info", description="info|warning|critical")
    event_id: Optional[str] = Field(None, description="Related event id")
    starts_at: Optional[datetime] = None
    ends_at: Optional[datetime] = None

class Post(BaseModel):
    user_id: str
    content: str
    image_url: Optional[str] = None
    likes: int = Field(0, ge=0)

class Score(BaseModel):
    user_id: str
    points: int = Field(..., ge=0)
    context: str = Field("general", description="Which game/context the points belong to")

class HuntClue(BaseModel):
    code: str = Field(..., description="Unique code e.g., QR content")
    title: str
    hint: str
    location_hint: Optional[str] = None
    points: int = Field(10, ge=1)

class HuntProgress(BaseModel):
    user_id: str
    found_codes: List[str] = Field(default_factory=list)
    total_points: int = Field(0, ge=0)
