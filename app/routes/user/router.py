from fastapi import APIRouter, Request
from common.schema import APIResponse, response_maker
from . import model, schema
router = APIRouter(prefix="/user", tags=["user"])

@router.get("/", response_model=schema.UserResponse, responses=response_maker[404])
async def get_users(request: Request):
    return APIResponse
