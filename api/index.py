"""Vercel Serverless Function - Giveaway Tracker API."""

import asyncio
import json
import os
from datetime import datetime, timedelta
from http.server import BaseHTTPRequestHandler
from urllib.parse import parse_qs, urlparse
import aiohttp
from bs4 import BeautifulSoup

class Giveaway:
    """Модель раздачи."""
    def __init__(self, platform, title, price, url, end_date, image=None, desc=None):
        self.platform = platform
        self.title = title
        self.original_price = price
        self.discount_price = "Free"
        self.url = url
        self.end_date = end_date
        self.image_url = image
        self.description = desc
        self.time_components = self._get_time()
        self.is_expired = self._is_expired()

    def _get_time(self):
        try:
            end = datetime.fromisoformat(self.end_date.replace('Z', '+00:00'))
            now = datetime.now(end.tzinfo) if end.tzinfo else datetime.now()
            diff = end - now
            ts = max(0, int(diff.total_seconds()))
            return {'days': ts//86400, 'hours': (ts%86400)//3600, 'minutes': (ts%3600)//60, 'seconds': ts%60, 'expired': ts<=0}
        except:
            return {'days': 0, 'hours': 0, 'minutes': 0, 'seconds': 0, 'expired': True}

    def _is_expired(self):
        try:
            if not self.end_date:
                return True
            end = datetime.fromisoformat(self.end_date.replace('Z', '+00:00'))
            now = datetime.now(end.tzinfo) if end.tzinfo else datetime.now()
            return end < now
        except:
            return True

    def to_dict(self):
        return {'platform': self.platform, 'title': self.title, 'original_price': self.original_price, 'discount_price': self.discount_price, 'url': self.url, 'end_date': self.end_date, 'description': self.description, 'image_url': self.image_url, 'is_expired': self.is_expired, 'time_components': self.time_components}


async def get_epic(session):
    """Epic Games Store - только временные бесплатные игры."""
    result = []
    try:
        async with session.get("https://store-site-backend-static.ak.epicgames.com/freeGamesPromotions", timeout=10) as r:
            if r.status != 200:
                return result
            data = await r.json()
            for game in data.get("data", {}).get("Catalog", {}).get("searchStore", {}).get("elements", []):
                promos = game.get("promotions")
                if not promos:
                    continue
                for og in promos.get("promotionalOffers", []):
                    for offer in og.get("promotionalOffers", []):
                        discount = offer.get("discountSetting", {}).get("discountPercentage", 100)
                        # Только 100% скидки (бесплатно)
                        if discount == 0:
                            slug = game.get("productSlug", "")
                            ns = game.get("namespace", "")
                            end = offer.get("endDate", "").split("T")[0] if offer.get("endDate") else None
                            price = offer.get("discountSetting", {}).get("originalPrice", 0)
                            
                            # Получаем изображение
                            img = None
                            for i in game.get("keyImages", []):
                                if i.get("type") in ["OfferImageWide", "Thumbnail", "DieselStoreFrontWide"]:
                                    img = i.get("url")
                                    break
                            
                            # Формируем URL
                            if slug:
                                clean_slug = slug.split('/')[-1] if '/' in slug else slug
                                url = f"https://store.epicgames.com/en-US/p/{clean_slug}"
                            elif ns:
                                url = f"https://store.epicgames.com/en-US/b/{ns}"
                            else:
                                url = "https://store.epicgames.com/"
                            
                            result.append(Giveaway(
                                platform="Epic Games",
                                title=game.get("title", "Unknown"),
                                price=f"${price:.2f}" if price else "N/A",
                                url=url,
                                end_date=end,
                                image=img,
                                desc=(game.get("description") or "")[:200]
                            ))
                            break
    except Exception as e:
        print(f"Epic error: {e}")
    return result


# Load HTML template
HTML_TEMPLATE = None
def get_template():
    global HTML_TEMPLATE
    if HTML_TEMPLATE is None:
        template_path = os.path.join(os.path.dirname(__file__), '..', 'templates', 'index.html')
        try:
            with open(template_path, 'r', encoding='utf-8') as f:
                HTML_TEMPLATE = f.read()
        except:
            HTML_TEMPLATE = "<html><body><h1>Error loading template</h1></body></html>"
    return HTML_TEMPLATE


class handler(BaseHTTPRequestHandler):
    """HTTP Request Handler for Vercel."""
    
    def do_GET(self):
        parsed = urlparse(self.path)
        path = parsed.path
        query = parse_qs(parsed.query)
        
        if path == '/api/giveaways':
            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.send_header('Cache-Control', 'max-age=300')
            self.end_headers()
            giveaways = asyncio.run(self._collect_giveaways())
            self.wfile.write(json.dumps(giveaways).encode())
        
        elif path == '/api/stats':
            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.end_headers()
            giveaways = asyncio.run(self._collect_giveaways())
            stats = {'total': len(giveaways), 'by_platform': {}}
            for g in giveaways:
                stats['by_platform'][g.platform] = stats['by_platform'].get(g.platform, 0) + 1
            self.wfile.write(json.dumps(stats).encode())
        
        else:
            template = get_template()
            self.send_response(200)
            self.send_header('Content-Type', 'text/html; charset=utf-8')
            self.send_header('Cache-Control', 'no-cache')
            self.end_headers()
            self.wfile.write(template.encode('utf-8'))
    
    async def _collect_giveaways(self):
        """Собрать только временные раздачи (Epic Games)."""
        async with aiohttp.ClientSession() as session:
            results = await asyncio.gather(get_epic(session), return_exceptions=True)
            all_games = []
            for r in results:
                if isinstance(r, list):
                    all_games.extend(r)
            # Удаляем дубликаты и истёкшие
            seen, unique = set(), []
            for g in all_games:
                if g.url not in seen and not g.is_expired:
                    seen.add(g.url)
                    unique.append(g)
            return [g.to_dict() for g in unique]
    
    def log_message(self, format, *args):
        print(f"{self.address_string()} - {format % args}")
