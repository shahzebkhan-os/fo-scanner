# NSE F&O Scanner (INDmoney Scraper)

A production-ready web application that scrapes real-time Futures & Options data from INDmoney, processes it to calculate technical signals, and serves it through a React dashboard.

## Features
- **Real-time Option Chain**: Fetches complete live option chains for major NSE stocks and indices.
- **Top Picks Engine**: Scores call and put options dynamically based on OI change, volume spikes, and IV to highlight the best trading opportunities.
- **Akamai Bypass**: Uses asynchronous `curl_cffi` to bypass Cloudflare/Akamai bot-protection without requiring API keys.
- **Multi-tenant Rendering**: A single Docker container serves both the optimized Vite/React static assets and the high-performance FastAPI Python backend on port 8000.

## Quickstart

### Option 1: Docker (Recommended)
You can directly spin up the entire application using Docker Compose.

```bash
git clone https://github.com/shahzebkhan-os/fo-scanner.git
cd fo-scanner
docker-compose up --build -d
```
The application will be running at `http://localhost:8000`.

### Option 2: Local Development

#### Requirements
- Node.js 20+
- Python 3.11+
- `pip` and `npm`

#### 1. Setup Backend
```bash
# Create a virtual environment
python3 -m venv venv
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Create an env file if you have a premium INDmoney token (optional)
cp .env.example .env
```

#### 2. Build Frontend
```bash
npm install
npm run build
```

#### 3. Run Application
```bash
# Serves both the React frontend and FastAPI backend
uvicorn main:app --host 0.0.0.0 --port 8000
```
Visit `http://localhost:8000` to access the scanner.

## Architecture

*   **Backend:** FastAPI, `curl_cffi`, BeautifulSoup. 
*   **Frontend:** React 19, Vite, Tailwind CSS (via pure CSS implementation).
*   **Data Source:** INDmoney public web scraping (`__NEXT_DATA__` SSR extraction) mapped to traditional NSE data structures.

## Disclaimer

This tool is for educational purposes and market research only. Do not use this as your sole indicator for financial trades.
