import os
import random
import json
import requests
import time
import hashlib
import logging
from datetime import datetime, timedelta, timezone
from flask import Flask, jsonify, request
from pytrends.request import TrendReq
from supabase import create_client, Client
from dotenv import load_dotenv
from typing import List, Dict, Optional

load_dotenv()
app = Flask(__name__)

# -------------------------
# CONFIG / ENV
# -------------------------
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")
if not SUPABASE_URL or not SUPABASE_KEY:
    raise RuntimeError("Supabase URL/KEY not set in env")

supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

# Rate limiting / caching
CACHE = {}
GLOBAL_CACHE = {
    "last_request_time": 0,
    "request_count": 0,
    "last_cleanup": datetime.utcnow().timestamp(),
    "hour_start": datetime.utcnow().timestamp(),
    "start_time": datetime.utcnow().timestamp(),
    "last_db_cleanup": datetime.utcnow().timestamp()
}
CACHE_DURATION = 3600             # 1 hour memory cache
GLOBAL_CACHE_DURATION = 1800      # 30 min
MIN_REQUEST_INTERVAL = float(os.getenv("MIN_REQUEST_INTERVAL", "10"))  # seconds
MAX_REQUESTS_PER_HOUR = int(os.getenv("MAX_REQUESTS_PER_HOUR", "100"))
CACHE_CLEANUP_INTERVAL = 7200     # 2 hours
EXTENDED_FIELDS_ENABLED = os.getenv("ENABLE_EXTENDED_FIELDS", "true").lower() not in {"false", "0", "no"}
DASHBOARD_DAY_BUCKET_ENABLED = os.getenv("ENABLE_DAY_BUCKET", "true").lower() not in {"false", "0", "no"}
DATABASE_CLEANUP_INTERVAL = int(os.getenv("DATABASE_CLEANUP_INTERVAL", "43200"))  # 12 hours
DB_RETENTION_DAYS = int(os.getenv("DB_RETENTION_DAYS", "30"))
BASE_DB_FIELDS = ["keyword", "score", "topic", "source", "timestamp"]
if DASHBOARD_DAY_BUCKET_ENABLED:
    BASE_DB_FIELDS.append("day_bucket")
EXTENDED_DB_FIELDS = ["topic_cluster", "intent", "keyword_hash"]

# -------------------------
# SEED TOPICS (clustered)
# -------------------------
SEED_TOPICS = {
    "character_prompts": [
        "3D Character Creator", "Anime Character Prompt", "3d animation prompt ai",
        "surreal art prompt ai", "kawaii cute design prompt", "Hyper Realistic",
        "fantasy character prompt", "sci fi character design", "steampunk character prompt",
        "villain character concept", "hero character backstory", "mythical creature prompt",
        "hyper realistic character", "photorealistic character design", "ultra realistic portrait",
        "realistic human character", "lifelike character rendering", "detailed realistic faces"
    ],
    
    "branding_prompts": [
        "AI Logo / Mascot Prompt", "Product Mockup Generation", "Social Media Template Prompt",
        "Styling Influencer Photos", "Interior / Room Design AI Prompt"
    ],

    # "ai_media_tools": [
    #     "ai image prompt", "ai photo prompt", "text to image", "ai video prompt",
    #     "text to video ai", "image editing ai", "video editing ai", "enhance photo ai",
    #     "remove background ai", "neon cyberpunk prompt", "cinematic ai prompt"
    # ],

    "social_media_ads": [
        "video ai", " ads creative", " affiliate ", "ugc video ai",
        "video affiliate prompt", "viral video prompt ai"
    ],
    "poster_design": [
        "movie poster design", "music poster design", "concert poster template",
        "vintage movie poster", "retro concert poster", "film poster inspiration",
        "event poster design", "band poster aesthetic", "typography poster design",
        "graphic poster layout", "poster illustration style", "advertising poster template",
        "minimalist poster design", "bold poster typography", "creative poster ideas",
        "poster design trends", "visual poster concepts", "artistic poster layouts"
    ],

    # "3d_design_art": [
    #     "3D modeling software", "3D animation techniques", "3D rendering process",
    #     "3D printing technology", "Blender 3D tutorial", "Maya 3D design",
    #     "Cinema 4D basics", "volumetric design", "perspective drawing",
    #     "depth mapping 3D", "3D character modeling", "3D scene creation",
    #     "3D product design", "entertainment 3D art", "industrial 3D modeling",
    #     "architectural visualization", "3D game assets", "motion graphics 3D"
    # ],

    "concept_art": [
        "concept art techniques", "environment concept art", "character concept design",
        "creature concept art", "storytelling concept art", "visual development art",
        "film concept art", "game concept art", "mood board concept art",
        "color scripting", "ideation sketches", "production concept art",
        "concept art workflow", "digital painting concept", "worldbuilding art",
        "environment ideation", "character silhouette design", "concept art portfolio"
    ],

    "portrait_photography": [
        "portrait photography lighting", "studio portrait setup", "natural light portraits",
        "portrait posing tips", "headshot photography", "family portrait ideas",
        "creative portrait concepts", "moody portrait lighting", "portrait retouching techniques",
        "portrait photography gear", "outdoor portrait locations", "portrait composition rules",
        "dramatic portrait lighting", "portrait photography workshops", "portrait editing workflow",
        "softbox portrait lighting", "portrait depth of field", "portrait storytelling"
    ],

    # "urban_design": [
    #     "urban design principles", "public space planning", "transit oriented development",
    #     "mixed use development", "walkable city design", "green infrastructure urban",
    #     "sustainable urban planning", "urban landscape architecture", "city zoning strategies",
    #     "urban mobility solutions", "smart city design", "urban regeneration projects",
    #     "downtown revitalization", "pedestrian friendly streets", "urban public art",
    #     "community engagement urban design", "urban master planning", "climate resilient cities"
    # ],
}

