from fastapi import APIRouter, Response

router = APIRouter()

@router.head("/health")
def health_head(response: Response):
    response.status_code = 200
    return
