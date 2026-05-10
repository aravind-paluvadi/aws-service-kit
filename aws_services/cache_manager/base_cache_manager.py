"""File to handle the base cache manager"""
# Standard Library Imports
import logging
from threading import Lock, RLock
from abc import ABC, abstractmethod
from collections import OrderedDict
from typing import TypeVar, Callable, Generic, Optional, Any, Dict


logger = logging.getLogger(__name__)
T = TypeVar('T')
_MISSING = object()


class BaseCacheManager(ABC, Generic[T]):
    """
    Base cache manager class to handle the shared infrastructure for thread-safe caches,
    Thread-safe cache manager that allows concurrent access to cached values using
    double-checked locking pattern.
    - Uses a per-key lock to prevent redundant factory() calls under concurrency.
    """

    def __init__(self, max_size: Optional[int] = None) -> None:
        """
        Initialize the cache and lock in base cache manager

        Parameter:
        ---------
        max_size:
            Maximum number of entries in the cache. If None, the cache size is unlimited. LRU (Least Recently Used)
            entry is evicted when exceeded.
        """
        self._cache: OrderedDict[Any, Any] = OrderedDict()
        self._lock: RLock = RLock()
        self._inflight: Dict[Any, Lock] = {}
        self._max_size = max_size

    def __len__(self) -> int:
        """Give the current size of the cache. Thread safe."""
        with self._lock:
            return len(self._cache)

    @abstractmethod
    def get(self, key: Any) -> Optional[T]:
        """
        Get the value for the given key, or None if not present

        Parameter:
        ---------
            key:
                The key to look up in the cache
        """
        ...

    def delete(self, key: Any) -> None:
        """
        Delete the value for the given key if present

        Parameter:
        ---------
            key:
                The key to delete from the cache
        """
        with self._lock:
            self._cache.pop(key, None)

    def clear(self) -> None:
        """Thread safe full cache Clear. Useful for testing"""
        with self._lock:
            self._cache.clear()
            self._inflight.clear()

    def _evict_if_needed(self) -> None:
        """Evict the least recently used (LRU) entry if max_sized exceed. Must be called under _lock"""
        if self._max_size is not None and len(self._cache) >= self._max_size:
            lru_key = next(iter(self._cache))
            del self._cache[lru_key]
            logger.debug(f"Evicted LRU cache entry", extra= {"key": lru_key})

    def _cache_entry(
            self,
            key: Any,
            is_valid: Callable[[Any], bool],
            extract: Callable[[Any], T],
            log_msg: str = "str"
    ) -> Any:
        """
        Cache the entry and evict if needed. Must be called under _lock

        Parameters:
        ----------
            key:
                The key to look up in the cache
            is_valid:
                A function to check if the cache entry is still valid (e.g., not expired)
            extract:
                A function to extract the value from the cache entry
            log_msg:
                A log message to indicate the cache hit reason, with {key} as a placeholder for the cache key

        Returns:
        -------
            The extracted value if the cache entry is valid, or _MISSING if not present or invalid
        """
        if key in self._cache:
            entry = self._cache[key]
            if is_valid(entry):
                self._cache.move_to_end(key)
                if log_msg:
                    logger.debug(log_msg, extra={"key": key})
                return extract(entry)
        return _MISSING

    def _get_or_create_impl(
            self,
            key: Any,
            is_valid: Callable[[Any], bool],
            extract: Callable[[Any], T],
            factory: Callable[[], Any]
    ) -> T:
        """
        Get or create the cache entry for the given key. Must be called under _lock

        Parameters:
        ----------
            key:
                The key to look up in the cache
            is_valid:
                A function to check if the cache entry is still valid (e.g., not expired)
            extract:
                A function to extract the value from the cache entry
            factory:
                A function to create a new cache entry if not present or invalid

        Returns:
        -------
            Cache entry if the cache entry is valid, or _MISSING if not present
        """
        # -- Step 1: Fast path - check cache under global lock --
        # Most calls hit this path and return immediately without any heavy work.
        with self._lock:
            cache_value = self._cache_entry(key, is_valid, extract, "Cache hit")
            if cache_value is not _MISSING:
                return cache_value

            # -- Step 2: Cache miss - get or create a per-key lock --
            # Per-key lock ensures only ONE thread runs factory() for a given key.
            # Other keys are not blocked - they each have their own lock
            if key not in self._inflight:
                self._inflight[key] = Lock()
            key_lock = self._inflight[key]

        # -- Step 3: Acquire per-key lock --
        # If another thread is already creating this key, we wait here.
        with key_lock:
            # -- Step 4: Double-check - re-check cache after acquiring key lock --
            # While we were waiting on key_lock, another thread may have already called factory() and cached the value.
            # If so, we can return it immediately without calling factory() again.
            with self._lock:
                cache_value = self._cache_entry(key, is_valid, extract, "Another thread already cached value")
                if cache_value is not _MISSING:
                    return cache_value

            # -- Step 5: Slow path - call factory() OUTSIDE the global lock --
            # This is the expensive part (e.g., AWS calls, API calls). Running it outside _lock ensures
            # other keys are not blocked during this I/O operation.
            try:
                new_entry = factory()
            except Exception:
                # Clean up the per-key lock so future requests can retry
                with self._lock:
                    self._inflight.pop(key, None)
                raise

            # -- Step 6: Store result under gloabl lock and return --
            # Evict the oldet entry if max_size exceeded, store the new entry, and clean up the
            # per-key inflight lock (no longer needed).
            with self._lock:
                self._evict_if_needed()
                self._cache[key] = new_entry
                self._inflight.pop(key, None)
                logger.debug("Cached new value", extra={"key": key})
                return extract(new_entry)
