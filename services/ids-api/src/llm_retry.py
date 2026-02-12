"""
Retry Logic with Exponential Backoff
Handles transient failures in LLM API calls.

This module provides:
1. Exponential backoff retry decorator
2. Rate limit handling
3. Transient error detection
"""

import asyncio
import functools
import logging
import random
import time
from typing import Callable, Optional, Set, Type, Union
from dataclasses import dataclass

logger = logging.getLogger(__name__)


# =============================================================================
# RETRYABLE EXCEPTIONS
# =============================================================================

RETRYABLE_STATUS_CODES: Set[int] = {
    408,  # Request Timeout
    429,  # Too Many Requests (Rate Limited)
    500,  # Internal Server Error
    502,  # Bad Gateway
    503,  # Service Unavailable
    504,  # Gateway Timeout
}

RETRYABLE_EXCEPTIONS: tuple = (
    ConnectionError,
    TimeoutError,
    asyncio.TimeoutError,
)


# =============================================================================
# RETRY CONFIGURATION
# =============================================================================

@dataclass
class RetryConfig:
    """Configuration for retry behavior"""
    max_retries: int = 3
    base_delay: float = 1.0  # seconds
    max_delay: float = 60.0  # seconds
    exponential_base: float = 2.0
    jitter: bool = True  # Add randomness to prevent thundering herd
    
    def calculate_delay(self, attempt: int) -> float:
        """Calculate delay for given attempt number"""
        delay = self.base_delay * (self.exponential_base ** attempt)
        delay = min(delay, self.max_delay)
        
        if self.jitter:
            # Add random jitter up to 25% of delay
            jitter = delay * 0.25 * random.random()
            delay += jitter
        
        return delay


# =============================================================================
# SYNC RETRY DECORATOR
# =============================================================================

def retry_with_backoff(
    max_retries: int = 3,
    base_delay: float = 1.0,
    max_delay: float = 60.0,
    retryable_exceptions: tuple = RETRYABLE_EXCEPTIONS,
    retryable_status_codes: Optional[Set[int]] = None,
    on_retry: Optional[Callable[[Exception, int], None]] = None,
):
    """
    Decorator for retry with exponential backoff (sync version).
    
    Args:
        max_retries: Maximum number of retry attempts
        base_delay: Initial delay between retries (seconds)
        max_delay: Maximum delay cap (seconds)
        retryable_exceptions: Tuple of exceptions to retry on
        retryable_status_codes: Set of HTTP status codes to retry on
        on_retry: Optional callback(exception, attempt) called on each retry
        
    Usage:
        @retry_with_backoff(max_retries=3)
        def call_api():
            response = requests.get(url)
            response.raise_for_status()
            return response.json()
    """
    if retryable_status_codes is None:
        retryable_status_codes = RETRYABLE_STATUS_CODES
    
    config = RetryConfig(
        max_retries=max_retries,
        base_delay=base_delay,
        max_delay=max_delay,
    )
    
    def decorator(func: Callable):
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            last_exception = None
            
            for attempt in range(max_retries + 1):
                try:
                    return func(*args, **kwargs)
                    
                except retryable_exceptions as e:
                    last_exception = e
                    
                    if attempt < max_retries:
                        delay = config.calculate_delay(attempt)
                        logger.warning(
                            f"Retry {attempt + 1}/{max_retries} for {func.__name__} "
                            f"after {e.__class__.__name__}: {e}. "
                            f"Waiting {delay:.1f}s..."
                        )
                        
                        if on_retry:
                            on_retry(e, attempt + 1)
                        
                        time.sleep(delay)
                    else:
                        logger.error(
                            f"Max retries ({max_retries}) exceeded for {func.__name__}"
                        )
                        raise
                        
                except Exception as e:
                    # Check if it's an HTTP error with retryable status code
                    status_code = getattr(e, 'status_code', None) or \
                                 getattr(getattr(e, 'response', None), 'status_code', None)
                    
                    if status_code in retryable_status_codes:
                        last_exception = e
                        
                        if attempt < max_retries:
                            # Special handling for rate limits (429)
                            if status_code == 429:
                                # Check for Retry-After header
                                retry_after = _get_retry_after(e)
                                delay = retry_after if retry_after else config.calculate_delay(attempt)
                                delay = min(delay, max_delay)
                            else:
                                delay = config.calculate_delay(attempt)
                            
                            logger.warning(
                                f"Retry {attempt + 1}/{max_retries} for {func.__name__} "
                                f"after HTTP {status_code}. Waiting {delay:.1f}s..."
                            )
                            
                            if on_retry:
                                on_retry(e, attempt + 1)
                            
                            time.sleep(delay)
                        else:
                            raise
                    else:
                        # Non-retryable error
                        raise
            
            # Should not reach here, but raise last exception if we do
            if last_exception:
                raise last_exception
                
        return wrapper
    return decorator


# =============================================================================
# ASYNC RETRY DECORATOR
# =============================================================================

