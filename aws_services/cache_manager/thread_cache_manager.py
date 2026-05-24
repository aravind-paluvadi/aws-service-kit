"""File for Thread Cache Manager"""
from __future__ import annotations

# Standard Library Imports
import logging
from typing import Callable, Any, override

# Local Imports
from .base_cache_manager import _BaseCacheManager

logger = logging.getLogger(__name__)



class ThreadCacheManager[T](_BaseCacheManager[T]):
    """
    ThreadCacheManager is a thread-safe cache manager that allows concurrent
    access to cached values using double-checked locking pattern.
    Uses a per-key lock to prevent redundant factory() calls under concurrency.
    """

    @override
    def get(self, key: Any) -> T | None:
        """
        Get the value for the given key, thread-safe read

        Parameter:
        ---------
            key:
                The key to look up in the cache
        """
        with self._lock:
            return self._cache.get(key)

    def set(self, key: Any, value: T) -> None:
        """
        Set the value for the given key, thread-safe write

        Parameter:
        ---------
            key:
                The key to look up in the cache
            value:
                The value to set the key to
        """
        with self._lock:
            self._evict_if_needed(key)
            self._cache[key] = value

    def get_or_create(self, key: Any, factory: Callable[[], T]) -> T:
        """
        Get the value for the given key, or create it using the factory if not present.
        One thread will call factory() per key; others wait for the result.

        Parameters:
        ----------
            key:
                The key to retrieve or create the value for.
            factory:
                A callable that produces the value if it's not already cached.
                Called at most once per key.

        Returns:
        -------
            The cached or newly created value for the given key.
        """
        return self._get_or_create_impl(
            key,
            is_valid=lambda entry: True,   # No expiry - always valid
            extract=lambda entry: entry,   # Entry is the value
            factory=factory
        )
