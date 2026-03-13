# src/workers/lead_hunter/scrapers.py
# 13-source lead scrapers — Playwright + BeautifulSoup
# Runs in Docker on VPS or ECS Fargate

import asyncio
import json
import re
import hashlib
import logging
from datetime import datetime, timezone
from typing import List, Dict, Optional
from urllib.parse import urlparse

import httpx
from bs4 import BeautifulSoup

logger = logging.getLogger("lead_hunter.scrapers")

# ============================================================================
# UTILITIES
# ============================================================================

def normalize_domain(url: str) -> str:
    """Create domain fingerprint for dedup."""
    if not url:
        return ""
    parsed = urlparse(url if url.startswith("http") else f"https://{url}")
    domain = parsed.netloc.lower().replace("www.", "")
    return hashlib.sha256(domain.encode()).hexdigest()[:16]


def extract_emails(html: str) -> List[str]:
    """Extract emails from HTML content."""
    pattern = r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}'
    emails = list(set(re.findall(pattern, html)))
    # Filter out image files and common false positives
    blocked = ['example.com', 'email.com', '.png', '.jpg', '.gif', '.svg']
    return [e for e in emails if not any(b in e.lower() for b in blocked)]


def detect_tech_stack(html: str) -> List[str]:
    """Detect tech stack from HTML meta tags, scripts, headers."""
    signals = []
    html_lower = html.lower()
    tech_map = {
        'react': ['react', 'reactdom', '_next'],
        'vue': ['vue.js', 'vuejs', '__vue'],
        'angular': ['ng-version', 'angular'],
        'nextjs': ['_next/static', '__next'],
        'wordpress': ['wp-content', 'wordpress'],
        'shopify': ['shopify', 'cdn.shopify'],
        'stripe': ['stripe.com', 'js.stripe'],
        'intercom': ['intercom', 'widget.intercom'],
        'hubspot': ['hubspot', 'hs-scripts'],
        'salesforce': ['salesforce', 'pardot'],
        'slack': ['slack', 'hooks.slack'],
        'datadog': ['datadoghq', 'dd-rum'],
        'posthog': ['posthog', 'app.posthog'],
        'segment': ['segment.com', 'analytics.js'],
        'aws': ['amazonaws.com', 'cloudfront'],
        'gcp': ['googleapis.com', 'gstatic'],
        'docker': ['docker', 'container'],
        'kubernetes': ['k8s', 'kubernetes'],
        'supabase': ['supabase'],
        'gitlab': ['gitlab'],
    }
    for tech, keywords in tech_map.items():
        if any(kw in html_lower for kw in keywords):
            signals.append(tech)
    return signals


# ============================================================================
# BASE SCRAPER
# ============================================================================

class BaseScraper:
    """Base class for all lead scrapers."""

    SOURCE = "base"
    RATE_LIMIT_RPS = 1.0
    HEADERS = {
        "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
                       "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept-Language": "en-US,en;q=0.9",
    }

    def __init__(self):
        self.client = httpx.AsyncClient(
            headers=self.HEADERS,
            timeout=30.0,
            follow_redirects=True
        )
        self._last_request = 0

    async def _rate_limit(self):
        """Enforce rate limiting. SRS-LEAD-002."""
        now = asyncio.get_event_loop().time()
        elapsed = now - self._last_request
        wait = (1.0 / self.RATE_LIMIT_RPS) - elapsed
        if wait > 0:
            await asyncio.sleep(wait)
        self._last_request = asyncio.get_event_loop().time()

    async def fetch(self, url: str) -> Optional[str]:
        """Fetch URL with rate limiting."""
        await self._rate_limit()
        try:
            resp = await self.client.get(url)
            resp.raise_for_status()
            return resp.text
        except Exception as e:
            logger.warning(f"[{self.SOURCE}] Fetch failed {url}: {e}")
            return None

    async def scrape(self, query: str, location: str = None, max_results: int = 100) -> List[Dict]:
        raise NotImplementedError

    async def close(self):
        await self.client.aclose()


# ============================================================================
# GOOGLE MAPS SCRAPER (via Google search)
# ============================================================================

class GoogleMapsScraper(BaseScraper):
    SOURCE = "google_maps"
    RATE_LIMIT_RPS = 0.5  # Conservative to avoid blocks

    async def scrape(self, query: str, location: str = None, max_results: int = 100) -> List[Dict]:
        results = []
        search_query = f"{query} {location or ''} site:google.com/maps"
        url = f"https://www.google.com/search?q={search_query}&num=20"
        html = await self.fetch(url)
        if not html:
            return results
        soup = BeautifulSoup(html, "html.parser")
        for div in soup.select("div.g")[:max_results]:
            title_el = div.select_one("h3")
            link_el = div.select_one("a")
            if title_el and link_el:
                results.append({
                    "company_name": title_el.get_text(strip=True),
                    "website": link_el.get("href", ""),
                    "source": self.SOURCE,
                    "raw_data": {"snippet": div.get_text(" ", strip=True)[:500]},
                })
        return results


# ============================================================================
# GOOGLE SERP SCRAPER
# ============================================================================

