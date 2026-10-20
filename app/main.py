from fastapi import FastAPI

from app.api import triagem
from app.api.erros import registrar_handlers

app = FastAPI(title="MediFlow")
registrar_handlers(app)
app.include_router(triagem.router)