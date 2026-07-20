from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from core.config import get_settings
from core.logging import configure_logging
from interfaces.api.routers import router


@asynccontextmanager
async def lifespan(app: FastAPI):
    configure_logging(get_settings())
    yield


def create_app() -> FastAPI:
    app = FastAPI(title="NXai Admin API", lifespan=lifespan)

    # Дев-CORS для React (Vite) на localhost — в проде фронтенд раздаётся тем же
    # nginx, что и API (см. ARCHITECTURE.md / deploy/nginx, перенесено из NX).
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://localhost:5173"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(router)

    return app


app = create_app()