ALL_TOPICS = [t for topics in SEED_TOPICS.values() for t in topics]

# -------------------------
# Helpers
# -------------------------
def cleanup_cache():
    current_time = datetime.utcnow().timestamp()
    expired = [k for k, v in CACHE.items() if current_time - v["time"] > CACHE_DURATION]
    for k in expired:
        del CACHE[k]
    GLOBAL_CACHE["last_cleanup"] = current_time
    logging.info(f"Cache cleanup: removed {len(expired)} entries")


def cleanup_database(retention_days: int = DB_RETENTION_DAYS) -> int:
    if retention_days <= 0:
        return 0
    cutoff_dt = datetime.now(timezone.utc) - timedelta(days=retention_days)
    cutoff_iso = cutoff_dt.isoformat()
    deleted = 0
    try:
        response = supabase.table("trend_keywords").delete().lt("timestamp", cutoff_iso).execute()
        deleted = len(response.data or [])
        logging.info(
            "Database cleanup removed %s rows older than %s days",
            deleted,
            retention_days
        )
    except Exception as e:
        logging.warning(f"Database cleanup failed: {e}")
    finally:
        GLOBAL_CACHE["last_db_cleanup"] = datetime.utcnow().timestamp()
    return deleted


def is_rate_limited() -> (bool, Optional[str]):
    current_time = datetime.utcnow().timestamp()
    # Reset hourly counter when hour passed
    if current_time - GLOBAL_CACHE.get("hour_start", 0) > 3600:
        GLOBAL_CACHE["request_count"] = 0
        GLOBAL_CACHE["hour_start"] = current_time

    time_since_last = current_time - GLOBAL_CACHE["last_request_time"]
    if time_since_last < MIN_REQUEST_INTERVAL:
        return True, f"Too frequent requests. Wait {MIN_REQUEST_INTERVAL - time_since_last:.1f}s"
    if GLOBAL_CACHE["request_count"] >= MAX_REQUESTS_PER_HOUR:
        return True, "Hourly rate limit exceeded"
    return False, None


def pick_topic(cluster: Optional[str] = None) -> (str, str):
    """
    Pick a topic randomly. If cluster specified, choose from that cluster.
    Returns (topic, cluster_name)
    """
    if cluster and cluster in SEED_TOPICS:
        topic = random.choice(SEED_TOPICS[cluster])
        return topic, cluster
    cluster = random.choice(list(SEED_TOPICS.keys()))
    topic = random.choice(SEED_TOPICS[cluster])
    return topic, cluster


def get_from_database_cache(topic: str) -> Optional[Dict]:
    try:
        cutoff_time = (datetime.utcnow() - timedelta(hours=2)).isoformat()
        resp = supabase.table("trend_keywords").select("*")\
            .eq("topic", topic).gte("timestamp", cutoff_time).order("timestamp", desc=True).limit(10).execute()
        if resp.data:
            return {"source": "database_cache", "topic": topic, "trend_keywords": resp.data, "cached_from_db": True}
    except Exception as e:
        logging.warning(f"Database cache error: {e}")
    return None


