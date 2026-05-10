"""
Initialization file for the cache manager package. This file imports the main cache manager classes and
makes them available for import at the package level.
- This allows users to import the cache manager classes directly from the cache_manager package instead of having to
specify the individual module they are located in.

EXAMPLE:
    Instead of importing ThreadCacheManager from thread_cache_manager, users can import it directly from cache_manager.
This promotes cleaner and more convenient imports for users of the package.
"""
# cache_manager/__init__.py
from .base_cache_manager import BaseCacheManager
from .thread_cache_manager import ThreadCacheManager
from .ttl_thread_cache_mager import TTLThreadCacheManager

__all__ = ['BaseCacheManager', 'ThreadCacheManager', 'TTLThreadCacheManager']
