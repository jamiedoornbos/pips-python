import os
from urllib.parse import urlparse

import dotenv

dotenv.load_dotenv()


def _parse_db_url():
    raw_url = os.environ['DATABASE_URL']
    url = raw_url.replace('postgresql://', 'postgresql+asyncpg://').replace('sslmode=require', '')
    host = urlparse(raw_url).hostname
    connect_args = {'ssl': True} if host != 'localhost' else {}
    return url, connect_args


DATABASE_URL, DATABASE_CONNECT_ARGS = _parse_db_url()
