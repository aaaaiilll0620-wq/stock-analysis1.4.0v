# FinMind Stock Analysis Project

## Project Structure & Architecture
This is a multi-modular Python quantitative stock analysis and backtesting system.
- `config`: Handles environment variables, parameters, and FinMind API initialization.
- `data_provider`: Fetches and caches clean market data from FinMind.
- `crawler`: Handles external or fallback web scraping tasks.
- `fundamentals`: Analyzes financial statements and company health metrics.
- `technical_analysis`: Calculates technical indicators (e.g., Moving Averages, RSI).
- `market_sentiment`: Tracks market breadth, institutional investors, and sentiment.
- `sector`: Analyzes industry sector performance and cash flow.
- `tdcc_provider`: Processes Taiwan TDCC (Taiwan Depository & Clearing Corporation) shareholding distribution data.
- `valuation`: Computes intrinsic values and price fair ranges.
- `scoring_manager`: Consolidates multi-dimensional signals into a unified stock score.
- `models`: Houses predictive or mathematical models for strategy alignment.
- `backtest`: Executes trading strategy simulation, tracks entry/exit signals, and calculates cost basis.
- `advisor`: Generates actionable insights or final portfolio recommendations based on scores.
- `main`: Main entry point or execution controller for the entire workflow.

## Core Data Conventions
- Stock ID format: Taiwan stock codes (e.g., "2330").
- FinMind standard columns: `date` (str), `stock_id` (str), `open`, `max`, `min`, `close`, `Trading_Volume`.
- Dataframes must be vectorized via Pandas for calculations; avoid using iterative loops.

## AI Instructions & Token Optimization Style
- **Cache-First**: Leverage file attachments via `@` in Claude Desktop to reuse module code.
- **Incremental Output**: DO NOT rewrite the entire file. ONLY output the specific methods, functions, or lines of code that need modification.
- **Short Context**: Keep answers dense and direct. Use pseudo-code or logic steps before writing large code blocks if requested.