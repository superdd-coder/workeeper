from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

from src.services import init_services
from src.tasks import task_manager
from src.config import get_config

logging.getLogger("src").setLevel(logging.INFO)
logging.getLogger("meeting").setLevel(logging.INFO)
logging.getLogger("src.meeting").setLevel(logging.INFO)
logging.getLogger("task_manager").setLevel(logging.INFO)
logging.getLogger("api").setLevel(logging.INFO)
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("qdrant_client").setLevel(logging.WARNING)

# Ensure loggers used in this project have a visible handler in the
# container. Uvicorn only configures its own loggers; without this, any
# logger named under "src.*" or "meeting" (e.g. "src.meeting.transcription
# .dashscope") has no destination and falls back to lastResort, which
# only emits WARNING+. Attach a single StreamHandler to the root and let
# propagation carry it to children.
#
# Guard against double-import: when launched via "python -m src.main",
# this module runs once as __main__ and again when uvicorn imports
# "src.main:app". Without the guard, we'd add duplicate handlers.
_root_handler = logging.StreamHandler()
_root_handler.setFormatter(
    logging.Formatter("%(asctime)s [%(name)s] %(levelname)s: %(message)s")
)
logging.getLogger().addHandler(_root_handler)

# Suppress expected FunASR internal warnings when using SenseVoiceSmall
# without passing punc_model to the main AutoModel (we use separate post-processing).
class _FunASRDiarizationFilter(logging.Filter):
    _SUPPRESSED = (
        "punc_model is missing, falling back to vad_segment mode",
        "No timestamp found in ASR result",
    )
    def filter(self, record: logging.LogRecord) -> bool:
        return not any(msg in record.getMessage() for msg in self._SUPPRESSED)

logging.getLogger().addFilter(_FunASRDiarizationFilter())


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_services()
    await task_manager.start()
    yield
    await task_manager.stop()


app = FastAPI(title="Workeeper", version="0.1.0", lifespan=lifespan)

# CORS for development
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

from src.api.routes.query import router as query_router
from src.api.routes.documents import router as documents_router
from src.api.routes.collections import router as collections_router
from src.api.routes.config import router as config_router
from src.api.routes.recall import router as recall_router
from src.api.routes.logs import router as logs_router
from src.api.routes.info import router as info_router
from src.meeting.routes import router as meeting_router
from src.hot_words.routes import router as hot_words_router

app.include_router(query_router, prefix="/api")
app.include_router(documents_router, prefix="/api")
app.include_router(collections_router, prefix="/api")
app.include_router(config_router, prefix="/api")
app.include_router(recall_router, prefix="/api")
app.include_router(logs_router, prefix="/api")
app.include_router(info_router, prefix="/api")
app.include_router(meeting_router, prefix="/api")
app.include_router(hot_words_router)


@app.get("/health")
def health():
    return {"status": "ok"}


# Serve React frontend in production
FRONTEND_DIST = Path(__file__).parent.parent / "frontend" / "dist"

if FRONTEND_DIST.exists():
    app.mount("/assets", StaticFiles(directory=FRONTEND_DIST / "assets"), name="static-assets")

    @app.get("/{full_path:path}")
    async def serve_spa(full_path: str):
        file = FRONTEND_DIST / full_path
        if file.is_file():
            return FileResponse(file)
        return FileResponse(FRONTEND_DIST / "index.html")


if __name__ == "__main__":
    import uvicorn
    from src.config import get_config
    config = get_config()
    uvicorn.run(
        app,
        host=config.server.host,
        port=config.server.api_port,
        reload=False,
    )
