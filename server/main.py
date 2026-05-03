import argparse
from contextlib import asynccontextmanager
from typing import AsyncIterator

import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from widget_server.api import router, start_session_bridge, stop_session_bridge


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    await start_session_bridge()
    try:
        yield
    finally:
        await stop_session_bridge()


def create_app() -> FastAPI:
    app = FastAPI(lifespan=lifespan)
    app.include_router(router)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    return app


def main() -> None:
    parser = argparse.ArgumentParser(description="Start the Emilia widget backend")
    parser.add_argument("--host", type=str, default="127.0.0.1", help="Server host")
    parser.add_argument("--port", type=int, default=8000, help="Server port")
    args = parser.parse_args()

    uvicorn.run(create_app(), host=args.host, port=args.port)


app = create_app()


if __name__ == "__main__":
    main()
