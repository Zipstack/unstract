# **Manual Testing:**

## **Test 1: BROKEN (Shell Wrapper)**
```bash
### Build and run
docker build -t signal-test .
docker run -d --name broken-test signal-test /bin/sh -c "python3 /app/shell-signal-test.py"
```

### **Test 2: WORKING (Dumb-init Wrapper)**
```bash
# Run with dumb-init
docker run -d --name working-test signal-test dumb-init /bin/sh -c "python3 /app/shell-signal-test.py"
```

# Results:

## **Test 1: BROKEN (Shell Wrapper)**

```
🚀 Signal Test Program Started
📋 PID: 7
⏰ Start Time: 09:07:15
🎯 Waiting for SIGTERM or SIGINT signal...
💡 Send 'kill -TERM 7' or 'kill -INT 7' from another terminal
🔄 Program will log status every 2 seconds until signal received
⚠️  SIGTERM Test: If no graceful shutdown appears, signal was NOT forwarded!
✅ Expected: Graceful shutdown messages should appear within 10 seconds
⏱️  [09:07:15] Running... (iteration 1, elapsed: 0.0s)
⏱️  [09:07:17] Running... (iteration 2, elapsed: 2.0s)
⏱️  [09:07:19] Running... (iteration 3, elapsed: 4.0s)
⏱️  [09:07:21] Running... (iteration 4, elapsed: 6.0s)
⏱️  [09:07:23] Running... (iteration 5, elapsed: 8.0s)
🔍 [09:07:23] Still waiting for SIGTERM... (No signal received yet)
⏱️  [09:07:25] Running... (iteration 6, elapsed: 10.0s)
⏱️  [09:07:27] Running... (iteration 7, elapsed: 12.0s)
⏱️  [09:07:29] Running... (iteration 8, elapsed: 14.0s)
⏱️  [09:07:31] Running... (iteration 9, elapsed: 16.0s)
⏱️  [09:07:33] Running... (iteration 10, elapsed: 18.0s)
🔍 [09:07:33] Still waiting for SIGTERM... (No signal received yet)
⏱️  [09:07:35] Running... (iteration 11, elapsed: 20.0s)
```
**Program exits without graceful shutdown.**

## **Test 2: WORKING (Dumb-init Wrapper)**

```
🚀 Signal Test Program Started
📋 PID: 8
⏰ Start Time: 09:07:49
🎯 Waiting for SIGTERM or SIGINT signal...
💡 Send 'kill -TERM 8' or 'kill -INT 8' from another terminal
🔄 Program will log status every 2 seconds until signal received
⚠️  SIGTERM Test: If no graceful shutdown appears, signal was NOT forwarded!
✅ Expected: Graceful shutdown messages should appear within 10 seconds
⏱️  [09:07:49] Running... (iteration 1, elapsed: 0.0s)
⏱️  [09:07:51] Running... (iteration 2, elapsed: 2.0s)
⏱️  [09:07:53] Running... (iteration 3, elapsed: 4.0s)
⏱️  [09:07:55] Running... (iteration 4, elapsed: 6.0s)
⏱️  [09:07:57] Running... (iteration 5, elapsed: 8.0s)
🔍 [09:07:57] Still waiting for SIGTERM... (No signal received yet)
⏱️  [09:07:59] Running... (iteration 6, elapsed: 10.0s)
⏱️  [09:08:01] Running... (iteration 7, elapsed: 12.0s)
🔔 [09:08:02] Received SIGTERM signal!
🔔 [09:08:02] Received SIGTERM signal!
📊 Program ran for: 13.5 seconds
🧹 Starting graceful shutdown procedure...
⏳ Simulating cleanup work (5 seconds)...
[09:08:02] 💾 Saving application state...
```
**Program exits with graceful shutdown.**

## Full results are shown in screenshot in PR
