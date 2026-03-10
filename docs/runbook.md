# Operational Runbook — Cloud-Native Order Service

This runbook covers common operational scenarios, failure modes, and resolution steps.

---

## Table of Contents

1. [Service Won't Start](#1-service-wont-start)
2. [Database Connection Failures](#2-database-connection-failures)
3. [Payment Service Timeouts](#3-payment-service-timeouts)
4. [High Latency / Slow Responses](#4-high-latency--slow-responses)
5. [Order Stuck in Invalid State](#5-order-stuck-in-invalid-state)
6. [Deployment Checklist](#6-deployment-checklist)

---

## 1. Service Won't Start

### Symptoms
- Container exits immediately
- `uvicorn` process fails on startup

### Investigation Steps
```bash
# Check container logs
docker-compose logs api

# Verify environment variables
docker-compose exec api env | grep DATABASE

# Test database connectivity manually
docker-compose exec db psql -U orders_user -d orders_db -c "SELECT 1"
```

### Common Causes
| Cause | Fix |
|-------|-----|
| Missing `DATABASE_URL` | Ensure `.env` or compose env is set |
| DB not ready yet | Check `depends_on` health check in compose |
| Port conflict | Change `APP_PORT` or stop conflicting service |

---

## 2. Database Connection Failures

### Symptoms
- `asyncpg.CannotConnectNowError` in logs
- 500 errors on all endpoints

### Resolution
1. Verify PostgreSQL is running: `docker-compose ps db`
2. Check connection string format: `postgresql+asyncpg://user:pass@host:5432/dbname`
3. Verify network connectivity: `docker-compose exec api ping db`
4. Check pool exhaustion in logs (look for `pool_size` warnings)

### Prevention
- Set `pool_pre_ping=True` (already configured)
- Monitor connection pool utilization
- Set appropriate `pool_size` and `max_overflow` values

---

## 3. Payment Service Timeouts

### Symptoms
- Status transitions to `confirmed` fail with 502
- Logs show `payment_failed` events with timeout errors

### Resolution
1. Check payment service health: `curl $PAYMENT_SERVICE_URL/health`
2. Review retry configuration:
   - `PAYMENT_SERVICE_RETRIES`: Number of retry attempts (default: 3)
   - `PAYMENT_SERVICE_TIMEOUT`: Request timeout in seconds (default: 5s)
3. The service uses **exponential backoff** (1s, 2s, 4s...) automatically

### Workaround
If the payment service is down for an extended period:
1. Do NOT retry confirmed transitions — they are idempotent
2. Monitor the order stuck in `pending` state
3. Once payment service recovers, retry the transition

---

## 4. High Latency / Slow Responses

### Investigation
```bash
# Check structured logs for slow requests
docker-compose logs api | grep '"duration_ms"' | sort -t: -k2 -rn | head

# Check database query performance
docker-compose exec db psql -U orders_user -d orders_db \
  -c "SELECT * FROM pg_stat_activity WHERE state = 'active'"
```

### Common Fixes
- Add database indexes (already included for common queries)
- Increase connection pool size
- Check for N+1 query patterns in logs

---

## 5. Order Stuck in Invalid State

### Investigation
```bash
# Check order history for what happened
curl http://localhost:8000/api/v1/orders/{order_id}/history
```

### Valid State Machine
```
pending → confirmed → shipped → delivered
pending → cancelled
confirmed → cancelled
```

### Manual Fix (last resort)
```sql
-- Only use if state is genuinely corrupted
UPDATE orders SET status = 'cancelled', updated_at = NOW()
WHERE id = '<order_id>';

INSERT INTO order_history (id, order_id, field_name, old_value, new_value, changed_by)
VALUES (gen_random_uuid(), '<order_id>', 'status', '<old>', 'cancelled', 'ops-manual');
```

---

## 6. Deployment Checklist

- [ ] Environment variables configured (see `.env.example`)
- [ ] PostgreSQL is accessible and migrations applied
- [ ] Health check endpoint responding: `GET /health`
- [ ] Structured logs are being collected
- [ ] CI pipeline is green
- [ ] Payment service URL is reachable (if applicable)
- [ ] Container resource limits are set (memory, CPU)
