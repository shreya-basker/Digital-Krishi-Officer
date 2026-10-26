from fastapi import APIRouter, FastAPI
from fastapi.staticfiles import StaticFiles

from app.config import settings
from app.routers import auth, chat, decisions, farms, market

app = FastAPI(title="Agrisathi API", version="0.1.0")

api = APIRouter(prefix="/api")
for module in (auth, farms, decisions, market, chat):
    api.include_router(module.router)


@api.get("/health")
def health():
    return {"status": "ok"}


app.include_router(api)
# mounted last so /api routes win; html=True serves index.html and 404.html
app.mount("/", StaticFiles(directory=settings.frontend_dir, html=True), name="frontend")
