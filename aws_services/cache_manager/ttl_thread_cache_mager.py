"""File for time to live (TTL) Thread Cache Manager"""
# Standard Library Imports
import logging
from time import time
from typing import TypeVar, Callable, Optional, Any, Tuple


# Local Imports
from .base_cache_manager import BaseCacheManager, _MISSING


logger = logging.getLogger(__name__)
T = TypeVar("T")


class TTLThreadCacheManager(BaseCacheManager[T]):
    """
    TTL Thread Cache Manager class with TTL expiry and early refresh window. Each cache entry is stored as a tuple
    of (value, expiry_time) and is considered valid if the current time is less than the expiry_time.
    - An optional early refresh window can be configured to trigger a background refresh before the actual expiry.
    """

    def __init__(self, early_refresh_secs: int = 300, max_size: Optional[int] = None) -> None:
        """
        Initialize the TTL Thread Cache Manager with cache and lock.
        Parameters:
        ----------
            early_refresh_secs:
                Seconds before the expiry to treat an entry as stale. Defaults to 300.
            max_size:
                Optional maximum size of the cache. LRU entry is evicted when exceeded.
        """
        super().__init__(max_size)
        self._early_refresh_secs = early_refresh_secs

    def get(self, key: Any) -> Optional[T]:
        """
        Get the value for the given key if not expired, thread-safe read
        Parameter:
        ---------
            key:
                The key to look up in the cache
        """
        with self._lock:
            result = self._cache_entry(key, self._is_valid_entry, lambda e: e[0], "Cache get hit")
            return None if result is _MISSING else result

    def set(self, key: Any, value: T, expires_at: float) -> None:
        """
        Set the value for the explicit Unix timestamp, thread-safe write

        Parameter:
        ---------
            key:
                The key to look up in the cache
            expiry_at:
                The expiry time of the entry
        """
        with self._lock:
            self._evict_if_needed()
            self._cache[key] = (value,expires_at)

    def get_or_create_expiry(self, key: Any, factory: Callable[[], Tuple[T, float]]) -> Optional[T]:
        """
        Return cached value for the given key, or call factory to create a new one. factory() is called outside
        the lock to avoid blocking other threads

        Parameter:
        ---------
            key:
                The key to look up in the cache
            factory:
                Callable that creates the value if not cached. Called at most once per key.

        Return:
        ------
            Cached value or newly created value for the given key.
        """
        return self._get_or_create_impl(
            key,
            is_valid=self._is_valid_entry,
            extract=lambda e: e[0],
            factory=factory
        )

    def _is_valid_entry(self, entry: Tuple[T, float]) -> bool:
        """
        Check if the given entry is valid, return true if the entry is still valid
        (Outside the early-refresh window).

        Parameter:
        ---------
            entry:
                Entry to be checked with expiry time.
        Return:
        ------
            Boolean, True if the entry is valid, False otherwise
        """
        _, expiry_time = entry
        return time() < (expiry_time - self._early_refresh_secs)
