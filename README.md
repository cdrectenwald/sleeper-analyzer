# Sleeper Fantasy Football Analyzer

A data pipeline and chat-based analytics system for Sleeper fantasy football leagues. Fetches league data from the Sleeper API, computes advanced metrics (all-play records, luck scores), and provides an LLM-powered chat interface to query your league's stats.

## What This Is

This tool helps fantasy football managers understand their performance beyond just wins and losses:

- **All-Play Records**: How would you have done if you played every team every week?
- **Luck Score**: The difference between your actual wins and expected wins based on all-play
- **Historical Analysis**: Query multiple seasons of data through natural language
- Responds in a Bill Simmon's esque voice

<img width="527" height="398" alt="image" src="https://github.com/user-attachments/assets/8ad93d9c-2dc0-4ebc-b261-3d3cc702e9f9" />


## Prerequisites

- Python 3.11+
- A Sleeper fantasy football league ID (find it in your league URL: `sleeper.app/leagues/{league_id}`)
- OpenAI API key (for the chat interface)

## TODOS

- Create Github action to update data
- Implement new data/metrics
- Token analysis
 
## Setup

### 1. Create a Virtual Environment

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
```

Or on Linux/macOS:
```bash
python -m venv .venv
source .venv/bin/activate
```

### 2. Install Dependencies

```bash
pip install -r requirements.txt
```

### 3. Configure Environment Variables

Create a `.env` file in the project root:

```env
OPENAI_API_KEY=sk-your-api-key-here
```

Or set it directly:
```powershell
$env:OPENAI_API_KEY = "sk-your-api-key-here"
```

## Usage

### Ingestion: Fetch League Data

Pull all data for a league from the Sleeper API:

```bash
python fetch_all.py --league-id 1257104404557856768
```

Options:
- `--max-week 18` - Number of weeks to fetch (default: 18)
- `--fetch-players` - Also cache the full NFL player database (large file)

### Build Metrics

Compute all-play records and luck scores:

```bash
python build_metrics.py --league-id 1257104404557856768 --season 2025
```

Options:
- `--week-start 1` - Start from a specific week
- `--week-end 14` - End at a specific week

### Check Data Health

Verify your data is complete and metrics are built:

```bash
python check_data.py
```

### Run the API Server

Start the FastAPI server:

```bash
uvicorn app:app --reload
```

The API will be available at `http://localhost:8000`

### API Documentation

Interactive API documentation is available at:
- **Swagger UI**: http://localhost:8000/docs
- **ReDoc**: http://localhost:8000/redoc

## API Reference

### Endpoints

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/` | Web chat UI |
| `GET` | `/glossary` | Stats glossary page |
| `POST` | `/chat` | Chat with the AI analyst |
| `GET` | `/health` | Basic liveness check |
| `GET` | `/health/ready` | Readiness check (verifies DB) |

### POST /chat

Submit a natural language question about your fantasy football league.

**Request Body:**
```json
{
  "message": "Who was the luckiest manager?",
  "season": "2024",           // optional, defaults to current season
  "league_id": "123..."       // optional, derived from season
}
```

**Response:**
```json
{
  "answer": "Here's the thing about luck in 2024...",
  "season": "2024",
  "league_id": "1124856081965645824"
}
```

**Error Responses:**

| Status | Error Code | Description |
|--------|------------|-------------|
| 400 | `validation_error` | Invalid request format |
| 422 | - | Pydantic validation failed |
| 429 | `llm_rate_limit` | OpenAI rate limit exceeded |
| 502 | `llm_error` | OpenAI service error |
| 504 | `llm_timeout` | OpenAI request timeout |

## API Examples

### Chat Endpoint

**PowerShell (Invoke-RestMethod):**
```powershell
Invoke-RestMethod -Method Post -Uri "http://localhost:8000/chat" `
  -ContentType "application/json" `
  -Body '{"message": "Who was the luckiest team in 2024?"}'