def async_retry_with_backoff(
    max_retries: int = 3,
    base_delay: float = 1.0,
    max_delay: float = 60.0,
    retryable_exceptions: tuple = RETRYABLE_EXCEPTIONS,
    retryable_status_codes: Optional[Set[int]] = None,
    on_retry: Optional[Callable[[Exception, int], None]] = None,
):
    """
    Decorator for retry with exponential backoff (async version).
    
    Usage:
        @async_retry_with_backoff(max_retries=3)
        async def call_api():
            async with httpx.AsyncClient() as client:
                response = await client.get(url)
                return response.json()
    """
    if retryable_status_codes is None:
        retryable_status_codes = RETRYABLE_STATUS_CODES
    
    config = RetryConfig(
        max_retries=max_retries,
        base_delay=base_delay,
        max_delay=max_delay,
    )
    
    def decorator(func: Callable):
        @functools.wraps(func)
        async def wrapper(*args, **kwargs):
            last_exception = None
            
            for attempt in range(max_retries + 1):
                try:
                    return await func(*args, **kwargs)
                    
                except retryable_exceptions as e:
                    last_exception = e
                    
                    if attempt < max_retries:
                        delay = config.calculate_delay(attempt)
                        logger.warning(
                            f"Async retry {attempt + 1}/{max_retries} for {func.__name__} "
                            f"after {e.__class__.__name__}. Waiting {delay:.1f}s..."
                        )
                        
                        if on_retry:
                            on_retry(e, attempt + 1)
                        
                        await asyncio.sleep(delay)
                    else:
                        raise
                        
                except Exception as e:
                    status_code = getattr(e, 'status_code', None) or \
                                 getattr(getattr(e, 'response', None), 'status_code', None)
                    
                    if status_code in retryable_status_codes:
                        last_exception = e
                        
                        if attempt < max_retries:
                            if status_code == 429:
                                retry_after = _get_retry_after(e)
                                delay = retry_after if retry_after else config.calculate_delay(attempt)
                                delay = min(delay, max_delay)
                            else:
                                delay = config.calculate_delay(attempt)
                            
                            logger.warning(
                                f"Async retry {attempt + 1}/{max_retries} for {func.__name__} "
                                f"after HTTP {status_code}. Waiting {delay:.1f}s..."
                            )
                            
                            if on_retry:
                                on_retry(e, attempt + 1)
                            
                            await asyncio.sleep(delay)
                        else:
                            raise
                    else:
                        raise
            
            if last_exception:
                raise last_exception
                
        return wrapper
    return decorator


# =============================================================================
# HELPER FUNCTIONS
# =============================================================================

def _get_retry_after(exception: Exception) -> Optional[float]:
    """
    Extract Retry-After header value from exception/response.
    
    Returns:
        Delay in seconds, or None if not found
    """
    try:
        response = getattr(exception, 'response', None)
        if response:
            retry_after = response.headers.get('Retry-After')
            if retry_after:
                # Could be seconds or HTTP-date
                try:
                    return float(retry_after)
                except ValueError:
                    # Parse HTTP-date format if needed
                    pass
    except Exception:
        pass
    
    return None


def is_retryable_error(exception: Exception) -> bool:
    """
    Check if an exception is retryable.
    
    Args:
        exception: The exception to check
        
    Returns:
        True if the error is transient and worth retrying
    """
    if isinstance(exception, RETRYABLE_EXCEPTIONS):
        return True
    
    status_code = getattr(exception, 'status_code', None) or \
                 getattr(getattr(exception, 'response', None), 'status_code', None)
    
    return status_code in RETRYABLE_STATUS_CODES


# =============================================================================
# RATE LIMITER
# =============================================================================

class RateLimiter:
    """
    Simple rate limiter using token bucket algorithm.
    
    Usage:
        limiter = RateLimiter(requests_per_minute=60)
        
        if limiter.acquire():
            make_api_call()
        else:
            # Rate limited, wait
            await asyncio.sleep(limiter.retry_after)
    """
    
    def __init__(
        self,
        requests_per_minute: int = 60,
        burst_size: Optional[int] = None,
    ):
        self.rate = requests_per_minute / 60.0  # tokens per second
        self.capacity = burst_size or requests_per_minute
        self.tokens = float(self.capacity)
        self.last_update = time.monotonic()
        self._lock = asyncio.Lock() if asyncio.get_event_loop().is_running() else None
    
    def _refill(self):
        """Refill tokens based on elapsed time"""
        now = time.monotonic()
        elapsed = now - self.last_update
        self.tokens = min(self.capacity, self.tokens + elapsed * self.rate)
        self.last_update = now
    
    def acquire(self, tokens: int = 1) -> bool:
        """
        Try to acquire tokens.
        
        Returns:
            True if tokens acquired, False if rate limited
        """
        self._refill()
        
        if self.tokens >= tokens:
            self.tokens -= tokens
            return True
        return False
    
    @property
    def retry_after(self) -> float:
        """Seconds until a token is available"""
        self._refill()
        if self.tokens >= 1:
            return 0.0
        return (1 - self.tokens) / self.rate
    
    async def acquire_async(self, tokens: int = 1) -> bool:
        """Thread-safe async acquire"""
        if self._lock:
            async with self._lock:
                return self.acquire(tokens)
        return self.acquire(tokens)
