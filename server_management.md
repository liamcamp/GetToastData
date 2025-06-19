# Toast API Server Management Guide

## Quick Start

### 1. Deploy to Server
```bash
./deploy_simple.sh
```

### 2. Test the API
```bash
python test_api.py
```

### 3. Check Logs (on server)
```bash
ssh root@64.23.129.92
journalctl -u toast-api -f
```

## Server Management Commands

### On Your Local Machine

```bash
# Deploy code to server
./deploy_simple.sh

# Test the remote API
python test_api.py

# Test local development server
./start_server_local.sh
python test_api.py local
```

### On the Server (via SSH)

```bash
# SSH into server
ssh root@64.23.129.92

# View live logs
journalctl -u toast-api -f

# View recent logs
journalctl -u toast-api -n 100

# Check service status
systemctl status toast-api

# Restart service
systemctl restart toast-api

# Stop service
systemctl stop toast-api

# Start service
systemctl start toast-api

# View error logs only
journalctl -u toast-api -p err

# View logs from specific time
journalctl -u toast-api --since "2025-06-19 10:00:00"
```

## API Endpoints

### Health Check
```bash
curl http://64.23.129.92:5000/health
```

### Debug Information
```bash
curl http://64.23.129.92:5000/debug
```

### Process Tips
```bash
curl -X POST http://64.23.129.92:5000/tips \
  -H "Content-Type: application/json" \
  -d '{
    "startDate": "2025-06-13",
    "endDate": "2025-06-15",
    "webhook": "https://your-webhook-url",
    "locationIndex": 1
  }'
```

### Check Task Status
```bash
curl http://64.23.129.92:5000/status/TASK_ID
```

### View Task Logs
```bash
curl http://64.23.129.92:5000/logs/TASK_ID
```

## Troubleshooting

### Server Not Responding
1. Check if service is running:
   ```bash
   ssh root@64.23.129.92 "systemctl status toast-api"
   ```

2. Check service logs:
   ```bash
   ssh root@64.23.129.92 "journalctl -u toast-api -n 50"
   ```

3. Restart service:
   ```bash
   ssh root@64.23.129.92 "systemctl restart toast-api"
   ```

### Task Stuck in Processing
1. Check task logs:
   ```bash
   curl http://64.23.129.92:5000/logs/TASK_ID
   ```

2. Check server logs:
   ```bash
   ssh root@64.23.129.92 "journalctl -u toast-api -f"
   ```

### API Returning Errors
1. Check debug endpoint:
   ```bash
   curl http://64.23.129.92:5000/debug | python -m json.tool
   ```

2. Verify environment variables:
   ```bash
   ssh root@64.23.129.92 "cd /root/GetToastData && cat .env"
   ```

## File Locations on Server

- **Application Code**: `/root/GetToastData/`
- **Service File**: `/etc/systemd/system/toast-api.service`
- **Application Logs**: `/root/GetToastData/logs/`
- **System Logs**: `journalctl -u toast-api`
- **Environment File**: `/root/GetToastData/.env`

## Development Workflow

1. **Make Changes Locally**: Edit files in your local directory
2. **Test Locally** (optional): `./start_server_local.sh`
3. **Deploy**: `./deploy_simple.sh`
4. **Test Remote**: `python test_api.py`
5. **Check Logs**: `ssh root@64.23.129.92 "journalctl -u toast-api -f"`

## Key Improvements

### Simplified Logging
- All logs go to one structured location
- Clear timestamps and context
- Separate log files for each task
- Easy to read format

### Better Error Handling
- Comprehensive error notifications
- Detailed traceback information
- Automatic retry mechanisms
- Clear error messages

### Easy Debugging
- `/debug` endpoint shows server state
- `/health` endpoint for monitoring
- Individual task log access
- Structured error reporting

### Reliable Deployment
- Single command deployment
- Automatic service management
- Environment validation
- Clear success/failure feedback