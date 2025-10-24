import os, random, json, requests
from datetime import datetime
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
    "dall-e", "ai image generator",
    "stable diffusion", "ai video generator", "prompt design",
    "promotional video", "social media graphics", "branding design",
    "3d modeling", "character design", "environment design",

]

CACHE = {}

def fetch_from_pytrends(topic):
    """Try using PyTrends"""
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
    """Fallback using unofficial endpoint"""
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
    topic = random.choice(SEED_TOPICS)
    print(f"Fetching topic: {topic}")

    # Cache 1 hour
    if topic in CACHE and (datetime.utcnow().timestamp() - CACHE[topic]["time"]) < 3600:
        return jsonify(CACHE[topic]["data"])

    try:
        trends = fetch_from_pytrends(topic)
    except Exception as e:
        print("PyTrends failed:", e)
        trends = []

    # fallback
    if not trends:
        trends = fetch_from_google_trends_json(topic)

    # kalau tetap kosong → dummy fallback
    if not trends:
        trends = [
            {"keyword": f"{topic} inspiration", "score": 30},
            {"keyword": f"{topic} ideas", "score": 25},
            {"keyword": f"{topic} aesthetic", "score": 22}
        ]

    # Format + insert ke Supabase
    final_data = [
        {
            "keyword": t["keyword"],
            "score": t["score"],
            "topic": topic,
            "source": "google_trends",
            "timestamp": datetime.utcnow().isoformat()
        }
        for t in trends
    ]

    supabase.table("trend_keywords").insert(final_data).execute()

    result = {"source": "google_trends", "trend_keywords": final_data, "topic": topic}
    CACHE[topic] = {"time": datetime.utcnow().timestamp(), "data": result}

    return jsonify(result)

if __name__ == "__main__":
    app.run(debug=True)
