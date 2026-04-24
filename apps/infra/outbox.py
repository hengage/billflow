"""
Reusable Outbox Drainer framework.

Implements the 'job drain' pattern from Brandur:
https://brandur.org/job-drain

Usage:
    def enqueue_notification(entry):
        payload = entry.payload
        send_task.delay(**payload)
    
    drainer = OutboxDrainer(
        domain='notifications',
        batch_size=50,
        enqueue_func=enqueue_notification,
        lock_key='outbox:drain:notifications:lock',
        lock_timeout_seconds=300,
    )
    drainer.drain()
"""
import logging
import random
import time
import uuid
from datetime import timedelta
from typing import Callable, List, Optional

from django.db import transaction
from django.utils import timezone
from django_redis import get_redis_connection

from .models import Outbox

logger = logging.getLogger(__name__)

# Lua script for atomic check-and-delete (prevents deleting another process's lock)
# Only delete if the value matches our unique token
LOCK_RELEASE_SCRIPT = """
if redis.call("get", KEYS[1]) == ARGV[1] then
    return redis.call("del", KEYS[1])
else
    return 0
end
"""

# Default empty queue backoff - exponential to reduce DB load when idle
# Max 60s with jitter to prevent thundering herd across multiple drainers
DEFAULT_EMPTY_BACKOFF_SECONDS = [2, 5, 10, 20, 30, 45, 60]

# Default lock timeout (3 minutes) - covers max backoff + processing
DEFAULT_LOCK_TIMEOUT_SECONDS = 180


class OutboxDrainer:
    """
    Domain-specific outbox drainer.
    
    Polls outbox for pending entries, fans out to Celery workers,
    and tracks status. Designed for exactly-once processing with
    fault tolerance and observability.
    
    Each domain instantiates its own drainer with appropriate:
    - batch_size (smaller for external APIs, larger for DB operations)
    - enqueue_func (callback to enqueue domain-specific Celery task)
    - lock_key (unique per domain to prevent cross-domain conflicts)
    """
    
    def __init__(
        self,
        domain: str,
        batch_size: int,
        enqueue_func: Callable[[Outbox], None],
        lock_key: str,
        lock_timeout_seconds: int = DEFAULT_LOCK_TIMEOUT_SECONDS,
        empty_backoff_seconds: Optional[List[int]] = None,
    ):
        """
        Initialize drainer for a specific domain.
        
        Args:
            domain: Domain identifier (e.g., 'notifications', 'subscriptions')
            batch_size: Number of entries to fetch per batch
            enqueue_func: Callback function(entry) to enqueue to Celery
            lock_key: Redis key for distributed lock (unique per domain)
            lock_timeout_seconds: Lock expiry time (default: 5 min)
            empty_backoff_seconds: Backoff intervals when queue empty
        """
        self.domain = domain
        self.batch_size = batch_size
        self.enqueue_func = enqueue_func
        self.lock_key = lock_key
        self.lock_timeout_seconds = lock_timeout_seconds
        self.empty_backoff_seconds = empty_backoff_seconds or DEFAULT_EMPTY_BACKOFF_SECONDS
    
    def drain(self) -> dict:
        """
        Poll outbox for pending jobs and enqueue to Celery.
        
        Only one drainer per domain runs at a time (enforced by Redis lock).
        
        Returns:
            dict: {processed: int, skipped: bool, empty: bool}
        """
        redis = get_redis_connection('default')
        
        # Generate unique token - prevents accidentally deleting another process's lock
        lock_token = str(uuid.uuid4())
        
        # Acquire distributed lock - atomic check-and-set
        lock_acquired = redis.set(
            self.lock_key, 
            lock_token, 
            nx=True, 
            ex=self.lock_timeout_seconds
        )
        if not lock_acquired:
            logger.debug(f'[{self.domain}] Lock held by another drainer, skipping')
            return {'processed': 0, 'skipped': True, 'empty': False}
        
        logger.debug(f'[{self.domain}] Acquired lock | token={lock_token[:8]}...')
        
        try:
            return self._drain_batch()
        finally:
            # Safe release: only delete if we still own the lock
            released = redis.eval(
                LOCK_RELEASE_SCRIPT, 
                1, 
                self.lock_key, 
                lock_token
            )
            if released:
                logger.debug(f'[{self.domain}] Released lock')
            else:
                logger.warning(
                    f'[{self.domain}] Lock expired or taken by another process'
                )
    
    def _drain_batch(self) -> dict:
        """
        Core drainer logic - process batches until queue is empty.
        
        Pattern from Brandur's job-drain:
        1. SELECT pending rows with FOR UPDATE (prevent other drainers)
        2. Enqueue to Celery
        3. Mark as 'sent' on successful enqueue
        
        Returns:
            dict: {processed: int, empty: bool}
        """
        start_time = time.time()
        empty_attempts = 0
        total_processed = 0
        
        while True:
            batch = self._fetch_pending_batch()
            
            if not batch:
                # Exponential backoff when empty to reduce DB load
                base_sleep = self.empty_backoff_seconds[
                    min(empty_attempts, len(self.empty_backoff_seconds) - 1)
                ]
                # Add jitter (±25%) to prevent thundering herd across drainers
                sleep_time = int(base_sleep * random.uniform(0.75, 1.25))
                logger.info(f'[{self.domain}] Empty batch, backing off for {sleep_time}s (base={base_sleep}s)')
                time.sleep(sleep_time)
                empty_attempts += 1
                
                # Exit after max backoff to release lock
                if empty_attempts >= len(self.empty_backoff_seconds):
                    break
                continue
            
            # Reset backoff on non-empty batch
            empty_attempts = 0
            
            # Process batch
            processed = self._process_batch(batch)
            total_processed += processed
            
            # Continue until we get a partial batch (end of queue)
            if len(batch) < self.batch_size:
                break
        
        elapsed_ms = (time.time() - start_time) * 1000
        logger.info(
            f'[{self.domain}] Drainer completed | '
            f'processed={total_processed} | elapsed_ms={elapsed_ms:.1f}'
        )
        
        return {'processed': total_processed, 'skipped': False, 'empty': empty_attempts > 0}
    
    def _fetch_pending_batch(self) -> List[Outbox]:
        """
        Fetch next batch of pending entries with row-level locking.
        
        Uses select_for_update() to prevent concurrent drainers from
        processing the same rows (DDIA: exactly-once processing).
        skip_locked=True allows other drainers to skip rows we're processing.
        """
        with transaction.atomic():
            batch = list(
                Outbox.objects
                .filter(domain=self.domain, status=Outbox.Status.PENDING)
                .order_by('id')
                .select_for_update(skip_locked=True)[:self.batch_size]
            )
            return batch
    
    def _process_batch(self, batch: List[Outbox]) -> int:
        """
        Process a batch of outbox entries.
        
        Steps:
        1. Enqueue entries to Celery (each entry is a Celery task)
        2. Mark successful enqueues as 'sent'
        3. Mark failed enqueues with error (stay pending for retry)
        
        Any failure during enqueue is tracked but doesn't stop processing.
        Celery handles the actual retry logic.
        
        Args:
            batch: List of Outbox entries to process
            
        Returns:
            int: Number of successfully enqueued entries
        """
        # Enqueue to Celery
        successfully_enqueued = []
        failed_enqueued = []
        
        for entry in batch:
            try:
                self.enqueue_func(entry)
                successfully_enqueued.append(entry.id)
            except Exception as e:
                logger.error(
                    f'[{self.domain}] Failed to enqueue outbox_id={entry.id} | '
                    f'error={type(e).__name__}: {str(e)}'
                )
                failed_enqueued.append((entry.id, str(e)))
        
        # Mark successful enqueues as sent
        if len(successfully_enqueued) > 0:
            with transaction.atomic():
                Outbox.objects.filter(id__in=successfully_enqueued).update(
                    status=Outbox.Status.SENT,
                    sent_at=timezone.now()
                )
        
        # Mark failed enqueues with error (stay pending for next poll)
        for entry_id, error in failed_enqueued:
            with transaction.atomic():
                Outbox.objects.filter(id=entry_id).update(
                    last_error=error[:500]  # Truncate for DB field
                )
        
        logger.info(
            f'[{self.domain}] Batch complete | '
            f'batch_size={len(batch)} | success={len(successfully_enqueued)} | '
            f'failed={len(failed_enqueued)}'
        )
        
        return len(successfully_enqueued)


