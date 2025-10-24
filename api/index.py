import os, random, json, requests, time
from datetime import datetime, timedelta
from flask import Flask, jsonify
from pytrends.request import TrendReq
from supabase import create_client, Client
from dotenv import load_dotenv

load_dotenv()
app = Flask(__name__)

# Supabase Config
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

# Topic Seed — Fokus visual & AI art
SEED_TOPICS = [
    "AI art", "digital art", "concept art", "illustration",
    "graphic design", "poster design", "motion graphics",
    "visual design", "midjourney", "stability ai",
    "text to image", "text to video","multiple images to image", "multiple images to video", "canva ai", "adobe firefly",
    "dall-e", "veo", "gemini", "chatGpt", "ai image generator",
    "stable diffusion", "ai video generator", "prompt design",
    "promotional video", "social media graphics", "branding design",
    "3d modeling", "character design", "environment design",

]

# Enhanced Caching System
CACHE = {}
GLOBAL_CACHE = {
    "last_request_time": 0,
    "request_count": 0,
    "last_cleanup": datetime.utcnow().timestamp()
}

# Cache Configuration
CACHE_DURATION = 3600  # 1 hour for topic cache
GLOBAL_CACHE_DURATION = 1800  # 30 minutes for global cache
MIN_REQUEST_INTERVAL = 10  # 10 seconds between API calls
MAX_REQUESTS_PER_HOUR = 100  # Rate limit
CACHE_CLEANUP_INTERVAL = 7200  # Clean cache every 2 hours

def cleanup_cache():
    """Clean up expired cache entries to prevent memory leak"""
    current_time = datetime.utcnow().timestamp()
    expired_keys = []
    
    for topic, cache_data in CACHE.items():
        if current_time - cache_data["time"] > CACHE_DURATION:
            expired_keys.append(topic)
    
    for key in expired_keys:
        del CACHE[key]
    
    GLOBAL_CACHE["last_cleanup"] = current_time
    print(f"Cache cleanup: removed {len(expired_keys)} expired entries")

def is_rate_limited():
    """Check if we're hitting rate limits"""
    current_time = datetime.utcnow().timestamp()
    
    # Reset hourly counter
    if current_time - GLOBAL_CACHE.get("hour_start", 0) > 3600:
        GLOBAL_CACHE["request_count"] = 0
        GLOBAL_CACHE["hour_start"] = current_time
    
    # Check rate limits
    time_since_last = current_time - GLOBAL_CACHE["last_request_time"]
    if time_since_last < MIN_REQUEST_INTERVAL:
        return True, f"Too frequent requests. Wait {MIN_REQUEST_INTERVAL - time_since_last:.1f}s"
    
    if GLOBAL_CACHE["request_count"] >= MAX_REQUESTS_PER_HOUR:
        return True, "Hourly rate limit exceeded"
    
    return False, None

def get_from_database_cache(topic):
    """Try to get recent data from Supabase to avoid API calls"""
    try:
        # Get data from last 2 hours for this topic
        cutoff_time = (datetime.utcnow() - timedelta(hours=2)).isoformat()
        
        response = supabase.table("trend_keywords").select("*").eq("topic", topic).gte("timestamp", cutoff_time).order("timestamp", desc=True).limit(10).execute()
        
        if response.data:
            # Format as API response
            return {
                "source": "database_cache",
                "topic": topic,
                "trend_keywords": response.data,
                "cached_from_db": True
            }
    except Exception as e:
        print(f"Database cache error: {e}")
    
    return None

def fetch_from_pytrends(topic):
    """Try using PyTrends with rate limiting"""
    print(f"Fetching from PyTrends: {topic}")
    GLOBAL_CACHE["last_request_time"] = datetime.utcnow().timestamp()
    GLOBAL_CACHE["request_count"] += 1
    
    pytrends = TrendReq(hl="en-US", tz=360)
    pytrends.build_payload([topic], timeframe="now 7-d")
    related = pytrends.related_queries().get(topic, {}).get("top")
    if related is None or related.empty:
        return []
    return [
        {"keyword": row["query"], "score": int(row["value"])}
        for _, row in related.iterrows() if row["value"] > 20
    ]

