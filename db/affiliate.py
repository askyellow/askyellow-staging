from fastapi import APIRouter, Query
from db.affiliate import get_affiliate_options

router = APIRouter()

@router.get("/affiliate/options")
def affiliate_options(
    q: str = Query(...),
    intent: str = Query("unknown")
):
    options = get_affiliate_options(intent=intent, query=q)

    return {
        "count": len(options),
        "options": options
    }

