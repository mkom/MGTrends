# MGTrends - AI Prompt & Social Media Trends API

A Flask API that fetches trending keywords related to AI prompts, poster design, social media content creation, and digital marketing from Google Trends, with data storage in Supabase.

## About

MGTrends is a specialized trends tracking API designed for content creators, digital marketers, and AI prompt enthusiasts. It monitors trending keywords specifically related to AI prompt engineering, social media content creation, and digital advertising. Unlike general trend APIs, MGTrends focuses on:

- **AI Prompt Engineering**: Tracks trends for poster design prompts, character creation, and AI art generation
- **Social Media Content**: Monitors TikTok trends, Instagram content, and viral marketing strategies  
- **Digital Advertising**: Follows social commerce, affiliate marketing, and creative advertising trends
- **Content Creation Tools**: Captures trending editing tools, templates, and design workflows

The API automatically fetches trending data from Google Trends, stores it in Supabase for historical analysis, and provides clean JSON responses perfect for content creation apps, marketing tools, or trend analysis dashboards.

**Perfect for:**
- Content creators tracking viral trends
- Marketing agencies monitoring ad creative trends
- AI prompt marketplace developers
- Social media tool builders
- Digital marketing researchers

## Features

- 🎨 **AI Prompt Focused**: Tracks trends in AI prompt engineering, poster design, and content creation
- 📱 **Social Media Trends**: Monitors TikTok, Instagram, and viral content strategies
- 💰 **Digital Marketing**: Follows social commerce, affiliate marketing, and advertising trends
- 📊 **Google Trends Integration**: Uses PyTrends library with fallback to unofficial Google Trends API
- 💾 **Supabase Storage**: Automatically stores trending keywords with advanced schema
- ⚡ **Multi-Level Caching**: Advanced caching system to prevent overfetching
  - Memory cache (1 hour) for instant responses
  - Database cache (2 hours) for recent data
  - Rate limiting (10s intervals, 100 req/hour)
  - Automatic cache cleanup and monitoring
- 🧹 **Database Cleanup**: Automatic data retention management (30 days default)
- 🔧 **Debug Tools**: Built-in endpoints for testing and monitoring
- 🚀 **Vercel Ready**: Configured for easy deployment on Vercel
- 🛡️ **Rate Limiting**: Built-in protection against API abuse and overfetching

## Tech Stack

- **Backend**: Python, Flask
- **Data Source**: Google Trends (via PyTrends)
- **Database**: Supabase
- **Deployment**: Vercel
- **Environment**: python-dotenv for configuration

## Setup

### Prerequisites

- Python 3.7+
- Supabase account and project
- Environment variables configured

### Installation

1. Clone the repository:
```bash
git clone <repository-url>
cd mgtrends
```

2. Install dependencies:
```bash
pip install -r requirements.txt
```

3. Create a `.env` file with your Supabase credentials:
```env
SUPABASE_URL=your_supabase_project_url
SUPABASE_KEY=your_supabase_service_role_key
ENABLE_EXTENDED_FIELDS=true
ENABLE_DAY_BUCKET=true
DATABASE_CLEANUP_INTERVAL=43200
DB_RETENTION_DAYS=30
MIN_REQUEST_INTERVAL=10
MAX_REQUESTS_PER_HOUR=100
```

4. Run the application:
```bash
python api/index.py
```

The API will be available at `http://localhost:5000`

## API Endpoints

### GET /

Returns trending keywords for a randomly selected AI prompt or social media topic.

**Query Parameters:**
- `cluster` (optional): Specify topic cluster (`poster_design`, `branding_prompts`, `character_prompts`, `ai_media_tools`, `social_media_ads`)

**Response Example:**
```json
{
  "source": "pytrends",
  "topic": "AI Poster Design",
  "cache_hit": "fresh",
  "timestamp": "2025-10-27T10:30:00.000000+00:00",
  "trend_keywords": [
    {
      "keyword": "propaganda poster ai generator",
      "score": 85,
      "topic": "AI Poster Design",
      "topic_cluster": "poster_design",
      "intent": "creative",
      "source": "pytrends",
      "keyword_hash": "abc123...",
      "timestamp": "2025-10-27T10:30:00.000000+00:00",
      "day_bucket": "2025-10-27"
    }
  ]
}
```

**Cache Sources:**
- `fresh`: Newly fetched from Google Trends
- `memory`: Served from 1-hour memory cache
- `database_cache`: Retrieved from 2-hour database cache

### GET /cache-status

Returns current cache statistics and rate limiting status for monitoring.

### POST /maintenance/db-cleanup

Manual database cleanup endpoint to remove old records.

**Query Parameters:**
- `days` (optional): Retention period in days (default: 30)

**Response Example:**
```json
{
  "message": "Database cleanup executed",
  "retention_days": 30,
  "deleted_rows": 150,
  "last_cleanup": "2025-10-27T10:30:00.000000"
}
```

### GET /debug/supabase

Debug endpoint to test Supabase connection and permissions.

### POST /debug/test-insert

Test endpoint to manually insert a record for debugging database issues.

## Caching Strategy

MGTrends implements a sophisticated multi-level caching system to prevent overfetching and API abuse:

### 1. Memory Cache (1 hour)
- Fastest response time
- Stores API responses in memory
- Automatic cleanup of expired entries

