"""
工具调用缓存模块

为 MCP 工具提供缓存能力：
- TTL（Time-To-Live）过期机制
- LRU 淘汰策略
- 线程安全
- 缓存统计
"""

import hashlib
import json
import threading
import time
from collections import OrderedDict
from dataclasses import dataclass
from typing import Any, Optional


@dataclass
class CacheStats:
    """缓存统计"""
    hits: int = 0
    misses: int = 0
    evictions: int = 0
    total_requests: int = 0
    
    @property
    def hit_rate(self) -> float:
        """命中率"""
        if self.total_requests == 0:
            return 0.0
        return self.hits / self.total_requests


@dataclass
class CacheEntry:
    """缓存条目"""
    value: Any
    created_at: float
    last_accessed: float
    access_count: int = 0


class TTLCache:
    """TTL 缓存实现（LRU + 线程安全）"""
    
    def __init__(self, ttl_seconds: int = 300, max_size: int = 1000):
        self._ttl = ttl_seconds
        self._max_size = max_size
        self._cache: OrderedDict[str, CacheEntry] = OrderedDict()
        self._lock = threading.RLock()
        self._stats = CacheStats()
    
    def _make_key(self, *args, **kwargs) -> str:
        key_data = {"args": args, "kwargs": kwargs}
        key_str = json.dumps(key_data, sort_keys=True, default=str)
        return hashlib.sha256(key_str.encode()).hexdigest()[:32]
    
    def get(self, key: str) -> Optional[Any]:
        with self._lock:
            self._stats.total_requests += 1
            if key not in self._cache:
                self._stats.misses += 1
                return None
            
            entry = self._cache[key]
            if time.time() - entry.created_at > self._ttl:
                del self._cache[key]
                self._stats.misses += 1
                self._stats.evictions += 1
                return None
            
            entry.last_accessed = time.time()
            entry.access_count += 1
            self._cache.move_to_end(key)
            self._stats.hits += 1
            return entry.value
    
    def set(self, key: str, value: Any) -> None:
        with self._lock:
            now = time.time()
            if key in self._cache:
                self._cache[key].value = value
                self._cache[key].last_accessed = now
                self._cache.move_to_end(key)
                return
            
            while len(self._cache) >= self._max_size:
                self._cache.popitem(last=False)
                self._stats.evictions += 1
            
            self._cache[key] = CacheEntry(value=value, created_at=now, last_accessed=now)
    
    def invalidate(self, key: str) -> bool:
        with self._lock:
            if key in self._cache:
                del self._cache[key]
                return True
            return False
    
    def clear(self) -> int:
        with self._lock:
            count = len(self._cache)
            self._cache.clear()
            return count
    
    def cleanup_expired(self) -> int:
        with self._lock:
            now = time.time()
            expired_keys = [k for k, e in self._cache.items() if now - e.created_at > self._ttl]
            for k in expired_keys:
                del self._cache[k]
            self._stats.evictions += len(expired_keys)
            return len(expired_keys)
    
    @property
    def stats(self) -> CacheStats:
        with self._lock:
            return CacheStats(
                hits=self._stats.hits,
                misses=self._stats.misses,
                evictions=self._stats.evictions,
                total_requests=self._stats.total_requests,
            )
    
    def __len__(self) -> int:
        with self._lock:
            return len(self._cache)


class ToolCache:
    """工具调用缓存"""
    
    def __init__(self, ttl_seconds: int = 300, max_size: int = 1000, enabled: bool = True):
        self._cache = TTLCache(ttl_seconds=ttl_seconds, max_size=max_size)
        self._enabled = enabled
    
    @property
    def enabled(self) -> bool:
        return self._enabled
    
    @enabled.setter
    def enabled(self, value: bool) -> None:
        self._enabled = value
    
    def make_key(self, tool_name: str, arguments: dict) -> str:
        key_data = {"tool": tool_name, "args": arguments}
        key_str = json.dumps(key_data, sort_keys=True, default=str)
        return hashlib.sha256(key_str.encode()).hexdigest()[:32]
    
    def get(self, tool_name: str, arguments: dict) -> Optional[Any]:
        if not self._enabled:
            return None
        return self._cache.get(self.make_key(tool_name, arguments))
    
    def set(self, tool_name: str, arguments: dict, result: Any) -> None:
        if not self._enabled:
            return
        self._cache.set(self.make_key(tool_name, arguments), result)
    
    def invalidate(self, tool_name: str, arguments: dict) -> bool:
        return self._cache.invalidate(self.make_key(tool_name, arguments))
    
    def clear(self) -> int:
        return self._cache.clear()
    
    def cleanup(self) -> int:
        return self._cache.cleanup_expired()
    
    @property
    def stats(self) -> CacheStats:
        return self._cache.stats
    
    def __len__(self) -> int:
        return len(self._cache)


_global_tool_cache: Optional[ToolCache] = None


def get_tool_cache() -> ToolCache:
    """获取全局工具缓存实例"""
    global _global_tool_cache
    if _global_tool_cache is None:
        from .config import get_config
        cfg = get_config()
        _global_tool_cache = ToolCache(
            ttl_seconds=cfg.cache.ttl_seconds,
            max_size=cfg.cache.max_size,
            enabled=cfg.cache.enabled,
        )
    return _global_tool_cache


def clear_tool_cache() -> int:
    """清空全局工具缓存"""
    return get_tool_cache().clear()
