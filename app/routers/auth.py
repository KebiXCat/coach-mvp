import secrets
import os
from dotenv import load_dotenv
from fastapi import APIRouter, Request, HTTPException, Depends
import httpx
from fastapi.responses import RedirectResponse, JSONResponse
from urllib.parse import urlencode
from datetime import datetime, timezone, timedelta
from jwt import encode
import sqlalchemy as sa
from app.database import user_table, connected_accounts_table, get_db
from cryptography.fernet import Fernet
load_dotenv()

client_id = os.getenv('GITHUB_CLIENT_ID') 
client_secret = os.getenv('GITHUB_CLIENT_SECRET') 
scope = "user:email repo"
redirect_uri = os.getenv("GITHUB_CALLBACK_URL")
SECRET_KEY = os.getenv("SECRET_KEY")
ACCESS_TOKEN_EXPIRE_MINUTES = os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES")
ENCRYPTION_KEY = os.getenv("ENCRYPTION_KEY")
if ENCRYPTION_KEY is None:
    raise RuntimeError("ENCRYPTION KEY IS NOT SET")
cipher = Fernet(ENCRYPTION_KEY)
router = APIRouter()
@router.get("/login_github")
async def login_github():
    state = secrets.token_urlsafe(16)   
    params = {"client_id" : client_id, "scope":scope, "state": state,
               "redirect_uri" : redirect_uri}
    query_string = urlencode(params)
    url = f"https://github.com/login/oauth/authorize?{query_string}"
    response = RedirectResponse(url)
    response.set_cookie(
        key="state",
        value=state,
        httponly=True,
        #secure=True,
        max_age = 600
    )
    return response
@router.get("/callback")
async def callback_github(request: Request, code: str, state: str, connection = Depends(get_db)):
    params = {"client_id" : client_id, "client_secret" : client_secret,
               "code" : code, "redirect_uri" : redirect_uri}
    bef_state = request.cookies.get("state")
    if bef_state != state:
        raise HTTPException(status_code=400, detail="Wrong state")
    async with httpx.AsyncClient() as client:
        responseAccessToken = await client.post(
            'https://github.com/login/oauth/access_token',
            headers={
                "Accept": "application/json"
            },
            data=params
        )
        access_token = responseAccessToken.json().get("access_token")
        if access_token is None:
            raise HTTPException(status_code=400, detail="Failed to obtain access token from Github")
        responseUser = await client.get(
            'https://api.github.com/user',
            headers={
                "Authorization" : f"Bearer {access_token}",
                "Accept": "application/vnd.github+json"
            }
        )
        responseEmail = await client.get(
            'https://api.github.com/user/emails',
            headers={
                "Authorization" : f"Bearer {access_token}",
                "Accept": "application/vnd.github+json"
            }
        )
    github_id = responseUser.json().get("id")
    login = responseUser.json().get("login")
    avatar_url = responseUser.json().get("avatar_url")
    if github_id is None:
        raise HTTPException(status_code=400, detail="Failed to obtain id from Github")
    if login is None:
        raise HTTPException(status_code=400, detail="Failed to obtain login from Github")
    if avatar_url is None:
        raise HTTPException(status_code=400, detail="Failed to obtain avatar_url from Github")
    email = None
    for em in responseEmail.json():
        if em.get("primary") == True and em.get("verified") == True:
            email = em.get("email")
            break
    if email is None:
        raise HTTPException(status_code=400, detail="Failed to obtain email from Github")
    stmt = sa.select(connected_accounts_table).where(connected_accounts_table.c.provider == "github",
                                                     connected_accounts_table.c.provider_id == github_id)
    result = connection.execute(stmt)
    row = result.first()
    encrypted_token = cipher.encrypt(access_token.encode()).decode()
    if row is None:
        created_at = datetime.now(timezone.utc)
        stmt1 = sa.insert(user_table).values(email=email, username=login, created_at=created_at, avatar_url=avatar_url)
        result = connection.execute(stmt1)
        primary_key_user_table = result.inserted_primary_key[0]
        stmt2 = sa.insert(connected_accounts_table).values(provider="github", provider_id=github_id, created_at=created_at, user_id=primary_key_user_table, access_token=encrypted_token)
        connection.execute(stmt2)
    else:
        primary_key_user_table = row.user_id
        stmt = sa.update(connected_accounts_table).where(connected_accounts_table.c.user_id == primary_key_user_table).values(access_token=encrypted_token)
        connection.execute(stmt)
    connection.commit()
    my_access_token = create_access_token(primary_key_user_table)
    response = JSONResponse(content={"message" : "Succesfully got user's data from Github"})
    response.set_cookie(
        key="access_token",
        value=my_access_token,
        httponly=True,
        #secure=True,
        max_age=int(ACCESS_TOKEN_EXPIRE_MINUTES)*60
    )
    return response
def create_access_token(user_id: int):
    payload = {"sub" : str(user_id), "exp" : datetime.now(timezone.utc) + timedelta(minutes=int(ACCESS_TOKEN_EXPIRE_MINUTES)), "iat": datetime.now(timezone.utc)}
    access_token = encode(payload, SECRET_KEY, 'HS256')
    return  access_token
@router.get("/me")
async def me():
    return {"message" : "works"}