### 2. Database Cache (2 hours) 
- Queries recent data from Supabase
- Fallback when memory cache misses
- Avoids external API calls for recent topics

### 3. Rate Limiting
- Minimum 10 seconds between external API calls
- Maximum 100 requests per hour
- Automatic blocking with error responses

### 4. Cache Monitoring
- `/cache-status` endpoint for monitoring
- Real-time statistics and system health
- Cache hit ratios and performance metrics

This ensures reliable service while respecting Google Trends API limits.

## Tracked Topics

The API focuses on AI prompts and social media trends across 5 main clusters:

### 🎨 Poster Design
- AI Poster Design, propaganda poster ai, soviet style poster prompt
- vintage red cream poster, revolution poster design ai
- minimalist poster prompt, retro vintage poster prompt

### 🏢 Branding & Marketing
- AI Logo / Mascot Prompt, Product Mockup Generation
- Social Media Template Prompt, Styling Influencer Photos
- Interior / Room Design AI Prompt

### 👥 Character Creation
- 3D Character Creator, Anime Character Prompt
- kawaii cute design prompt, surreal art prompt ai
- 3d animation prompt ai

### 🤖 AI Media Tools
- ai image prompt, ai photo prompt, text to image
- ai video prompt, text to video ai, image editing ai
- video editing ai, enhance photo ai, remove background ai
- neon cyberpunk prompt, cinematic ai prompt

### 📱 Social Media & Ads
- tiktok video ai, tiktok ads creative, shopee affiliate tiktok
- video affiliate prompt, viral video prompt ai

## Database Schema

The API stores data in a Supabase table called `trend_keywords` with the following structure:

```sql
CREATE TABLE public.trend_keywords (
  id uuid NOT NULL DEFAULT extensions.uuid_generate_v4(),
  keyword text NULL,
  topic text NULL,
  score integer NULL,
  source text NULL,
  timestamp timestamp with time zone NULL DEFAULT now(),
  processed boolean NULL DEFAULT false,
  topic_cluster text NULL,
  intent text NULL,
  keyword_hash text NULL,
  day_bucket date NULL,
  CONSTRAINT trend_keywords_pkey PRIMARY KEY (id)
);

-- Unique constraint to prevent duplicates
CREATE UNIQUE INDEX ux_trend_keyword_unique 
ON public.trend_keywords (topic, keyword, day_bucket);

-- Text search index for keywords
CREATE INDEX idx_trend_keywords_keyword_trgm 
ON public.trend_keywords USING gin (keyword gin_trgm_ops);

-- Trigger to auto-set day_bucket
CREATE TRIGGER set_day_bucket 
BEFORE INSERT OR UPDATE ON trend_keywords 
FOR EACH ROW EXECUTE FUNCTION trg_set_day_bucket();
```

### Field Descriptions:
- `keyword`: The trending search term
- `topic`: The seed topic used to fetch trends
- `score`: Trend popularity score (0-100)
- `source`: Data source (pytrends, google_trends_json, fallback)
- `topic_cluster`: Grouped category (poster_design, branding_prompts, etc.)
- `intent`: Classified intent (commercial, creative, informational)
- `keyword_hash`: Unique hash for deduplication
- `day_bucket`: Date bucket for daily aggregation

## Deployment

### Vercel

The project is configured for Vercel deployment with `vercel.json`. Simply:

1. Connect your repository to Vercel
2. Add environment variables in Vercel dashboard
3. Deploy

### Environment Variables

Set the following environment variables in your deployment platform:

**Required:**
- `SUPABASE_URL`: Your Supabase project URL
- `SUPABASE_KEY`: Your Supabase service role key (for insert permissions)

**Optional:**
- `ENABLE_EXTENDED_FIELDS`: Enable topic_cluster, intent, keyword_hash fields (default: true)
- `ENABLE_DAY_BUCKET`: Enable day_bucket field for daily aggregation (default: true)
- `DATABASE_CLEANUP_INTERVAL`: Auto cleanup interval in seconds (default: 43200 = 12h)
- `DB_RETENTION_DAYS`: Data retention period in days (default: 30)
- `MIN_REQUEST_INTERVAL`: Minimum seconds between API calls (default: 10)
- `MAX_REQUESTS_PER_HOUR`: Rate limit per hour (default: 100)

## Debugging & Troubleshooting

### Test Database Connection
```bash
curl https://your-domain.vercel.app/debug/supabase
```

### Manual Insert Test
```bash
curl -X POST https://your-domain.vercel.app/debug/test-insert
```

### Check Logs
```bash
vercel logs --prod --follow
```

### Manual Database Cleanup
```bash
curl -X POST https://your-domain.vercel.app/maintenance/db-cleanup?days=7
```

## Contributing

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Add tests if applicable
5. Submit a pull request

## License

MIT License - see LICENSE file for details

## Notes

- The API includes fallback mechanisms for when PyTrends fails
- Multi-level caching prevents hitting Google Trends rate limits
- Focus is specifically on AI prompts and social media trends
- Data is automatically timestamped and deduplicated
- Automatic database cleanup keeps storage optimized
- Debug endpoints available for troubleshooting
- Intent classification helps categorize keywords by purpose
- Cluster-based topic organization for better trend analysis