def fetch_from_google_trends_json(topic):
    """Fallback using unofficial endpoint with rate limiting"""
    print(f"Fetching from Google Trends JSON: {topic}")
    GLOBAL_CACHE["last_request_time"] = datetime.utcnow().timestamp()
    GLOBAL_CACHE["request_count"] += 1
    
    url = f"https://trends.google.com/trends/api/widgetdata/relatedsearches?hl=en-US&tz=360&req=%7B%22restriction%22:%7B%22complexKeywordsRestriction%22:%7B%22keyword%22:%5B%7B%22type%22:%22BROAD%22,%22value%22:%22{topic}%22%7D%5D%7D%7D,%22keywordType%22:%22QUERY%22,%22metric%22:%5B%22TOP%22%5D,%22trendinessSettings%22:%7B%22compareTime%22:%22now%207-d%22%7D,%22requestOptions%22:%7B%22property%22:%22%22,%22backend%22:%22IZG%22,%22category%22:0%7D,%22language%22:%22en-US%22%7D&token="
    resp = requests.get(url, timeout=10, headers={"User-Agent": "Mozilla/5.0"})
    if resp.status_code != 200:
        return []
    try:
        data_str = resp.text.replace(")]}',", "")
        data = json.loads(data_str)
        keywords = []
        for item in data.get("default", {}).get("rankedList", [])[0].get("rankedKeyword", []):
            val = item.get("value", 0)
            if val > 20:
                keywords.append({"keyword": item["query"], "score": val})
        return keywords
    except Exception:
        return []

@app.route("/", methods=["GET"])
def get_trends():
    # Cleanup cache periodically
    current_time = datetime.utcnow().timestamp()
    if current_time - GLOBAL_CACHE["last_cleanup"] > CACHE_CLEANUP_INTERVAL:
        cleanup_cache()
    
    # Check rate limiting first
    is_limited, limit_msg = is_rate_limited()
    if is_limited:
        return jsonify({
            "error": "Rate limited",
            "message": limit_msg,
            "retry_after": MIN_REQUEST_INTERVAL
        }), 429
    
    topic = random.choice(SEED_TOPICS)
    print(f"Selected topic: {topic}")

    # Level 1: Check in-memory cache (1 hour)
    if topic in CACHE and (current_time - CACHE[topic]["time"]) < CACHE_DURATION:
        print(f"Serving from memory cache: {topic}")
        cached_data = CACHE[topic]["data"]
        cached_data["cache_hit"] = "memory"
        return jsonify(cached_data)

    # Level 2: Check database cache (2 hours)
    db_cached = get_from_database_cache(topic)
    if db_cached:
        print(f"Serving from database cache: {topic}")
        # Also store in memory cache for faster future access
        CACHE[topic] = {"time": current_time, "data": db_cached}
        return jsonify(db_cached)

    # Level 3: Fetch fresh data from APIs
    print(f"Fetching fresh data for: {topic}")
    trends = []
    
    try:
        trends = fetch_from_pytrends(topic)
        source = "pytrends"
    except Exception as e:
        print("PyTrends failed:", e)
        # Add delay before fallback to avoid hitting rate limits
        time.sleep(2)
        
        try:
            trends = fetch_from_google_trends_json(topic)
            source = "google_trends_json"
        except Exception as e2:
            print("Google Trends JSON failed:", e2)

    # Final fallback with dummy data
    if not trends:
        print(f"Using fallback data for: {topic}")
        trends = [
            {"keyword": f"{topic} inspiration", "score": 30},
            {"keyword": f"{topic} ideas", "score": 25},
            {"keyword": f"{topic} aesthetic", "score": 22}
        ]
        source = "fallback"

    # Format data
    final_data = [
        {
            "keyword": t["keyword"],
            "score": t["score"],
            "topic": topic,
            "source": source,
            "timestamp": datetime.utcnow().isoformat()
        }
        for t in trends
    ]

    # Store in database (only if we got real data, not fallback)
    if source != "fallback":
        try:
            supabase.table("trend_keywords").insert(final_data).execute()
            print(f"Stored {len(final_data)} keywords in database")
        except Exception as e:
            print(f"Database insert failed: {e}")

    # Prepare response
    result = {
        "source": source,
        "trend_keywords": final_data,
        "topic": topic,
        "cache_hit": "fresh",
        "timestamp": datetime.utcnow().isoformat()
    }
    
    # Store in memory cache
    CACHE[topic] = {"time": current_time, "data": result}

    return jsonify(result)

@app.route("/cache-status", methods=["GET"])
def cache_status():
    """Endpoint to monitor cache status and rate limiting"""
    current_time = datetime.utcnow().timestamp()
    
    # Calculate cache statistics
    total_cached = len(CACHE)
    fresh_cache = sum(1 for cache_data in CACHE.values() 
                     if current_time - cache_data["time"] < CACHE_DURATION)
    
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
            "last_request_time": datetime.fromtimestamp(
                GLOBAL_CACHE["last_request_time"]
            ).isoformat() if GLOBAL_CACHE["last_request_time"] > 0 else None
        },
        "system_info": {
            "uptime_hours": (current_time - GLOBAL_CACHE.get("start_time", current_time)) / 3600,
            "last_cleanup": datetime.fromtimestamp(
                GLOBAL_CACHE["last_cleanup"]
            ).isoformat(),
            "cached_topics": list(CACHE.keys())
        }
    })

if __name__ == "__main__":
    # Initialize global cache start time
    GLOBAL_CACHE["start_time"] = datetime.utcnow().timestamp()
    app.run(debug=True)