class GoogleSERPScraper(BaseScraper):
    SOURCE = "google_serp"
    RATE_LIMIT_RPS = 0.5

    async def scrape(self, query: str, location: str = None, max_results: int = 100) -> List[Dict]:
        results = []
        for start in range(0, min(max_results, 100), 10):
            search_url = f"https://www.google.com/search?q={query}+{location or ''}&start={start}&num=10"
            html = await self.fetch(search_url)
            if not html:
                break
            soup = BeautifulSoup(html, "html.parser")
            for div in soup.select("div.g"):
                title_el = div.select_one("h3")
                link_el = div.select_one("a")
                if title_el and link_el:
                    href = link_el.get("href", "")
                    if href.startswith("http") and "google.com" not in href:
                        results.append({
                            "company_name": title_el.get_text(strip=True),
                            "website": href,
                            "source": self.SOURCE,
                            "domain_fingerprint": normalize_domain(href),
                        })
            if len(results) >= max_results:
                break
        return results[:max_results]


# ============================================================================
# YELP SCRAPER
# ============================================================================

class YelpScraper(BaseScraper):
    SOURCE = "yelp"
    RATE_LIMIT_RPS = 0.5

    async def scrape(self, query: str, location: str = None, max_results: int = 100) -> List[Dict]:
        results = []
        loc = (location or "Houston-TX").replace(" ", "-")
        url = f"https://www.yelp.com/search?find_desc={query}&find_loc={loc}"
        html = await self.fetch(url)
        if not html:
            return results
        soup = BeautifulSoup(html, "html.parser")
        for card in soup.select("[data-testid='serp-ia-card']")[:max_results]:
            name_el = card.select_one("a[href*='/biz/'] span")
            link_el = card.select_one("a[href*='/biz/']")
            phone_el = card.select_one("p[class*='phone']")
            if name_el:
                results.append({
                    "company_name": name_el.get_text(strip=True),
                    "website": f"https://www.yelp.com{link_el.get('href', '')}" if link_el else None,
                    "phone": phone_el.get_text(strip=True) if phone_el else None,
                    "source": self.SOURCE,
                    "category": query,
                })
        return results


# ============================================================================
# GITHUB ORG SCRAPER
# ============================================================================

class GitHubScraper(BaseScraper):
    SOURCE = "github"
    RATE_LIMIT_RPS = 1.0

    async def scrape(self, query: str, location: str = None, max_results: int = 100) -> List[Dict]:
        """Scrape GitHub org pages for company tech signals."""
        results = []
        # GitHub search API is free, 10 req/min unauthenticated
        url = f"https://api.github.com/search/users?q={query}+type:org&per_page={min(max_results, 30)}"
        await self._rate_limit()
        try:
            resp = await self.client.get(url, headers={"Accept": "application/vnd.github.v3+json"})
            data = resp.json()
            for org in data.get("items", [])[:max_results]:
                org_url = f"https://api.github.com/orgs/{org['login']}"
                await self._rate_limit()
                org_resp = await self.client.get(org_url)
                org_data = org_resp.json()
                results.append({
                    "company_name": org_data.get("name") or org["login"],
                    "website": org_data.get("blog") or f"https://github.com/{org['login']}",
                    "source": self.SOURCE,
                    "category": "technology",
                    "employee_count": org_data.get("public_repos", 0),  # proxy signal
                    "address": org_data.get("location", ""),
                    "raw_data": {
                        "github_handle": org["login"],
                        "public_repos": org_data.get("public_repos"),
                        "followers": org_data.get("followers"),
                        "description": org_data.get("description"),
                    },
                })
        except Exception as e:
            logger.warning(f"[github] Search failed: {e}")
        return results


# ============================================================================
# PRODUCT HUNT SCRAPER
# ============================================================================

class ProductHuntScraper(BaseScraper):
    SOURCE = "product_hunt"
    RATE_LIMIT_RPS = 0.5

    async def scrape(self, query: str, location: str = None, max_results: int = 100) -> List[Dict]:
        results = []
        url = f"https://www.producthunt.com/search?q={query}"
        html = await self.fetch(url)
        if not html:
            return results
        soup = BeautifulSoup(html, "html.parser")
        for item in soup.select("[data-test='post-item']")[:max_results]:
            name = item.select_one("h3")
            link = item.select_one("a")
            desc = item.select_one("p")
            if name:
                results.append({
                    "company_name": name.get_text(strip=True),
                    "website": f"https://www.producthunt.com{link.get('href', '')}" if link else None,
                    "source": self.SOURCE,
                    "category": query,
                    "raw_data": {"description": desc.get_text(strip=True) if desc else ""},
                })
        return results


# ============================================================================
# SCRAPER REGISTRY
# ============================================================================

SCRAPER_REGISTRY = {
    "google_maps": GoogleMapsScraper,
    "google_serp": GoogleSERPScraper,
    "yelp": YelpScraper,
    "github": GitHubScraper,
    "product_hunt": ProductHuntScraper,
}

def get_scraper(source: str) -> BaseScraper:
    cls = SCRAPER_REGISTRY.get(source)
    if not cls:
        raise ValueError(f"Unknown scraper source: {source}")
    return cls()
