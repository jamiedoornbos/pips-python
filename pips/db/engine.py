from sqlalchemy import create_engine
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.orm import sessionmaker

from pips.config import DATABASE_CONNECT_ARGS, DATABASE_URL, SYNC_DATABASE_CONNECT_ARGS, SYNC_DATABASE_URL


def _create_session_factories():
    shared_args = dict(
        pool_size=10,
        max_overflow=20,
        pool_timeout=30,
        pool_recycle=1800,
        pool_pre_ping=True,
    )
    async_engine = create_async_engine(DATABASE_URL, **shared_args, connect_args=DATABASE_CONNECT_ARGS)
    sync_engine = create_engine(SYNC_DATABASE_URL, **shared_args, connect_args=SYNC_DATABASE_CONNECT_ARGS)
    return (
        async_sessionmaker(async_engine, expire_on_commit=False),
        sessionmaker(sync_engine, expire_on_commit=False),
    )


async_session, sync_session = _create_session_factories()
