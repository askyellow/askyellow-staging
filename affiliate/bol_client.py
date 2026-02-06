# affiliate/bol_client.py
import httpx
import base64
import time

BOL_TOKEN_URL = "https://login.bol.com/token"
BOL_SEARCH_URL = "https://api.bol.com/retailer/products"

class BolClient:
    def __init__(self, client_id: str, client_secret: str):
        self.client_id = client_id
        self.client_secret = client_secret
        self._token = None
        self._token_expiry = 0

    async def _get_token(self) -> str:
        if self._token and time.time() < self._token_expiry:
            return self._token

        auth = base64.b64encode(
            f"{self.client_id}:{self.client_secret}".encode()
        ).decode()

        async with httpx.AsyncClient() as client:
            res = await client.post(
                BOL_TOKEN_URL,
                headers={
                    "Authorization": f"Basic {auth}",
                    "Content-Type": "application/x-www-form-urlencoded"
                },
                data="grant_type=client_credentials"
            )
            res.raise_for_status()
            data = res.json()

        self._token = data["access_token"]
        self._token_expiry = time.time() + data["expires_in"] - 30
        return self._token

    async def search_products(self, query: str, limit: int = 50):
        token = await self._get_token()

        async with httpx.AsyncClient() as client:
            res = await client.get(
                BOL_SEARCH_URL,
                headers={
                    "Authorization": f"Bearer {token}",
                    "Accept": "application/vnd.retailer.v10+json"
                },
                params={
                    "query": query,
                    "limit": limit
                }
            )
            res.raise_for_status()
            return res.json()
