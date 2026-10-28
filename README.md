# Multi-Agent Codebase Architecture Navigator

An interactive architectural mapping, impact analysis, and onboarding platform powered by **Google Gemini**, **Tree-sitter AST parsing**, **LangGraph multi-agent orchestration**, **Neo4j**, **Qdrant**, and **React Flow**.

---

## Features

- **Automated Codebase Ingestion**: Clone and index any public GitHub repository or point to local directories using Tree-sitter AST parsing.
- **Dependency & Call Graphing**: Maps classes, functions, files, and their call dependencies into an interactive graph with React Flow.
- **Multi-Agent Blast Radius & Impact Analysis**: Evaluates proposed modifications using Google Gemini and LangGraph to calculate change risk levels, identify impacted files, and suggest regression tests.
- **Hybrid Storage & In-Memory Fallbacks**: Seamlessly integrates with Neo4j and Qdrant, with automatic embedded fallback stores when external databases are offline.

---

## Project Structure

```
├── backend/
│   ├── app/
│   │   ├── agents/         # LangGraph multi-agent impact reasoning
│   │   ├── api/            # FastAPI endpoints & schemas
│   │   ├── core/           # Database connections & config
│   │   ├── parser/         # Tree-sitter AST parsing & sample codebases
│   │   ├── ingest.py       # Codebase cloning, indexing & embedding
│   │   └── main.py         # FastAPI application entrypoint
│   ├── .env.example        # Environment variable template
│   └── requirements.txt    # Python dependencies
├── frontend/
│   ├── src/                # React 19 application with React Flow
│   ├── package.json        # Frontend scripts and dependencies
│   └── vite.config.js      # Vite dev server configuration & API proxy
├── start-dev.bat           # One-click startup script for Windows
└── README.md
```

---

## Getting Started

### 1. Prerequisites
- **Python 3.10+**
- **Node.js 18+** & npm
- **Google Gemini API Key** (from [Google AI Studio](https://aistudio.google.com/app/apikey))

### 2. Backend Setup
```bash
cd backend
copy .env.example .env
# Add your GEMINI_API_KEY in backend/.env
pip install -r requirements.txt
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload
```

### 3. Frontend Setup
```bash
cd frontend
npm install
npm run dev
```

Visit [http://localhost:5173](http://localhost:5173) in your browser.

Or on Windows, simply double-click **`start-dev.bat`** to start both servers together.
