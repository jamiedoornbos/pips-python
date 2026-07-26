import os
from urllib.parse import urlparse

import dotenv

dotenv.load_dotenv()


def _parse_db_url():
    raw_url = os.environ['DATABASE_URL']
    sync_url = raw_url.replace('postgresql://', 'postgresql+psycopg2://')
    async_url = raw_url.replace('sslmode=require', '').replace('postgresql://', 'postgresql+asyncpg://')
    host = urlparse(raw_url).hostname
    connect_args = {'ssl': True} if host != 'localhost' else {}
    return async_url, sync_url, connect_args, {}


(
    DATABASE_URL,
    SYNC_DATABASE_URL,
    DATABASE_CONNECT_ARGS,
    SYNC_DATABASE_CONNECT_ARGS,
) = _parse_db_url()
