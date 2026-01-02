# Makefile for sleeper-analyzer
# Usage: make <target>

.PHONY: init fetch fetch-players metrics run test check lint format clean

# Default league/season (override with make fetch LEAGUE_ID=xxx)
LEAGUE_ID ?= 1257104404557856768
SEASON ?= 2025

# Create virtual environment and install dependencies
init:
	python -m venv .venv
	.venv\Scripts\pip install -r requirements.txt

# Fetch data for a league
fetch:
	python fetch_all.py --league-id $(LEAGUE_ID)

# Fetch player name mappings (run once, ~15MB)
fetch-players:
	python fetch_all.py --league-id $(LEAGUE_ID) --fetch-players

# Build metrics for a league/season
metrics:
	python build_metrics.py --league-id $(LEAGUE_ID) --season $(SEASON)

# Run the FastAPI server
run:
	uvicorn app:app --reload

# Run tests
test:
	pytest -v

# Check data health
check:
	python check_data.py

# Lint with ruff (if installed)
lint:
	ruff check .

# Format with black and ruff (if installed)
format:
	black .
	ruff check --fix .

# Clean generated files
clean:
	rm -rf __pycache__ .pytest_cache .ruff_cache .mypy_cache
	rm -rf src/__pycache__ src/*/__pycache__ tests/__pycache__
	find . -name "*.pyc" -delete
