import os
from datetime import datetime, timezone
from typing import List, Optional, Any, Dict

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from database import db, create_document, get_documents

app = FastAPI(title="Saturnalia Backend", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# -----------------------------
# Pydantic request/response models
# -----------------------------
class EventIn(BaseModel):
    title: str
    description: Optional[str] = None
    start_time: datetime
    end_time: datetime
    stage_id: str
    capacity: Optional[int] = None
    tags: List[str] = []

class EventOut(EventIn):
    id: str = Field(..., description="Document id")

class StageIn(BaseModel):
    name: str
    lat: float
    lng: float
    geoRadius: int = 50

class StageOut(StageIn):
    id: str

class AlertIn(BaseModel):
    title: str
    message: str
    severity: str = Field("info", description="info|warning|critical")
    event_id: Optional[str] = None
    starts_at: Optional[datetime] = None
    ends_at: Optional[datetime] = None

class AlertOut(AlertIn):
    id: str

class LeaderboardSubmit(BaseModel):
    user_id: str
    score: int

class HuntScan(BaseModel):
    user_id: str
    code: str

class VoucherClaim(BaseModel):
    voucher_id: str
    user_id: str

class PostIn(BaseModel):
    author_id: str
    image_url: Optional[str] = None
    caption: str

# -----------------------------
# Helper
# -----------------------------

def _serialize(doc: Dict[str, Any]) -> Dict[str, Any]:
    d = {**doc}
    if "_id" in d:
        d["id"] = str(d.pop("_id"))
    # convert datetimes to isoformat
    for k, v in list(d.items()):
        if isinstance(v, datetime):
            d[k] = v.isoformat()
    return d

# -----------------------------
# Health & root
# -----------------------------
@app.get("/")
def root():
    return {"app": "Saturnalia Backend", "status": "ok"}

@app.get("/test")
def test_database():
    response = {
        "backend": "✅ Running",
        "database": "❌ Not Available",
        "database_url": "❌ Not Set",
        "database_name": "❌ Not Set",
        "connection_status": "Not Connected",
        "collections": []
    }
    try:
        if db is not None:
            response["database"] = "✅ Available"
            response["database_url"] = "✅ Set" if os.getenv("DATABASE_URL") else "❌ Not Set"
            response["database_name"] = getattr(db, "name", "✅ Connected")
            response["connection_status"] = "Connected"
            try:
                response["collections"] = db.list_collection_names()
                response["database"] = "✅ Connected & Working"
            except Exception as e:
                response["database"] = f"⚠️ Connected but Error: {str(e)[:80]}"
    except Exception as e:
        response["database"] = f"❌ Error: {str(e)[:120]}"
    return response

# -----------------------------
# Events
# -----------------------------
@app.get("/api/events", response_model=List[EventOut])
def list_events(stage: Optional[str] = Query(default=None), tag: Optional[str] = Query(default=None)):
    filt: Dict[str, Any] = {}
    if stage:
        filt["stage_id"] = stage
    if tag:
        filt["tags"] = {"$in": [tag]}
    docs = get_documents("event", filt)
    return [EventOut(**_serialize(d)) for d in docs]

@app.get("/api/events/now", response_model=List[EventOut])
def events_now():
    now = datetime.now(timezone.utc)
    docs = db["event"].find({"start_time": {"$lte": now}, "end_time": {"$gte": now}}).sort("start_time", 1)
    return [EventOut(**_serialize(d)) for d in docs]

@app.post("/api/events", response_model=EventOut)
def create_event(payload: EventIn):
    data = payload.model_dump()
    data["updated_at"] = datetime.now(timezone.utc)
    inserted_id = db["event"].insert_one(data).inserted_id
    doc = db["event"].find_one({"_id": inserted_id})
    return EventOut(**_serialize(doc))

# -----------------------------
# Stages
# -----------------------------
@app.get("/api/stages", response_model=List[StageOut])
def list_stages():
    docs = get_documents("stage")
    return [StageOut(**_serialize(d)) for d in docs]

@app.post("/api/stages", response_model=StageOut)
def create_stage(payload: StageIn):
    inserted_id = db["stage"].insert_one(payload.model_dump()).inserted_id
    doc = db["stage"].find_one({"_id": inserted_id})
    return StageOut(**_serialize(doc))

# -----------------------------
# Alerts / Announcements
# -----------------------------
@app.get("/api/alerts", response_model=List[AlertOut])
def list_alerts():
    docs = db["alert"].find({}).sort("starts_at", -1)
    return [AlertOut(**_serialize(d)) for d in docs]

@app.post("/api/admin/announce", response_model=AlertOut)
def announce(alert: AlertIn):
    data = alert.model_dump()
    data["created_at"] = datetime.now(timezone.utc)
    inserted_id = db["alert"].insert_one(data).inserted_id
    doc = db["alert"].find_one({"_id": inserted_id})
    return AlertOut(**_serialize(doc))

# -----------------------------
# Leaderboard
# -----------------------------
@app.get("/api/leaderboard/{game_id}")
def get_leaderboard(game_id: str, limit: int = 100):
    docs = db["leaderboard"].find({"game_id": game_id}).sort("score", -1).limit(limit)
    return [_serialize(d) for d in docs]

@app.post("/api/leaderboard/{game_id}/submit")
def submit_score(game_id: str, body: LeaderboardSubmit):
    if body.score < 0:
        raise HTTPException(status_code=400, detail="Score must be >= 0")
    existing = db["leaderboard"].find_one({"game_id": game_id, "user_id": body.user_id})
    now = datetime.now(timezone.utc)
    if existing:
        # keep best score
        best = max(existing.get("score", 0), body.score)
        db["leaderboard"].update_one(
            {"_id": existing["_id"]},
            {"$set": {"score": best, "updated_at": now}}
        )
    else:
        db["leaderboard"].insert_one({
            "game_id": game_id,
            "user_id": body.user_id,
            "score": body.score,
            "updated_at": now
        })
    saved = db["leaderboard"].find_one({"game_id": game_id, "user_id": body.user_id})
    return _serialize(saved)

# -----------------------------
# AR Scavenger Hunt
# -----------------------------
@app.get("/api/hunt/clues")
def list_clues():
    docs = db["huntclue"].find({}, {"code": 0})  # don't leak codes to clients
    return [_serialize(d) for d in docs]

@app.post("/api/hunt/scan")
def scan_code(body: HuntScan):
    clue = db["huntclue"].find_one({"code": body.code})
    if not clue:
        raise HTTPException(status_code=404, detail="Invalid code")
    prog = db["huntprogress"].find_one({"user_id": body.user_id})
    now = datetime.now(timezone.utc)
    if not prog:
        prog = {
            "user_id": body.user_id,
            "found_codes": [],
            "total_points": 0,
            "updated_at": now
        }
        db["huntprogress"].insert_one(prog)
        prog = db["huntprogress"].find_one({"user_id": body.user_id})
    if body.code in prog.get("found_codes", []):
        return {"status": "already", **_serialize(prog)}
    points = clue.get("points", 10)
    new_total = int(prog.get("total_points", 0)) + int(points)
    db["huntprogress"].update_one(
        {"_id": prog["_id"]},
        {"$set": {"updated_at": now, "total_points": new_total}, "$addToSet": {"found_codes": body.code}}
    )
    updated = db["huntprogress"].find_one({"user_id": body.user_id})
    return {"status": "ok", **_serialize(updated)}

# -----------------------------
# Social Posts (basic)
# -----------------------------
@app.get("/api/posts")
def list_posts(limit: int = 50):
    docs = db["post"].find({}).sort("created_at", -1).limit(limit)
    return [_serialize(d) for d in docs]

@app.post("/api/posts")
def create_post(body: PostIn):
    now = datetime.now(timezone.utc)
    data = {**body.model_dump(), "likes": 0, "created_at": now, "moderated": True}
    inserted = db["post"].insert_one(data).inserted_id
    doc = db["post"].find_one({"_id": inserted})
    return _serialize(doc)

# -----------------------------
# Vouchers (simplified)
# -----------------------------
@app.post("/api/voucher/claim")
def claim_voucher(body: VoucherClaim):
    v = db["voucher"].find_one({"_id": body.voucher_id})
    if not v:
        # allow using code instead of _id for demo
        v = db["voucher"].find_one({"code": body.voucher_id})
    if not v:
        raise HTTPException(status_code=404, detail="Voucher not found")
    if v.get("redeemedBy"):
        raise HTTPException(status_code=400, detail="Already redeemed")
    db["voucher"].update_one({"_id": v["_id"]}, {"$set": {"redeemedBy": body.user_id, "redeemedAt": datetime.now(timezone.utc)}})
    updated = db["voucher"].find_one({"_id": v["_id"]})
    return _serialize(updated)

# -----------------------------
# Seed helper (optional, idempotent)
# -----------------------------
@app.post("/api/admin/seed")
def seed_minimum():
    # Only seed if empty
    if db["stage"].count_documents({}) == 0:
        db["stage"].insert_many([
            {"name": "Main Stage", "lat": 12.9716, "lng": 77.5946, "geoRadius": 60},
            {"name": "Tech Arena", "lat": 12.972, "lng": 77.595, "geoRadius": 40},
        ])
    if db["event"].count_documents({}) == 0:
        now = datetime.now(timezone.utc)
        db["event"].insert_many([
            {
                "title": "Opening Ceremony",
                "description": "Kick-off with parade",
                "start_time": now,
                "end_time": now.replace(hour=(now.hour + 1) % 24),
                "stage_id": "main",
                "capacity": 500,
                "tags": ["ceremony"],
                "updated_at": now
            },
        ])
    if db["huntclue"].count_documents({}) == 0:
        db["huntclue"].insert_many([
            {"code": "STAR-001", "title": "Orion", "hint": "Find the hunter", "points": 10},
            {"code": "STAR-002", "title": "Cassiopeia", "hint": "W-shaped queen", "points": 10},
        ])
    return {"status": "ok"}

if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)
