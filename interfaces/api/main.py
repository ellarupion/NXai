from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware

from core.config import get_settings
from core.logging import configure_logging
from core.request_context import reset_actor_ip, set_actor_ip
from interfaces.api.deps import client_ip
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

    @app.middleware("http")
    async def remember_actor_ip(request: Request, call_next):
        # Кладём адрес на время запроса, чтобы записи журнала подхватывали его сами
        # (core/services/audit.py). reset обязателен и обязательно в finally: воркер
        # переиспользует поток между запросами, и оставленное значение приписало бы
        # чужой адрес следующему действию.
        token = set_actor_ip(client_ip(request))
        try:
            return await call_next(request)
        finally:
            reset_actor_ip(token)

    app.include_router(router)

    return app


app = create_app()
