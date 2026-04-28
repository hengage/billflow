"""
Outbox pattern for reliable async job processing.

Implements the 'job drain' pattern from:
https://brandur.org/job-drain

Key principles:
- Jobs are written to outbox in same transaction as business logic
- Single enqueuer process polls and fans out to workers
- Domain-specific drainers for different batch sizes/rates
- Celery handles retries, outbox tracks pending/drained/failed status
"""
import uuid
from django.db import models


class Outbox(models.Model):
    """
    Staged jobs for async processing.
    
    Each domain has its own drainer task that polls this table,
    enqueues to Celery, then marks as drained.
    """
    
    class Status(models.TextChoices):
        PENDING = 'pending', 'Pending'
        DRAINED = 'drained', 'Drained'  # Queued to Celery
        SENT = 'sent', 'Sent'  # Successfully delivered
        FAILED = 'failed', 'Failed'  # Max retries exhausted or permanent failure
    
    # Sequential ID for efficient range queries (ORDER BY id)
    id = models.BigAutoField(primary_key=True)
    
    # Domain identifies which app/system owns this job
    # Examples: 'notifications', 'webhooks', 'payments'
    domain = models.CharField(max_length=50, db_index=True)
    
    # Event type - domain-specific (e.g., 'renewal_failed', 'payment_webhook')
    event_type = models.CharField(max_length=100)
    
    # Opaque payload - each domain defines its own schema
    # Notifications: {user_id, email, template_name, subject, context}
    # Webhooks: {webhook_url, headers, body}
    payload = models.JSONField()
    
    # Status tracking
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.PENDING
    )
    
    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)
    last_drained_at = models.DateTimeField(null=True, blank=True)
    sent_at = models.DateTimeField(null=True, blank=True)
    
    # Error tracking (for audit, not for retry logic)
    last_error = models.TextField(blank=True)
    
    class Meta:
        indexes = [
            models.Index(fields=['domain', 'status', 'id']),
            models.Index(fields=['status', 'created_at']),
            models.Index(fields=['status', 'last_drained_at']),
            models.Index(fields=['status', 'updated_at']),
        ]
        ordering = ['id']
        verbose_name = 'Outbox Entry'
        verbose_name_plural = 'Outbox Entries'
    
    def __str__(self):
        return f"{self.domain}:{self.event_type} ({self.status})"
