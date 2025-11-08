# Bimdash - Simple Self-Hosted System Monitor

A comprehensive, lightweight system monitoring dashboard with real-time metrics and external API integration.

![Bimdash](static/images/bimdash-og.png)

## Features

-  **Real-time Monitoring**: CPU, memory, disk, network, and process monitoring
-  **Docker Integration**: Monitor Docker containers with detailed stats
-  **Interactive Dashboard**: Clean, responsive UI with charts
-  **API Access**: RESTful API with API key authentication
-  **Mobile Friendly**: Fully responsive design
-  **Lightweight**: Idle mode uses only ~0.06% CPU
-  **Secure**: Rate limiting, API key management, login protection

## Quick Start

### Using Docker Compose (Recommended)

```bash
docker compose up -d
```

Access the dashboard at `http://localhost:8535`

**Default credentials:**
- Username: `bimdash`
- Password: `secret123`

**⚠️ Change the default password immediately in Settings!**

## Environment Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `BIMDASH_USERNAME` | Default username | `bimdash` |
| `BIMDASH_PASSWORD` | Default password | `secret123` |
| `SECRET_KEY` | Flask secret key | `dev-secret-key-change-in-production` |
| `BIMDASH_METRICS_INTERVAL` | Collector interval (seconds) | `1.0` |
| `BIMDASH_IDLE_INTERVAL` | Idle mode interval (seconds) | `30.0` |
| `BIMDASH_IDLE_TIMEOUT` | Seconds before entering idle mode | `5.0` |
| `BIMDASH_FAST_POLL_MS` | Frontend poll interval when active (ms) | `1000` |
| `BIMDASH_SLOW_POLL_MS` | Frontend slow poll interval (ms) | `5000` |
| `BIMDASH_HIDDEN_POLL_MS` | Poll interval when tab is hidden (ms) | `0` (disabled) |
| `BIMDASH_DEFAULT_LIMITS` | Default rate limits (comma-separated) | `200 per day,50 per hour` |
| `RATELIMIT_STORAGE_URL` | Rate limit storage backend | `memory://` |

## Rate Limiting & DDoS Protection

### Current Protection

- **Login endpoint**: 5 requests per minute
- **API v1 endpoints**: 10 requests per minute per API key
- **Default limits**: 200 requests per day, 50 per hour
- **Invalid API keys**: Shared bucket to prevent bypass attempts

### Production Deployment (Important!)

⚠️ **For production deployments with multiple Gunicorn workers**, the default in-memory rate limiting will be **per-worker**, not global. This means clients can bypass limits by hitting different workers.

**Recommended: Use Redis for production**

1. Install Redis:
```bash
docker run -d --name redis -p 6379:6379 redis:alpine
```

2. Set environment variable:
```bash
RATELIMIT_STORAGE_URL=redis://redis:6379
```

3. Update `docker-compose.yml`:
```yaml
services:
  bimdash:
    environment:
      - RATELIMIT_STORAGE_URL=redis://redis:6379
    depends_on:
      - redis
  
  redis:
    image: redis:alpine
    container_name: redis
    restart: unless-stopped
```

This ensures rate limits are enforced **globally across all workers**.

### Customizing Rate Limits

Set environment variables to adjust limits:

```bash
# More restrictive
BIMDASH_DEFAULT_LIMITS="100 per day,20 per hour"

# For high-traffic scenarios (with Redis!)
BIMDASH_DEFAULT_LIMITS="1000 per day,200 per hour"
```

## API Documentation

### Access Swagger UI

Visit `http://localhost:8535/api/v1/docs` for interactive API documentation.

### Creating API Keys

1. Login to the dashboard
2. Go to **Settings** (top right)
3. Scroll to **API Keys** section
4. Click **+ New API Key**
5. Copy the key immediately (only shown once!)

### Using the API

**Authentication:**
```bash
# Via header (recommended)
curl -H "X-API-Key: YOUR_API_KEY" http://localhost:8535/api/v1/stats

# Via query parameter
curl "http://localhost:8535/api/v1/stats?api_key=YOUR_API_KEY"
```

**Available Endpoints:**
- `GET /api/v1/system` - System information (hostname, OS, CPU count, uptime)
- `GET /api/v1/stats` - Current statistics (CPU, memory, network)
- `GET /api/v1/docker` - Docker containers information

**Note:** API data is cached and updated every ~30 seconds when idle to save resources. It's NOT real-time.

### JavaScript Example

```javascript
const API_KEY = 'YOUR_API_KEY';
const BASE_URL = 'http://localhost:8535/api/v1';

async function getStats() {
  const response = await fetch(`${BASE_URL}/stats`, {
    headers: {
      'X-API-Key': API_KEY
    }
  });
  
  if (response.status === 429) {
    console.error('Rate limit exceeded');
    return;
  }
  
  const data = await response.json();
  console.log(`CPU: ${data.cpu.percent}%`);
  console.log(`Memory: ${data.memory.percent}%`);
}

getStats();
```

## Performance & Resource Usage

### Idle Mode (No Active Users)
- CPU: ~0.03-0.06%
- Memory: ~130-140 MB
- Collector updates: Every 30 seconds (disk & docker only)

### Active Mode (Dashboard Open)
- CPU: ~10-15%
- Memory: ~135-145 MB
- Collector updates: Every 1 second (all metrics)

### Automatic Mode Switching
- Enters idle mode after 5 seconds of no requests
- Wakes instantly when requests arrive
- Frontend stops polling when tab is hidden

## Security Recommendations

1. **Change default credentials** immediately
2. **Use strong SECRET_KEY** in production:
   ```bash
   SECRET_KEY=$(python3 -c 'import secrets; print(secrets.token_hex(32))')
   ```
3. **Enable HTTPS** with reverse proxy (Nginx/Traefik)
4. **Use Redis** for rate limiting in production
5. **Limit API key count** (max 5 per user by default)
6. **Monitor logs** for suspicious activity
7. **Keep API keys secret** - treat like passwords

## Troubleshooting

### Rate limit not working?

If using multiple Gunicorn workers (default: 3), install Redis:
```bash
# Add to docker-compose.yml
RATELIMIT_STORAGE_URL=redis://redis:6379
```

### High CPU usage?

Check if you're in active mode. CPU usage should drop to <0.1% after 5 seconds of inactivity.

### Can't access Docker stats?

Ensure Docker socket is mounted:
```yaml
volumes:
  - /var/run/docker.sock:/var/run/docker.sock
```

## License

MIT License - feel free to use and modify!

## Support

For issues or questions, please check the application logs:
```bash
docker logs bimdash
```
