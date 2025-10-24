# MGTrends - Visual AI Art Trends API

A Flask API that fetches trending keywords related to visual AI art and design from Google Trends, with data storage in Supabase.

## About

MGTrends is a specialized trends tracking API designed for the creative and AI art community. It monitors trending keywords specifically related to visual AI art, digital design, and emerging creative technologies. Unlike general trend APIs, MGTrends focuses on:

- **AI Art & Generation Tools**: Tracks trends for tools like Midjourney, Stability AI, Adobe Firefly
- **Digital Design**: Monitors graphic design, poster design, and motion graphics trends
- **Creative Technologies**: Follows text-to-image, text-to-video, and generative design trends
- **Visual Aesthetics**: Captures trending art styles and visual design movements

The API automatically fetches trending data from Google Trends, stores it in Supabase for historical analysis, and provides clean JSON responses perfect for creative apps, design tools, or trend analysis dashboards.

**Perfect for:**
- Creative agencies tracking design trends
- AI art platforms monitoring popular styles
- Design tool developers understanding user interests
- Researchers studying creative technology adoption
- Content creators staying ahead of visual trends

## Features

- 🎨 **AI Art Focused**: Tracks trends in AI art, digital design, and visual creation tools
- 📊 **Google Trends Integration**: Uses PyTrends library with fallback to unofficial Google Trends API
- 💾 **Supabase Storage**: Automatically stores trending keywords in Supabase database
- ⚡ **Caching**: 1-hour cache to optimize API calls
- 🚀 **Vercel Ready**: Configured for easy deployment on Vercel

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
SUPABASE_KEY=your_supabase_anon_key
```

4. Run the application:
```bash
python api/index.py
```

The API will be available at `http://localhost:5000`

## API Endpoints

### GET /

Returns trending keywords for a randomly selected visual AI art topic.

**Response Example:**
```json
{
  "source": "google_trends",
  "topic": "AI art",
  "trend_keywords": [
    {
      "keyword": "ai art generator",
      "score": 85,
      "topic": "AI art",
      "source": "google_trends",
      "timestamp": "2024-10-24T10:30:00.000000"
    }
  ]
}
```

## Tracked Topics

The API focuses on visual and AI art trends, including:

- AI art, digital art, concept art
- Graphic design, poster design, motion graphics
- AI tools: Midjourney, Stability AI, Adobe Firefly
- Text-to-image/video generation
- Prompt design and generative design
- Visual aesthetics and design trends

## Database Schema

The API stores data in a Supabase table called `trend_keywords` with the following structure:

```sql
CREATE TABLE trend_keywords (
  id SERIAL PRIMARY KEY,
  keyword TEXT NOT NULL,
  score INTEGER NOT NULL,
  topic TEXT NOT NULL,
  source TEXT NOT NULL,
  timestamp TIMESTAMP NOT NULL,
  created_at TIMESTAMP DEFAULT NOW()
);
```

## Deployment

### Vercel

The project is configured for Vercel deployment with `vercel.json`. Simply:

1. Connect your repository to Vercel
2. Add environment variables in Vercel dashboard
3. Deploy

### Environment Variables

Set the following environment variables in your deployment platform:

- `SUPABASE_URL`: Your Supabase project URL
- `SUPABASE_KEY`: Your Supabase anonymous/public key

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
- Caching is implemented to avoid hitting rate limits
- Focus is specifically on visual/AI art trends rather than general topics
- Data is automatically timestamped and stored for trend analysis