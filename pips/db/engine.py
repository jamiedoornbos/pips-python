from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from pips.config import DATABASE_URL, DATABASE_CONNECT_ARGS

engine = create_async_engine(
    DATABASE_URL,
    pool_size=10,
    max_overflow=20,
    pool_timeout=30,
    pool_recycle=1800,
    connect_args=DATABASE_CONNECT_ARGS,
)

async_session = async_sessionmaker(engine, expire_on_commit=False)