def recover_stale_entries(domain: str, stale_threshold_minutes: int = 30) -> dict:
    """
    Recovery function: detect and reset entries stuck for too long.
    
    In normal operation, entries transition PENDING -> SENT quickly.
    If the drainer or worker crashes, entries might stay in PENDING
    state indefinitely. This function detects stale entries and 
    logs them for investigation.
    
    Note: Entries stay PENDING so they get reprocessed. The outbox
    is the source of truth - we don't force-reset, just alert.
    
    Args:
        domain: Domain to check (e.g., 'notifications')
        stale_threshold_minutes: Age threshold for staleness
        
    Returns:
        dict: {stale_count: int, oldest_stale_minutes: int|None}
    """
    stale_threshold = timezone.now() - timedelta(minutes=stale_threshold_minutes)
    
    stale_entries = Outbox.objects.filter(
        domain=domain,
        status=Outbox.Status.PENDING,
        created_at__lt=stale_threshold
    ).order_by('created_at')
    
    count = stale_entries.count()
    oldest = stale_entries.first()
    
    if count > 0 and oldest:
        oldest_age = (timezone.now() - oldest.created_at).total_seconds() / 60
        logger.warning(
            f'[{domain}] Found {count} stale pending entries | '
            f'oldest={oldest_age:.1f}min ago | '
            f'ids={list(stale_entries.values_list("id", flat=True)[:10])}'
        )
        return {'stale_count': count, 'oldest_stale_minutes': oldest_age}
    
    return {'stale_count': 0, 'oldest_stale_minutes': None}