```

**cURL:**
```bash
curl -X POST http://localhost:8000/chat \
  -H "Content-Type: application/json" \
  -d '{"message": "Who was the luckiest team in 2024?", "season": "2024"}'
```

**Example Response:**
```json
{
  "answer": "Based on the luck leaderboard for 2024, TeamX was the luckiest with a luck score of +3.2, meaning they won about 3 more games than expected based on their points scored.",
  "season": "2024",
  "league_id": "1124856081965645824"
}
```

### More Query Examples

```powershell
# Full season luck leaderboard
Invoke-RestMethod -Method Post -Uri "http://localhost:8000/chat" `
  -ContentType "application/json" `
  -Body '{"message": "Show me the luck leaderboard for the 2024 season"}'

# Specific week range analysis
Invoke-RestMethod -Method Post -Uri "http://localhost:8000/chat" `
  -ContentType "application/json" `
  -Body '{"message": "Who was unluckiest in weeks 10-14 of 2024?"}'

# Compare seasons
Invoke-RestMethod -Method Post -Uri "http://localhost:8000/chat" `
  -ContentType "application/json" `
  -Body '{"message": "Compare my luck between 2023 and 2024"}'
```

## Project Structure

```
sleeper-analyzer/
├── app.py                 # Application entry point (thin wrapper)
├── fetch_all.py           # Data ingestion from Sleeper API
├── build_metrics.py       # Compute all-play and luck metrics
├── check_data.py          # Data health verification
├── schema.sql             # SQLite database schema
├── requirements.txt       # Python dependencies
├── Makefile               # Common development commands
├── static/                # Web UI assets
│   ├── index.html         # Chat interface
│   ├── glossary.html      # Stats glossary
│   ├── styles.css         # Styling
│   └── app.js             # Frontend JavaScript
├── src/
│   ├── api/               # FastAPI application module
│   │   ├── __init__.py
│   │   ├── app.py         # App factory and configuration
│   │   ├── exceptions.py  # Custom exception hierarchy
│   │   ├── models.py      # Pydantic request/response schemas
│   │   └── routes/        # Route modules
│   │       ├── chat.py    # /chat endpoint
│   │       └── health.py  # Health check endpoints
│   ├── chat/
│   │   ├── llm.py         # OpenAI integration with tools
│   │   └── tools.py       # Database query functions for LLM
│   ├── common/
│   │   └── logging.py     # Structured logging setup
│   ├── config.py          # Application configuration
│   └── sleeper/
│       ├── api.py         # Sleeper API client
│       └── db.py          # Database operations
├── tests/                 # pytest test suite
│   ├── test_all_play.py   # All-play calculation tests
│   ├── test_metrics_rollup.py  # Metrics integration tests
│   ├── test_web_app.py    # API endpoint tests
│   └── ...
└── data/                  # Generated data (gitignored)
    ├── raw/               # Raw JSON from Sleeper API
    └── processed/         # SQLite database
```

## Development

### Run Tests

```bash
pytest -v
```

### Using the Makefile

```bash
make init      # Create venv and install dependencies
make fetch     # Fetch data for default league
make metrics   # Build metrics for default league/season
make run       # Start the API server
make test      # Run tests
make check     # Check data health
```

Override defaults:
```bash
make fetch LEAGUE_ID=867850980811821056
make metrics LEAGUE_ID=867850980811821056 SEASON=2022
```

## Configuration

The app uses environment variables and a `.env` file for configuration:

| Variable | Default | Description |
|----------|---------|-------------|
| `OPENAI_API_KEY` | (required) | Your OpenAI API key |
| `DB_PATH` | `data/processed/sleeper.sqlite` | SQLite database location |
| `DEFAULT_SEASON` | `2025` | Default season for queries |
| `LOG_LEVEL` | `INFO` | Logging verbosity |

## License

MIT



