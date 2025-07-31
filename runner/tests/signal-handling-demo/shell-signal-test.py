#!/usr/bin/env python3
"""SIGTERM Signal Handling Test Program

This program demonstrates proper SIGTERM signal handling.
It will run indefinitely until it receives a SIGTERM signal,
at which point it will perform graceful shutdown.

Usage:
    python3 shell-signal-test.py
"""

import os
import signal
import sys
import time
from datetime import datetime


class SignalTestProgram:
    def __init__(self):
        self.running = True
        self.start_time = datetime.now()

    def signal_handler(self, signum, frame):
        """Handle SIGTERM and SIGINT signals with realistic cleanup simulation"""
        signal_name = signal.Signals(signum).name
        elapsed = datetime.now() - self.start_time

        print(
            f"\n🔔 [{datetime.now().strftime('%H:%M:%S')}] Received {signal_name} signal!"
        )
        print(f"📊 Program ran for: {elapsed.total_seconds():.1f} seconds")
        print("🧹 Starting graceful shutdown procedure...")
        print("⏳ Simulating cleanup work (5 seconds)...")
        sys.stdout.flush()

        # Simulate realistic cleanup work that takes time
        cleanup_tasks = [
            "💾 Saving application state...",
            "🔌 Closing database connections...",
            "📡 Shutting down network listeners...",
            "🗄️  Flushing file buffers...",
            "🧼 Final cleanup and validation...",
        ]

        for i, task in enumerate(cleanup_tasks, 1):
            print(f"[{datetime.now().strftime('%H:%M:%S')}] {task}")
            sys.stdout.flush()
            time.sleep(10)  # Each cleanup task takes 1 second
            print(
                f"✅ [{datetime.now().strftime('%H:%M:%S')}] Cleanup step {i}/5 completed"
            )
            sys.stdout.flush()

        print(
            f"🎉 [{datetime.now().strftime('%H:%M:%S')}] All cleanup completed successfully!"
        )
        print(f"👋 Goodbye from PID {os.getpid()}!")
        sys.stdout.flush()

        self.running = False

    def run(self):
        """Main program loop"""
        # Register signal handlers for graceful shutdown
        signal.signal(signal.SIGTERM, self.signal_handler)
        signal.signal(signal.SIGINT, self.signal_handler)

        print("🚀 Signal Test Program Started")
        print(f"📋 PID: {os.getpid()}")
        print(f"⏰ Start Time: {self.start_time.strftime('%H:%M:%S')}")
        print("🎯 Waiting for SIGTERM or SIGINT signal...")
        print(
            f"💡 Send 'kill -TERM {os.getpid()}' or 'kill -INT {os.getpid()}' from another terminal"
        )
        print("🔄 Program will log status every 2 seconds until signal received")
        print(
            "⚠️  SIGTERM Test: If no graceful shutdown appears, signal was NOT forwarded!"
        )
        print("✅ Expected: Graceful shutdown messages should appear within 10 seconds")
        print("")
        sys.stdout.flush()  # Force immediate output

        counter = 0
        max_iterations = 30  # Run for max 60 seconds to avoid infinite loops

        while self.running and counter < max_iterations:
            counter += 1
            elapsed = datetime.now() - self.start_time
            timestamp = datetime.now().strftime("%H:%M:%S")

            print(
                f"⏱️  [{timestamp}] Running... (iteration {counter}, elapsed: {elapsed.total_seconds():.1f}s)"
            )

            # Add explicit verification message every 5 iterations
            if counter % 5 == 0:
                print(
                    f"🔍 [{timestamp}] Still waiting for SIGTERM... (No signal received yet)"
                )

            sys.stdout.flush()  # Force immediate output

            try:
                time.sleep(2)
            except KeyboardInterrupt:
                # Handle Ctrl+C as SIGINT
                print("\n🔔 Received Ctrl+C (SIGINT)")
                self.signal_handler(signal.SIGINT, None)
                break

        if counter >= max_iterations:
            print(
                f"\n⏰ [{datetime.now().strftime('%H:%M:%S')}] Maximum runtime reached (60s)"
            )
            print(
                "❌ No SIGTERM signal received - this indicates BROKEN signal forwarding!"
            )

        print("🏁 Program terminated gracefully")
        sys.stdout.flush()
        sys.exit(0)


if __name__ == "__main__":
    program = SignalTestProgram()
    program.run()
