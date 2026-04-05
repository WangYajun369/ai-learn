"""
数据库连接池模块

提供 SQLite 连接池，支持：
- 连接复用，避免频繁创建/销毁连接
- 线程安全
- 自动清理空闲连接
- WAL 模式优化
"""

import sqlite3
import threading
import time
from pathlib import Path
from typing import Generator, Optional
from contextlib import contextmanager


class ConnectionPool:
    """
    SQLite 连接池
    
    注意：SQLite 的连接池比较特殊，因为 SQLite 是进程内数据库，
    这里实现的是线程级连接池，共享一个连接对象。
    对于真正的高并发场景，建议使用连接队列 + 线程本地连接。
    """
    
    def __init__(
        self,
        db_path: Path,
        pool_size: int = 5,
        timeout: float = 30.0,
        wal_mode: bool = True,
    ):
        self.db_path = Path(db_path)
        self._pool_size = pool_size
        self._timeout = timeout
        self._wal_mode = wal_mode
        
        # 连接管理
        self._local = threading.local()
        self._lock = threading.Lock()
        self._last_used: dict[int, float] = {}  # thread_id -> last_used timestamp
        
        # 创建目录
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        
        # 初始化连接
        self._init_connection()
    
    def _init_connection(self) -> sqlite3.Connection:
        """创建新的数据库连接"""
        conn = sqlite3.connect(
            str(self.db_path),
            timeout=self._timeout,
            check_same_thread=False,  # 允许跨线程使用
        )
        conn.row_factory = sqlite3.Row
        
        # WAL 模式提升并发性能
        if self._wal_mode:
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("PRAGMA synchronous=NORMAL")
        
        # 外键约束
        conn.execute("PRAGMA foreign_keys=ON")
        
        return conn
    
    def get_connection(self) -> sqlite3.Connection:
        """获取线程本地的数据库连接"""
        thread_id = threading.current_thread().ident
        
        # 检查线程本地是否有连接
        if hasattr(self._local, 'conn') and self._local.conn:
            self._last_used[thread_id] = time.time()
            return self._local.conn
        
        # 创建新连接
        with self._lock:
            conn = self._init_connection()
            self._local.conn = conn
            self._last_used[thread_id] = time.time()
            return conn
    
    @contextmanager
    def cursor(self) -> Generator[sqlite3.Cursor, None, None]:
        """
        获取游标的上下文管理器
        
        用法：
            with pool.cursor() as c:
                c.execute("SELECT * FROM ...")
        """
        thread_id = threading.current_thread().ident
        conn = self.get_connection()
        cursor = conn.cursor()
        
        try:
            yield cursor
            conn.commit()
        except Exception as e:
            conn.rollback()
            raise RuntimeError(f"数据库操作失败: {e}") from e
        finally:
            cursor.close()
            self._last_used[thread_id] = time.time()
    
    @contextmanager
    def transaction(self) -> Generator[sqlite3.Connection, None, None]:
        """
        获取事务上下文的上下文管理器
        
        用法：
            with pool.transaction() as conn:
                conn.execute("INSERT ...")
                conn.execute("UPDATE ...")
            # 自动提交或回滚
        """
        conn = self.get_connection()
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
    
    def close_all(self) -> None:
        """关闭所有连接"""
        if hasattr(self._local, 'conn') and self._local.conn:
            self._local.conn.close()
            self._local.conn = None
    
    def execute(
        self,
        sql: str,
        params: tuple = (),
    ) -> list[sqlite3.Row]:
        """执行查询并返回结果"""
        with self.cursor() as c:
            c.execute(sql, params)
            return c.fetchall()
    
    def execute_many(self, sql: str, params_list: list[tuple]) -> int:
        """批量执行"""
        with self.transaction() as conn:
            cursor = conn.cursor()
            cursor.executemany(sql, params_list)
            return cursor.rowcount
    
    def execute_script(self, script: str) -> None:
        """执行 SQL 脚本"""
        with self.transaction() as conn:
            conn.executescript(script)


class MultiDBPool:
    """
    多数据库连接池管理器
    
    统一管理多个数据库的连接池：
    - sales.db（只读）
    - conversations.db（读写）
    - memory_db（ChromaDB）
    - user_profile.db（读写）
    """
    
    def __init__(self, config=None):
        self._pools: dict[str, ConnectionPool] = {}
        self._config = config or {}
        
        # 获取数据库路径配置
        from .config import get_config
        cfg = get_config()
        
        # 初始化 sales.db 连接池（只读优化）
        self._pools["sales"] = ConnectionPool(
            cfg.database.sales_db,
            pool_size=cfg.database.pool_size,
            timeout=cfg.database.pool_timeout,
        )
        
        # 初始化 conversations.db 连接池
        self._pools["conversations"] = ConnectionPool(
            cfg.database.conversations_db,
            pool_size=cfg.database.pool_size,
            timeout=cfg.database.pool_timeout,
        )
    
    def get_pool(self, name: str) -> Optional[ConnectionPool]:
        """获取指定名称的连接池"""
        return self._pools.get(name)
    
    def get_sales_pool(self) -> ConnectionPool:
        """获取销售数据库连接池"""
        return self._pools["sales"]
    
    def get_conversations_pool(self) -> ConnectionPool:
        """获取会话记录数据库连接池"""
        return self._pools["conversations"]
    
    def close_all(self) -> None:
        """关闭所有连接池"""
        for pool in self._pools.values():
            pool.close_all()
        self._pools.clear()


# 全局连接池实例
_global_pool: Optional[MultiDBPool] = None


def get_db_pool() -> MultiDBPool:
    """获取全局数据库连接池（单例）"""
    global _global_pool
    if _global_pool is None:
        _global_pool = MultiDBPool()
    return _global_pool


def close_db_pool() -> None:
    """关闭全局数据库连接池"""
    global _global_pool
    if _global_pool:
        _global_pool.close_all()
        _global_pool = None
