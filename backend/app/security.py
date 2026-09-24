import hashlib
import hmac
import re
import secrets
import threading
import time
from collections import defaultdict, deque
from datetime import timedelta
from urllib.parse import urlparse

from fastapi import HTTPException, Request, Response
from sqlalchemy import select
from .database import SessionToken, User, now


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    digest = hashlib.scrypt(password.encode(), salt=salt, n=16384, r=8, p=1)
    return f'{salt.hex()}:{digest.hex()}'


def verify_password(password: str, stored: str) -> bool:
    salt, digest = stored.split(':')
    computed = hashlib.scrypt(password.encode(), salt=bytes.fromhex(salt), n=16384, r=8, p=1)
    return hmac.compare_digest(computed.hex(), digest)


def token_hash(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


def create_session(db, user: User, response: Response, settings):
    token = secrets.token_urlsafe(48)
    db.add(
        SessionToken(
            user_id=user.id,
            token_hash=token_hash(token),
            expires_at=now() + timedelta(hours=settings.session_hours),
        )
    )
    db.commit()
    response.set_cookie(
        'legallens_session',
        token,
        httponly=True,
        secure=settings.secure_cookies,
        samesite='strict',
        max_age=settings.session_hours * 3600,
        path='/',
    )


def authenticate(request: Request, db) -> User:
    token = request.cookies.get('legallens_session', '')
    session = db.scalar(
        select(SessionToken).where(
            SessionToken.token_hash == token_hash(token), SessionToken.expires_at > now()
        )
    )
    if not session:
        raise HTTPException(401, 'Sign in to access your private workspaces.')
    user = db.get(User, session.user_id)
    if not user:
        raise HTTPException(401, 'Session no longer exists. Please sign in again.')
    return user


def sanitize_filename(name: str) -> str:
    name = name.replace('\\', '/').split('/')[-1]
    name = re.sub(r'[^\w. ()-]', '_', name)[:200].strip(' .')
    return name or 'document.txt'


class RateLimiter:
    """Process-local protection; production replicas require a shared gateway limit."""

    def __init__(self):
        self.windows: dict[str, deque] = defaultdict(deque)
        self.lock = threading.Lock()

    def check(self, key: str, maximum: int):
        with self.lock:
            current = time.monotonic()
            window = self.windows[key]
            while window and window[0] < current - 60:
                window.popleft()
            if len(window) >= maximum:
                raise HTTPException(
                    429,
                    'Too many requests. Please wait one minute and try again.',
                    headers={'Retry-After': '60'},
                )
            window.append(current)
            if len(self.windows) > 10000:
                self.windows = defaultdict(
                    deque, {k: v for k, v in self.windows.items() if v and v[-1] > current - 60}
                )


def validate_origin(request: Request, allowed: str) -> bool:
    origin = request.headers.get('origin')
    if request.headers.get('sec-fetch-site') == 'cross-site':
        return False
    if not origin:
        return True  # Non-browser clients; browsers send Origin on state-changing fetches.
    permitted = {item.strip() for item in allowed.split(',')}
    permitted.add(str(request.base_url).rstrip('/'))
    return origin in permitted and urlparse(origin).scheme in ('http', 'https')