def simple_intent_classifier(keyword: str) -> str:
    """
    Rule-based classifier:
    - Commercial if keyword contains buying/selling/ad-related terms
    - Creative if contains prompt/art/template/aesthetic
    - Otherwise informational
    """
    k = keyword.lower()
    commercial_tokens = ["beli", "jual", "jualan", "iklan", "promo", "order", "harga", "toko", "shop", "video produk", "tiktok shop", "affiliate"]
    creative_tokens = ["prompt", "aesthetic", "poster", "midjourney", "art", "desain", "template", "keren", "vintage", "surreal", "cyberpunk", "anime"]
    for t in commercial_tokens:
        if t in k:
            return "commercial"
    for t in creative_tokens:
        if t in k:
            return "creative"
    return "informational"


def keyword_hash(topic: str, keyword: str) -> str:
    """
    Lightweight dedupe helper: hash topic+keyword
    """
    h = hashlib.sha1(f"{topic}|{keyword}".encode("utf-8")).hexdigest()
    return h


def prepare_db_records(records: List[Dict]) -> List[Dict]:
    """Return payload compatible with Supabase schema"""
    prepared = []
    for item in records:
        base = {field: item[field] for field in BASE_DB_FIELDS if field in item}
        if EXTENDED_FIELDS_ENABLED:
            for field in EXTENDED_DB_FIELDS:
                if field in item:
                    base[field] = item[field]
        prepared.append(base)
    return prepared


# -------------------------
# Fetching functions
# -------------------------
def fetch_from_pytrends(topic: str, geo: str = "ID") -> List[Dict]:
    logging.info(f"Fetching from PyTrends: {topic} (geo={geo})")
    GLOBAL_CACHE["last_request_time"] = datetime.utcnow().timestamp()
    GLOBAL_CACHE["request_count"] += 1
    pytrends = TrendReq(hl="id-ID", tz=420)  # Indonesia timezone offset for display
    try:
        pytrends.build_payload([topic], timeframe="now 7-d", geo=geo)
        related = pytrends.related_queries().get(topic, {}).get("top")
        results = []
        if related is None or related.empty:
            return results
        for _, row in related.iterrows():
            try:
                val = int(row["value"])
            except Exception:
                continue
            if val > 20:
                results.append({"keyword": row["query"], "score": val})
        return results
    except Exception as e:
        logging.warning(f"PyTrends error for {topic}: {e}")
        return []


def fetch_from_google_trends_json(topic: str, geo: str = "ID") -> List[Dict]:
    logging.info(f"Fetching from Google Trends JSON: {topic} (geo={geo})")
    GLOBAL_CACHE["last_request_time"] = datetime.utcnow().timestamp()
    GLOBAL_CACHE["request_count"] += 1
    # Official widget endpoint requires token and complex req; this is a best-effort fallback
    url = f"https://trends.google.com/trends/api/widgetdata/relatedsearches?hl=id&tz=420&req=%7B%22restriction%22:%7B%22complexKeywordsRestriction%22:%7B%22keyword%22:%5B%7B%22type%22:%22BROAD%22,%22value%22:%22{topic}%22%7D%5D%7D%7D,%22keywordType%22:%22QUERY%22,%22metric%22:%5B%22TOP%22%5D,%22trendinessSettings%22:%7B%22compareTime%22:%22now%207-d%22%7D,%22requestOptions%22:%7B%22property%22:%22{geo}%22,%22backend%22:%22IZG%22,%22category%22:0%7D,%22language%22:%22id%22%7D&token="
    try:
        resp = requests.get(url, timeout=10, headers={"User-Agent": "Mozilla/5.0"})
        if resp.status_code != 200:
            return []
        data_str = resp.text.replace(")]}',", "")
        data = json.loads(data_str)
        keywords = []
        for item in data.get("default", {}).get("rankedList", [])[0].get("rankedKeyword", []):
            val = item.get("value", 0)
            if val > 20:
                keywords.append({"keyword": item["query"], "score": val})
        return keywords
    except Exception as e:
        logging.warning(f"Google Trends JSON fetch failed: {e}")
        return []


