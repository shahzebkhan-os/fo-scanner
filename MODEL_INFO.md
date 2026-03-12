# Model Information

## AI Models Used in This Project

**This project does NOT use any AI/ML models.** The fo-scanner is a quantitative financial analysis tool that uses:

### Mathematical Models
- **Black-Scholes Model**: For options Greeks calculation (Delta, Gamma, Theta, Vega)
- **Statistical Models**: For IV Rank, PCR analysis, and unusual options activity detection

### External APIs
- **IndStocks API**: For live NSE market data
- **NSE Public APIs**: For bulk/block deals and FII/DII data
- **Telegram Bot API**: For alert notifications

## If You're Asking About GitHub Agents

If this question is about which Claude model is being used by GitHub agents working on this repository:

### Claude Agent Information
- **Current Agent Model**: Claude Sonnet 4.5
- **Model ID**: `claude-sonnet-4-5-20250929`
- **Knowledge Cutoff**: January 2025

The GitHub agent helping with development tasks uses Claude Sonnet 4.5, which is Anthropic's frontier model optimized for coding tasks, offering an excellent balance of speed, intelligence, and cost-effectiveness.

For more information about Claude models, visit: https://www.anthropic.com/claude

## Technology Stack

This project is built with:
- **Backend**: Python FastAPI
- **Frontend**: React.js with Vite
- **Database**: SQLite
- **Trading Logic**: Custom Python algorithms for options analysis

No machine learning, LLMs, or AI inference is performed by this application.
