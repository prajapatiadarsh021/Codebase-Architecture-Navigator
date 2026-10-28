import os
os.environ["GIT_PYTHON_REFRESH"] = "quiet"

import sys
from pathlib import Path

# Ensure backend directory is in sys.path for serverless runtimes
backend_dir = Path(__file__).resolve().parent
if str(backend_dir) not in sys.path:
    sys.path.insert(0, str(backend_dir))

from app.main import app

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
