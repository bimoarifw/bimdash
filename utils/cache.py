# Thread-safe caching using cachelib
import time
from functools import wraps
from cachelib import FileSystemCache

cache = FileSystemCache('cache_dir', threshold=500)
CACHE_DURATION = 2  # seconds

def cached(duration=CACHE_DURATION):
    """Thread-safe cache decorator for functions"""
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            cache_key = f"{func.__name__}_{str(args)}_{str(kwargs)}"
            
            cached_result = cache.get(cache_key)
            if cached_result is not None:
                return cached_result

            result = func(*args, **kwargs)
            cache.set(cache_key, result, timeout=duration)
            return result
        return wrapper
    return decorator