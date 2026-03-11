# Quick Start Guide - How to Run NSE F&O Scanner

This guide will help you get the NSE F&O Scanner running on your machine in just a few minutes.

## Prerequisites

Before you begin, make sure you have these installed:

- **Python 3.11 or higher** - [Download Python](https://www.python.org/downloads/)
- **Node.js 20 or higher** - [Download Node.js](https://nodejs.org/)
- **Git** - [Download Git](https://git-scm.com/)

To check if you have them installed, run:

```bash
python --version    # or python3 --version
node --version
git --version
```

## Option 1: Quick Start (Recommended for Beginners)

### Step 1: Get the Code

```bash
# Clone the repository
git clone https://github.com/shahzebkhan-os/fo-scanner.git

# Navigate into the directory
cd fo-scanner
```

### Step 2: Set Up Environment Variables

```bash
# Copy the example environment file
cp .env.example .env

# Edit the .env file with your preferred text editor
# nano .env    # or use vim, code, notepad, etc.
```

**Add your credentials** (optional but recommended for full functionality):
```env
INDSTOCKS_TOKEN="your_token_here"        # For live market data
TELEGRAM_BOT_TOKEN="your_bot_token"      # For alerts (optional)
TELEGRAM_CHAT_ID="your_chat_id"          # For alerts (optional)
```

**Note:** The application will work without these credentials, but with limited functionality.

### Step 3: Run the Application

```bash
# Make the start script executable (Linux/Mac only)
chmod +x start.sh

# Run the startup script
./start.sh
```

**For Windows users:**
```bash
# Use Git Bash or WSL, or run manually (see Option 2 below)
bash start.sh
```

### Step 4: Access the Application

Open your browser and go to:

- **Frontend (Main UI):** http://localhost:5175
- **API Documentation:** http://localhost:8000/docs
- **Backend API:** http://localhost:8000

**That's it!** The scanner should now be running.

To stop the application, press `Ctrl+C` in the terminal.

---

## Option 2: Manual Setup (For More Control)

If the automatic startup script doesn't work, or you prefer to set things up manually:

### Step 1: Set Up Python Backend

```bash
# Navigate to backend directory
cd backend

# Create a virtual environment
python -m venv venv

# Activate the virtual environment
# On Linux/Mac:
source venv/bin/activate
# On Windows:
venv\Scripts\activate

# Install Python dependencies
pip install -r requirements.txt

# Initialize the database
python -c "import db; db.init_db()"

# Start the backend server
python main.py
```

The backend should now be running at http://localhost:8000

### Step 2: Set Up Frontend (Open a New Terminal)

```bash
# Navigate to frontend directory (from project root)
cd frontend

# Install Node dependencies
npm install

# Start the development server
npm run dev -- --port 5175
```

The frontend should now be running at http://localhost:5175

---

## Option 3: Using Docker (Easiest)

If you have Docker installed, this is the simplest way:

### Step 1: Copy Environment Variables

```bash
cp .env.example .env
# Edit .env if needed
```

### Step 2: Build and Run

```bash
# Build and start the container
docker-compose up -d

# View logs
docker-compose logs -f

# Stop when done
docker-compose down
```

The application will be available at http://localhost:8000

---

## Troubleshooting

### "Module not found" or "Package not installed" errors

**Backend:**
```bash
cd backend
pip install -r requirements.txt
```

**Frontend:**
```bash
cd frontend
npm install
```

### Port Already in Use

If you see errors like "Address already in use":

```bash
# Kill processes on port 8000 (backend)
lsof -ti:8000 | xargs kill -9    # Linux/Mac
netstat -ano | findstr :8000     # Windows (then kill the PID)

# Kill processes on port 5175 (frontend)
lsof -ti:5175 | xargs kill -9    # Linux/Mac
netstat -ano | findstr :5175     # Windows (then kill the PID)
```

### Python Version Issues

Make sure you're using Python 3.11 or higher:

```bash
python3 --version
# or
python --version
```

If you have an older version, download the latest from [python.org](https://www.python.org/downloads/)

### Node.js Version Issues

Make sure you're using Node.js 20 or higher:

```bash
node --version
```

If you have an older version, download the latest from [nodejs.org](https://nodejs.org/)

### Database Initialization Error

If you see database errors:

```bash
cd backend
python -c "import db; db.init_db()"
```

---

## Getting API Credentials (Optional)

### INDstocks API Token

1. Visit [INDstocks API](https://api.indstocks.com/)
2. Sign up for an account
3. Generate an API token
4. Add it to your `.env` file: `INDSTOCKS_TOKEN="your_token_here"`

### Telegram Bot (For Alerts)

1. Open Telegram and search for `@BotFather`
2. Send `/newbot` and follow the instructions
3. Copy the bot token to `.env`: `TELEGRAM_BOT_TOKEN="your_bot_token"`
4. To get your Chat ID:
   - Search for `@userinfobot` on Telegram
   - Send `/start`
   - Copy your ID to `.env`: `TELEGRAM_CHAT_ID="your_chat_id"`

---

## What's Next?

Once the application is running:

1. **Explore the UI** - The main dashboard shows real-time market data
2. **Check the API Docs** - Visit http://localhost:8000/docs for interactive API documentation
3. **Read the README** - See [README.md](README.md) for detailed feature documentation
4. **Try Backtesting** - See [README_BACKTESTING.md](README_BACKTESTING.md) for historical testing

---

## Still Having Issues?

- Check [README.md](README.md) for more detailed documentation
- Open an issue at [GitHub Issues](https://github.com/shahzebkhan-os/fo-scanner/issues)
- Review logs in `fo-scanner.log` for error details

---

## Quick Reference Commands

```bash
# Start the application
./start.sh

# Stop (press in terminal)
Ctrl+C

# Update dependencies
cd backend && pip install -r requirements.txt
cd frontend && npm install

# Rebuild frontend
cd frontend && npm run build

# Run with Docker
docker-compose up -d
docker-compose logs -f
docker-compose down
```

---

**Happy Trading!** 🚀📈
