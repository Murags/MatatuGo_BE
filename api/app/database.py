from sqlalchemy import create_engine
from sqlalchemy.exc import OperationalError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker
from .config import settings
import alembic.config

DATABASE_URL = str(settings.database_url)

class Base(DeclarativeBase):
    pass

class DatabaseSessionManager:
    def __init__(self):
        base_url = str(DATABASE_URL)
        sync_url = base_url.replace("postgresql://", "postgresql+psycopg2://")
        self.engine = create_engine(sync_url)

        async_url = base_url.replace("postgresql://", "postgresql+asyncpg://")
        self.async_engine = create_async_engine(async_url)

        self.SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=self.engine)
        self.AsyncSessionLocal = async_sessionmaker(self.async_engine, class_=AsyncSession, expire_on_commit=False)

    def get_db(self):
        db = self.SessionLocal()
        try:
            yield db
        finally:
            db.close()

    async def get_async_db(self):
        async with self.AsyncSessionLocal() as session:
            try:
                yield session
                await session.commit()
            except Exception:
                await session.rollback()
                raise

class AlembicManager:
    def __init__(self):
        import os
        current_dir = os.path.dirname(os.path.abspath(__file__))
        api_dir = os.path.dirname(current_dir)
        alembic_ini_path = os.path.join(api_dir, "alembic.ini")

        self.alembic_config = alembic.config.Config(alembic_ini_path)
        self.alembic_config.set_main_option("script_location", os.path.join(api_dir, "alembic"))

        # Set the database URL for migrations (use psycopg2 for sync migrations)
        migration_url = str(DATABASE_URL).replace("postgresql://", "postgresql+psycopg2://")
        self.alembic_config.set_main_option("sqlalchemy.url", migration_url)

    def create_database(self):
        Base.metadata.create_all(bind=database_session_manager.engine)

    def run_migrations(self):
        try:
            # Base.metadata.drop_all(bind=database_session_manager.engine)
            alembic.command.upgrade(self.alembic_config, "head")
            alembic.command.stamp(self.alembic_config, "head")
        except OperationalError:
            self.create_database()
            self.run_migrations()
        except Exception as e:
            print(f"Error running migrations: {e}")
            raise e

database_session_manager = DatabaseSessionManager()
alembic_manager = AlembicManager()
