"""
数据库会话管理
"""

from contextlib import contextmanager
from typing import Generator
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import sessionmaker, Session
from sqlalchemy.exc import SQLAlchemyError
import os
import logging

from .models import Base

logger = logging.getLogger(__name__)


def _build_sqlalchemy_url(database_url: str) -> str:
    if database_url.startswith("postgresql://"):
        return "postgresql+psycopg://" + database_url[len("postgresql://"):]
    if database_url.startswith("postgres://"):
        return "postgresql+psycopg://" + database_url[len("postgres://"):]
    return database_url


class DatabaseSessionManager:
    """数据库会话管理器"""

    def __init__(self, database_url: str = None):
        if database_url is None:
            env_url = os.environ.get("APP_DATABASE_URL") or os.environ.get("DATABASE_URL")
            if env_url:
                database_url = env_url
            else:
                # 优先使用 APP_DATA_DIR 环境变量（PyInstaller 打包后由 webui.py 设置）
                data_dir = os.environ.get('APP_DATA_DIR') or os.path.join(
                    os.path.dirname(os.path.dirname(os.path.dirname(__file__))),
                    'data'
                )
                db_path = os.path.join(data_dir, 'database.db')
                # 确保目录存在
                os.makedirs(data_dir, exist_ok=True)
                database_url = f"sqlite:///{db_path}"

        self.database_url = _build_sqlalchemy_url(database_url)
        self.engine = create_engine(
            self.database_url,
            connect_args={"check_same_thread": False} if self.database_url.startswith("sqlite") else {},
            echo=False,  # 设置为 True 可以查看所有 SQL 语句
            pool_pre_ping=True  # 连接池预检查
        )
        self.SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=self.engine)

    def get_db(self) -> Generator[Session, None, None]:
        """
        获取数据库会话的上下文管理器
        使用示例:
            with get_db() as db:
                # 使用 db 进行数据库操作
                pass
        """
        db = self.SessionLocal()
        try:
            yield db
        finally:
            db.close()

    @contextmanager
    def session_scope(self) -> Generator[Session, None, None]:
        """
        事务作用域上下文管理器
        使用示例:
            with session_scope() as session:
                # 数据库操作
                pass
        """
        session = self.SessionLocal()
        try:
            yield session
            session.commit()
        except Exception as e:
            session.rollback()
            raise e
        finally:
            session.close()

    def create_tables(self):
        """创建所有表"""
        Base.metadata.create_all(bind=self.engine)

    def drop_tables(self):
        """删除所有表（谨慎使用）"""
        Base.metadata.drop_all(bind=self.engine)

    def migrate_tables(self):
        """
        数据库迁移 - 添加缺失的列
        用于在不删除数据的情况下更新表结构
        """
        # 需要检查和添加的新列
        migrations = [
            # (表名, 列名, 各数据库类型定义)
            ("accounts", "cpa_uploaded", {
                "default": "BOOLEAN DEFAULT FALSE",
                "sqlite": "BOOLEAN DEFAULT 0",
            }),
            ("accounts", "cpa_uploaded_at", {
                "default": "TIMESTAMP",
                "sqlite": "DATETIME",
            }),
            ("accounts", "source", {
                "default": "VARCHAR(20) DEFAULT 'register'",
            }),
            ("accounts", "subscription_type", {
                "default": "VARCHAR(20)",
            }),
            ("accounts", "subscription_at", {
                "default": "TIMESTAMP",
                "sqlite": "DATETIME",
            }),
            ("accounts", "cookies", {
                "default": "TEXT",
            }),
            ("proxies", "is_default", {
                "default": "BOOLEAN DEFAULT FALSE",
                "sqlite": "BOOLEAN DEFAULT 0",
            }),
            ("sub2api_services", "group_ids", {
                "default": "TEXT DEFAULT '[]'",
            }),
            ("sub2api_services", "proxy_id", {
                "default": "INTEGER",
            }),
            ("cpa_services", "include_proxy_url", {
                "default": "BOOLEAN DEFAULT FALSE",
                "sqlite": "BOOLEAN DEFAULT 0",
            }),
            ("sub2api_scheduler_history", "total_accounts_after_scan", {
                "default": "INTEGER",
            }),
        ]

        # 确保新表存在（create_tables 已处理，此处兜底）
        Base.metadata.create_all(bind=self.engine)

        dialect_name = self.engine.dialect.name
        inspector = inspect(self.engine)

        with self.engine.connect() as conn:
            # 数据迁移：将旧的 custom_domain 记录统一为 moe_mail
            try:
                conn.execute(text("UPDATE email_services SET service_type='moe_mail' WHERE service_type='custom_domain'"))
                conn.execute(text("UPDATE accounts SET email_service='moe_mail' WHERE email_service='custom_domain'"))
                conn.commit()
            except Exception as e:
                logger.warning(f"迁移 custom_domain -> moe_mail 时出错: {e}")

            for table_name, column_name, column_types in migrations:
                try:
                    existing_columns = {col["name"] for col in inspector.get_columns(table_name)}
                    if column_name not in existing_columns:
                        column_type = column_types.get(dialect_name) or column_types["default"]
                        logger.info(f"添加列 {table_name}.{column_name}")
                        conn.execute(text(
                            f"ALTER TABLE {table_name} ADD COLUMN {column_name} {column_type}"
                        ))
                        conn.commit()
                        logger.info(f"成功添加列 {table_name}.{column_name}")

                    if table_name == "sub2api_services" and column_name == "group_ids":
                        conn.execute(text(
                            "UPDATE sub2api_services SET group_ids = '[]' "
                            "WHERE group_ids IS NULL OR group_ids = ''"
                        ))
                        conn.commit()
                except Exception as e:
                    logger.warning(f"迁移列 {table_name}.{column_name} 时出错: {e}")


# 全局数据库会话管理器实例
_db_manager: DatabaseSessionManager = None


def init_database(database_url: str = None) -> DatabaseSessionManager:
    """
    初始化数据库会话管理器
    """
    global _db_manager
    if _db_manager is None:
        _db_manager = DatabaseSessionManager(database_url)
        _db_manager.create_tables()
        # 执行数据库迁移
        _db_manager.migrate_tables()
    return _db_manager


def get_session_manager() -> DatabaseSessionManager:
    """
    获取数据库会话管理器
    """
    if _db_manager is None:
        raise RuntimeError("数据库未初始化，请先调用 init_database()")
    return _db_manager


@contextmanager
def get_db() -> Generator[Session, None, None]:
    """
    获取数据库会话的快捷函数
    """
    manager = get_session_manager()
    db = manager.SessionLocal()
    try:
        yield db
    finally:
        db.close()