# -------------------------
# Endpoint
# -------------------------
@app.route("/", methods=["GET"])
def get_trends():
    # Cleanup
    current_time = datetime.utcnow().timestamp()
    if current_time - GLOBAL_CACHE["last_cleanup"] > CACHE_CLEANUP_INTERVAL:
        cleanup_cache()
    if DATABASE_CLEANUP_INTERVAL > 0 and current_time - GLOBAL_CACHE.get("last_db_cleanup", 0) > DATABASE_CLEANUP_INTERVAL:
        cleanup_database()

    # Rate limiting
    is_limited, limit_msg = is_rate_limited()
    if is_limited:
        return jsonify({"error": "Rate limited", "message": limit_msg, "retry_after": MIN_REQUEST_INTERVAL}), 429

    # Optional: allow query param cluster (product|art|character)
    req_cluster = request.args.get("cluster")
    topic, cluster = pick_topic(req_cluster)

    logging.info(f"Selected topic: {topic} (cluster={cluster})")

    # Memory cache
    if topic in CACHE and (current_time - CACHE[topic]["time"]) < CACHE_DURATION:
        logging.info(f"Serving from memory cache: {topic}")
        cached_data = CACHE[topic]["data"]
        cached_data["cache_hit"] = "memory"
        return jsonify(cached_data)

    # DB cache
    db_cached = get_from_database_cache(topic)
    if db_cached:
        logging.info(f"Serving from database cache: {topic}")
        CACHE[topic] = {"time": current_time, "data": db_cached}
        return jsonify(db_cached)

    # Fetch fresh
    logging.info(f"Fetching fresh data for: {topic}")
    trends = []
    source = "none"
    try:
        trends = fetch_from_pytrends(topic, geo="ID")
        source = "pytrends"
    except Exception as e:
        logging.warning(f"PyTrends fetch exception: {e}")
        time.sleep(1)
        try:
            trends = fetch_from_google_trends_json(topic, geo="ID")
            source = "google_trends_json"
        except Exception as e2:
            logging.warning(f"Google JSON fallback failed: {e2}")

    # Fallback
    if not trends:
        logging.info(f"No real trends for {topic}, using fallback")
        trends = [
            {"keyword": f"{topic} inspiration", "score": 30},
            {"keyword": f"{topic} ideas", "score": 25},
            {"keyword": f"{topic} aesthetic", "score": 22}
        ]
        source = "fallback"

    # Format and enrich
    final_data = []
    now_utc = datetime.now(timezone.utc)
    timestamp_iso = now_utc.isoformat()
    day_bucket_iso = now_utc.date().isoformat()

    for t in trends:
        kw = t["keyword"]
        score = int(t.get("score", 0))
        intent = simple_intent_classifier(kw)
        k_hash = keyword_hash(topic, kw)
        record = {
            "keyword": kw,
            "score": score,
            "topic": topic,
            "topic_cluster": cluster,
            "intent": intent,
            "source": source,
            "keyword_hash": k_hash,
            "timestamp": timestamp_iso
        }
        if DASHBOARD_DAY_BUCKET_ENABLED:
            record["day_bucket"] = day_bucket_iso
        final_data.append(record)

    # Insert to Supabase (always try to insert, even fallback for testing)
    logging.info(
        "Preparing to insert %s records to Supabase (topic=%s, cluster=%s, source=%s)",
        len(final_data),
        topic,
        cluster,
        source
    )
    
    db_records = prepare_db_records(final_data)
    logging.info(f"DB records prepared: {len(db_records)} records")
    logging.info(f"Sample record: {db_records[0] if db_records else 'None'}")
    
    try:
        # Simplified insert approach - just use regular insert first
        response = supabase.table("trend_keywords").insert(db_records).execute()
        
        inserted = len(response.data or [])
        logging.info(f"Successfully inserted {inserted} keywords")
        
        if hasattr(response, 'error') and response.error:
            logging.error(f"Supabase response error: {response.error}")
            
    except Exception as e:
        logging.error(f"Supabase insert failed with exception: {e}")
        logging.error(f"Exception type: {type(e)}")
        
        # Try alternative approach with upsert
        try:
            logging.info("Attempting upsert fallback...")
            if DASHBOARD_DAY_BUCKET_ENABLED:
                conflict_cols = "topic,keyword,day_bucket"
            else:
                conflict_cols = "topic,keyword"
                
            response = supabase.table("trend_keywords").upsert(
                db_records,
                on_conflict=conflict_cols
            ).execute()
            
            inserted = len(response.data or [])
            logging.info(f"Upsert fallback succeeded: {inserted} keywords")
            
        except Exception as e2:
            logging.error(f"Upsert fallback also failed: {e2}")
            logging.error(f"Giving up on database insert")

    # Prepare response
    result = {"source": source, "trend_keywords": final_data, "topic": topic, "cache_hit": "fresh", "timestamp": timestamp_iso}
    CACHE[topic] = {"time": current_time, "data": result}

    return jsonify(result)


