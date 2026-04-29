# BillFlow

A bill payment, wallet & subscription API built with Django REST Framework.

## Stack

- **Backend:** Python · Django 5.2 · Django REST Framework
- **Database:** PostgreSQL
- **Cache/Queue:** Redis · Celery
- **Real-time:** Django Channels · Daphne
- **Payments:** Paystack (NGN) · Stripe (USD)
- **Auth:** JWT (dj-rest-auth) · Google OAuth (allauth)

## Features

### Core Domains

- **Plans** — Subscription products with monthly/yearly pricing in NGN/USD
- **Subscriptions** — Active, cancelled, or expired user subscriptions with automatic expiry handling
- **Wallet** — Per-user balance with top-up via Paystack/Stripe
- **Payments** — Direct payment initiation with idempotency, webhook handling, and provider abstraction

### Payment Flows

| Flow | Description |
|------|-------------|
| **Wallet Top-up** | Add funds via Paystack/Stripe → Credit wallet instantly |
| **Wallet Subscription** | Deduct from wallet → Immediate subscription activation |
| **Direct Subscription** | Paystack/Stripe → Webhook activates subscription on success |
| **Renewal** | Extend existing subscription (7-day eligibility gate) |
| **Plan Switch** | Cancel current → Create new with immediate or deferred activation |

### Infrastructure

- **Outbox Pattern** — Reliable async notification delivery with at-least-once guarantees
- **Idempotency Keys** — Duplicate request protection for payment initiation
- **Payment Processor** — Atomic phases pattern for payment lifecycle management
- **Row-level Locking** — Concurrency safety via `select_for_update()`
- **Circuit Breaker** — Automatic degradation on provider failures

## Project Structure

```
billflow/
├── apps/
│   ├── authentication/    # JWT auth, Google OAuth, password reset
│   ├── users/            # Custom User model, UserManager, permissions
│   ├── wallet/          # Wallet balance, top-up, deductions
│   ├── subscriptions/    # Plans, Subscriptions, renewal, plan switching
│   ├── payments/         # Paystack/Stripe services, webhooks, history
│   ├── notifications/    # Outbox, email/push delivery, Celery tasks
│   ├── rates/           # Exchange rates with Redis caching
│   ├── websockets/      # JWT WebSocket auth, real-time consumers
│   └── infra/           # Outbox drainer, Celery helpers, shared utils
├── api_response/         # Standardized API response helpers
├── utils/               # Cross-cutting utilities (messages, currency, etc.)
└── config/              # Django settings, URLs, WSGI/ASGI
```

### Creating New Apps

All apps live in `apps/` directory. To create a new app:

```bash
make create-app NAME=<app_name>
```

This scaffolds:
```
apps/<app_name>/
├── __init__.py
├── apps.py
├── models.py
├── serializers.py
├── views.py
├── urls.py
├── permissions.py
├── admin.py
└── migrations/
    └── __init__.py
```

Then register in `config/settings.py`:
```python
INSTALLED_APPS = [
    ...
    'apps.<app_name>',
]
```

## Quick Start

### Prerequisites

- Docker
- Docker Compose

### Setup

```bash
# Copy environment variables
cp .env.example .env
# Edit .env with your Paystack and Stripe credentials

# Build and start all services
make up

# Run migrations
make migrate

# Create superuser
make superuser
```

See `Makefile` for all available commands (`make build`, `make down`, `make logs`, `make test`, etc.).

## API Overview

### Authentication

- `POST /api/auth/register/` — User registration
- `POST /api/auth/login/` — JWT login
- `POST /api/auth/google/` — Google OAuth
- `POST /api/auth/token/refresh/` — Refresh JWT

### Subscriptions

- `GET /api/subscriptions/plans/` — List active plans
- `POST /api/subscriptions/subscribe/` — New subscription (wallet or direct)
- `POST /api/subscriptions/renew/` — Renew existing subscription
- `POST /api/subscriptions/switch-plan/` — Switch to different plan
- `GET /api/subscriptions/me/` — Current user's subscription
- `POST /api/subscriptions/cancel/` — Cancel subscription

### Wallet

- `GET /api/wallet/balance/` — Current balance
- `POST /api/wallet/topup/` — Initiate top-up
- `GET /api/wallet/transactions/` — Transaction history

### Payments

- `POST /api/payments/initiate/` — Initiate direct payment
- `GET /api/payments/history/` — Payment history
- `POST /api/payments/paystack/verify/{reference}/` — Verify Paystack transaction

### Webhooks

- `POST /api/payments/paystack/webhook/` — Paystack webhooks
- `POST /api/payments/stripe/webhook/` — Stripe webhooks

## Architecture Highlights

### Payment Processing

The `PaymentProcessor` class implements [Brandur's atomic phases pattern](https://brandur.org/idempotency-keys):

1. **STARTED** — Idempotency key created
2. **PAYMENT_CREATED** — Payment record created
3. **FINISHED** — Provider called, response returned

Each phase is idempotent and resumable on crash/retry.

### Outbox Pattern

Notifications are written to an Outbox table within the same transaction as business logic. A separate drainer process:

1. Polls for PENDING entries
2. Enqueues to Celery
3. Marks as DRAINED on success
4. Celery workers deliver and mark as SENT/FAILED

This ensures at-least-once delivery without distributed transactions.

### Subscription Lifecycle

```
ACTIVE → CANCELLED (user action)
       → EXPIRED (scheduled task when end_date_utc passed)
       → RENEWED (payment extends end_date)
       → SWITCHED (cancel old, create new)
```

Scheduled tasks:
- `dispatch_subscription_expiries` — Fan out expired subscriptions
- `process_single_expiry` — Handle expiry side-effects
- `attempt_auto_renewal` — Retry failed renewals

### Idempotency

All direct payments require an `X-Idempotency-Key` header. The same key returns the same response for 24 hours without double-charging.

## Development

### Running Tests

```bash
python manage.py test
```

### Celery Tasks

List all tasks:
```bash
celery -A config inspect registered
```

### Environment Variables

| Variable | Description |
|----------|-------------|
| `SECRET_KEY` | Django secret key |
| `DATABASE_URL` | PostgreSQL connection string |
| `REDIS_URL` | Redis connection string |
| `PAYSTACK_SECRET_KEY` | Paystack API key |
| `STRIPE_SECRET_KEY` | Stripe API key |
| `STRIPE_WEBHOOK_SECRET` | Stripe webhook signing secret |
| `CELERY_BROKER_URL` | Redis URL for Celery |

## License

MIT License

## Credits

Built with Django REST Framework, inspired by Brandur's atomic phases pattern for payment processing.
