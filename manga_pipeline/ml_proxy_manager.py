import json
import logging
import random
import time
import requests
from bs4 import BeautifulSoup
from pathlib import Path
from typing import Dict, List, Optional
import math
import threading

logger = logging.getLogger(__name__)

class MLProxyManager:
    """
    Manages a pool of proxy IPs using a Multi-Armed Bandit (Upper Confidence Bound)
    algorithm to prioritize reliable and fast proxies.
    Automatically fetches free proxies if none are provided.
    """
    def __init__(self, data_dir: str = '.', config_file: str = 'proxy_stats.json'):
        self.data_dir = Path(data_dir)
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.config_path = self.data_dir / config_file
        self.proxies: Dict[str, Dict] = {}
        # add_proxy() persists while holding the lock, so this must be re-entrant.
        self._lock = threading.RLock()
        
        # Load or initialize
        self._load_stats()
        
        # If no proxies exist or all are heavily penalized, fetch free ones
        if not self.proxies or self._count_healthy_proxies() < 5:
            self.fetch_free_proxies()

    def _load_stats(self):
        if self.config_path.exists():
            try:
                with open(self.config_path, 'r') as f:
                    self.proxies = json.load(f)
                logger.info(f"Loaded {len(self.proxies)} proxies from {self.config_path}")
            except Exception as e:
                logger.error(f"Failed to load proxy stats: {e}")
                self.proxies = {}

    def _save_stats(self):
        with self._lock:
            try:
                temp_path = self.config_path.with_suffix(self.config_path.suffix + ".tmp")
                with open(temp_path, 'w') as f:
                    json.dump(self.proxies, f, indent=2)
                temp_path.replace(self.config_path)
            except Exception as e:
                logger.error(f"Failed to save proxy stats: {e}")

    def _count_healthy_proxies(self) -> int:
        return sum(1 for p in self.proxies.values() if p.get('success_rate', 1.0) > 0.2 and p.get('ban_until', 0) < time.time())

    def fetch_free_proxies(self):
        """Scrapes free public proxies to use as a fallback if the user has no premium proxies."""
        logger.info("Fetching free public proxies for ML Proxy Manager...")
        added = 0
        
        # Source 1: free-proxy-list.net
        try:
            response = requests.get("https://free-proxy-list.net/", timeout=10)
            soup = BeautifulSoup(response.text, 'html.parser')
            table = soup.find('table', attrs={'class': 'table table-striped table-bordered'})
            if table and table.tbody:
                for row in table.tbody.find_all('tr')[:50]:
                    cols = row.find_all('td')
                    if len(cols) >= 8:
                        ip, port = cols[0].text.strip(), cols[1].text.strip()
                        https = cols[6].text.strip() == 'yes'
                        proxy_url = f"{'https' if https else 'http'}://{ip}:{port}"
                        self.add_proxy(proxy_url, tier="free")
                        added += 1
        except Exception as e:
            logger.debug(f"Source 1 proxy fetch failed: {e}")

        # Source 2: ProxyScrape API (very reliable text list)
        try:
            url = "https://api.proxyscrape.com/v2/?request=displayproxies&protocol=http&timeout=10000&country=all&ssl=all&anonymity=all"
            response = requests.get(url, timeout=10)
            if response.status_code == 200:
                for line in response.text.split('\n')[:50]:
                    line = line.strip()
                    if line:
                        # Assume HTTP for these
                        self.add_proxy(f"http://{line}", tier="free")
                        added += 1
        except Exception as e:
            logger.debug(f"Source 2 proxy fetch failed: {e}")

        if added > 0:
            logger.info(f"Successfully scraped {added} free proxies.")
        else:
            logger.warning("Failed to fetch any free proxies. Direct IP will be used.")

    def add_proxy(self, proxy_str: str, tier: str = "custom", initial_score: float = 1.0):
        with self._lock:
            if proxy_str not in self.proxies:
                self.proxies[proxy_str] = {
                    'tier': tier,
                    'successes': 0,
                    'failures': 0,
                    'success_rate': initial_score,
                    'avg_latency': 5.0, # default 5s
                    'total_requests': 0,
                    'ban_until': 0
                }
        self._save_stats()

    def get_best_proxy(self) -> Optional[str]:
        """
        Selects the optimal proxy using Upper Confidence Bound (UCB).
        Balancing Exploration (trying new/unused proxies) and Exploitation (using fast, reliable ones).
        """
        with self._lock:
            if not self.proxies:
                return None

            current_time = time.time()
            best_proxy = None
            max_ucb = -float('inf')
            
            # Total pulls for UCB log
            total_pulls = sum(p['total_requests'] for p in self.proxies.values()) + 1
            
            for proxy, stats in self.proxies.items():
                if stats['ban_until'] > current_time:
                    continue # This proxy is currently in timeout
                
                # If we've never tried this proxy, force explore it
                if stats['total_requests'] == 0:
                    return proxy

                # UCB formula: Success Rate + Exploration term + Speed bonus
                success_rate = stats['successes'] / stats['total_requests']
                exploration = math.sqrt((2 * math.log(total_pulls)) / stats['total_requests'])
                
                # Speed modifier (lower latency is better, cap at +0.5 bonus)
                speed_bonus = max(0, (5.0 - stats['avg_latency']) * 0.1)
                
                ucb_score = success_rate + exploration + speed_bonus
                
                if ucb_score > max_ucb:
                    max_ucb = ucb_score
                    best_proxy = proxy
                    
            # If all are banned, fallback to direct IP (None)
            return best_proxy

    def report_result(self, proxy: str, success: bool, latency: float, cloudflare_blocked: bool = False):
        """Report back to the ML manager to adjust weights."""
        if not proxy or proxy not in self.proxies:
            return

        with self._lock:
            stats = self.proxies[proxy]
            stats['total_requests'] += 1
            
            if success:
                stats['successes'] += 1
            else:
                stats['failures'] += 1
                
                # A connection failure from an untested public proxy is enough
                # evidence to set it aside. This lets UCB explore another
                # candidate immediately instead of repeatedly timing out.
                if cloudflare_blocked:
                    logger.warning(f"Proxy {proxy} blocked by Cloudflare. Banning for 1 hour.")
                    stats['ban_until'] = time.time() + 3600
                elif stats['successes'] == 0:
                    logger.warning(f"Proxy {proxy} failed its first request. Banning for 10 minutes.")
                    stats['ban_until'] = time.time() + 600
                elif stats['success_rate'] < 0.2 and stats['total_requests'] > 5:
                    logger.warning(f"Proxy {proxy} is too unreliable. Banning for 10 minutes.")
                    stats['ban_until'] = time.time() + 600

            # Update rolling success rate
            stats['success_rate'] = stats['successes'] / stats['total_requests']
            
            # Update EMA (Exponential Moving Average) of latency
            alpha = 0.3
            stats['avg_latency'] = (alpha * latency) + ((1 - alpha) * stats['avg_latency'])
            
        # Save occasionally, not every single request to save I/O
        if random.random() < 0.1:
            self._save_stats()