@app.route("/debug/supabase", methods=["GET"])
def debug_supabase():
    """Debug endpoint to test Supabase connection and permissions"""
    try:
        # Test basic connection
        response = supabase.table("trend_keywords").select("count").execute()
        
        # Test insert with simple record
        test_record = {
            "keyword": "test keyword",
            "topic": "test topic", 
            "score": 50,
            "source": "debug",
            "timestamp": datetime.now(timezone.utc).isoformat()
        }
        
        if DASHBOARD_DAY_BUCKET_ENABLED:
            test_record["day_bucket"] = datetime.now(timezone.utc).date().isoformat()
            
        if EXTENDED_FIELDS_ENABLED:
            test_record["topic_cluster"] = "debug"
            test_record["intent"] = "test"
            test_record["keyword_hash"] = "testhash123"
        
        db_record = prepare_db_records([test_record])
        
        insert_response = supabase.table("trend_keywords").insert(db_record).execute()
        
        return jsonify({
            "status": "success",
            "connection": "OK",
            "select_response": len(response.data or []),
            "insert_test": len(insert_response.data or []),
            "test_record": db_record[0] if db_record else None,
            "supabase_url": SUPABASE_URL,
            "extended_fields": EXTENDED_FIELDS_ENABLED,
            "day_bucket": DASHBOARD_DAY_BUCKET_ENABLED
        })
        
    except Exception as e:
        return jsonify({
            "status": "error",
            "error": str(e),
            "error_type": type(e).__name__,
            "supabase_url": SUPABASE_URL,
            "extended_fields": EXTENDED_FIELDS_ENABLED,
            "day_bucket": DASHBOARD_DAY_BUCKET_ENABLED
        }), 500


@app.route("/cache-status", methods=["GET"])
def cache_status():
    current_time = datetime.utcnow().timestamp()
    total_cached = len(CACHE)
    fresh_cache = sum(1 for c in CACHE.values() if current_time - c["time"] < CACHE_DURATION)
    return jsonify({
        "cache_stats": {
            "total_entries": total_cached,
            "fresh_entries": fresh_cache,
            "expired_entries": total_cached - fresh_cache,
            "cache_duration_hours": CACHE_DURATION / 3600
        },
        "rate_limiting": {
            "requests_this_hour": GLOBAL_CACHE.get("request_count", 0),
            "max_requests_per_hour": MAX_REQUESTS_PER_HOUR,
            "min_request_interval_seconds": MIN_REQUEST_INTERVAL,
            "last_request_time": datetime.fromtimestamp(GLOBAL_CACHE["last_request_time"]).isoformat() if GLOBAL_CACHE["last_request_time"] > 0 else None
        },
        "system_info": {
            "uptime_hours": (current_time - GLOBAL_CACHE.get("start_time", current_time)) / 3600,
            "last_cleanup": datetime.fromtimestamp(GLOBAL_CACHE["last_cleanup"]).isoformat(),
            "cached_topics": list(CACHE.keys())
        }
    })


@app.route("/debug/test-insert", methods=["POST"])
def test_insert():
    """Test endpoint to manually insert a record"""
    try:
        test_data = {
            "keyword": f"manual test {datetime.now(timezone.utc).strftime('%H:%M:%S')}",
            "topic": "manual test topic",
            "score": 75,
            "source": "manual",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "day_bucket": datetime.now(timezone.utc).date().isoformat(),
            "topic_cluster": "test",
            "intent": "test",
            "keyword_hash": f"manual{datetime.now(timezone.utc).timestamp()}"
        }
        
        # Prepare according to schema
        db_record = prepare_db_records([test_data])
        
        # Try direct insert
        response = supabase.table("trend_keywords").insert(db_record).execute()
        
        return jsonify({
            "status": "success",
            "inserted": len(response.data or []),
            "record_sent": db_record[0] if db_record else None,
            "response_data": response.data[0] if response.data else None
        })
        
    except Exception as e:
        return jsonify({
            "status": "error", 
            "error": str(e),
            "error_type": type(e).__name__
        }), 500


@app.route("/maintenance/db-cleanup", methods=["POST"])
def manual_db_cleanup():
    try:
        retention_param = request.args.get("days")
        retention_days = int(retention_param) if retention_param is not None else DB_RETENTION_DAYS
    except ValueError:
        return jsonify({"error": "Invalid days parameter"}), 400

    deleted = cleanup_database(retention_days)
    return jsonify({
        "message": "Database cleanup executed",
        "retention_days": retention_days,
        "deleted_rows": deleted,
        "last_cleanup": datetime.utcnow().isoformat()
    })


if __name__ == "__main__":
    GLOBAL_CACHE["start_time"] = datetime.utcnow().timestamp()
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", 5000)), debug=False)
