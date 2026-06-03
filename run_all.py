#!/usr/bin/env python3
"""
Runner script to run both Aziza (bot.py) and Nuvi Jobs Bot (nuvi_bot.py) concurrently.
"""
import subprocess
import sys
import time

print("🚀 Starting both bots concurrently...")

p1 = subprocess.Popen([sys.executable, "bot.py"])
p2 = subprocess.Popen([sys.executable, "nuvi_bot.py"])

print(f"🔹 bot.py started with PID: {p1.pid}")
print(f"🔹 nuvi_bot.py started with PID: {p2.pid}")

try:
    while True:
        time.sleep(5)
        # Check if any process has exited
        if p1.poll() is not None:
            print("❌ bot.py exited. Shutting down nuvi_bot.py and exiting...")
            p2.terminate()
            sys.exit(p1.returncode)
        if p2.poll() is not None:
            print("❌ nuvi_bot.py exited. Shutting down bot.py and exiting...")
            p1.terminate()
            sys.exit(p2.returncode)
except KeyboardInterrupt:
    print("⚠️ Shutdown signal received. Terminating both processes...")
    p1.terminate()
    p2.terminate()
    sys.exit(0)
