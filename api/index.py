"""Vercel Serverless Function - Giveaway Tracker API."""

import asyncio
import json
import os
from datetime import datetime, timedelta
from http.server import BaseHTTPRequestHandler
from urllib.parse import parse_qs, urlparse
import aiohttp

class Giveaway:
    """Модель раздачи."""
    def __init__(self, platform, title, price, url, end_date=None, image=None, desc=None, is_permanent=False):
        self.platform = platform
        self.title = title
        self.original_price = price
        self.discount_price = "Free"
        self.url = url
        self.end_date = end_date
        self.image_url = image
        self.description = desc
        self.is_permanent = is_permanent
        self.time_components = self._get_time() if end_date else {'days': 0, 'hours': 0, 'minutes': 0, 'seconds': 0, 'expired': False}
        self.is_expired = self._is_expired() if end_date else False

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
        return {
            'platform': self.platform, 
            'title': self.title, 
            'original_price': self.original_price, 
            'discount_price': self.discount_price, 
            'url': self.url, 
            'end_date': self.end_date, 
            'description': self.description, 
            'image_url': self.image_url, 
            'is_expired': self.is_expired, 
            'time_components': self.time_components,
            'is_permanent': self.is_permanent
        }


async def get_epic(session):
    """Epic Games Store - временные бесплатные игры."""
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
                        if discount == 0:
                            slug = game.get("productSlug", "")
                            ns = game.get("namespace", "")
                            title = game.get("title", "Unknown")
                            end = offer.get("endDate", "").split("T")[0] if offer.get("endDate") else None
                            price = offer.get("discountSetting", {}).get("originalPrice", 0)
                            
                            img = next((i.get("url") for i in game.get("keyImages", []) if i.get("type") in ["OfferImageWide", "Thumbnail", "DieselStoreFrontWide"]), None)
                            
                            url = "https://store.epicgames.com/"
                            if slug:
                                clean_slug = slug.split('/')[-1] if '/' in slug else slug
                                url = f"https://store.epicgames.com/ru/p/{clean_slug}"
                            elif ns:
                                url = f"https://store.epicgames.com/ru/search?q={title.replace(' ', '%20')}"
                            
                            result.append(Giveaway(
                                platform="Epic Games",
                                title=title,
                                price=f"${price:.2f}" if price else "N/A",
                                url=url,
                                end_date=end,
                                image=img,
                                desc=(game.get("description") or "")[:200],
                                is_permanent=False
                            ))
                            break
    except Exception as e:
        print(f"Epic error: {e}")
    return result


async def get_steam_specials(session):
    """Steam - игры со 100% скидкой через API."""
    result = []
    
    try:
        # Steam API для специальных предложений
        async with session.get(
            "https://store.steampowered.com/api/featuredcategories/",
            timeout=10
        ) as r:
            if r.status != 200:
                print(f"Steam API status: {r.status}")
                return result
            
            data = await r.json()
            
            # Ищем секции со скидками
            for key, section in data.items():
                if not isinstance(section, dict):
                    continue
                    
                items = section.get('items', [])
                if not items:
                    continue
                
                for item in items:
                    # Проверяем 100% скидку
                    discount = item.get('discount', 0)
                    if discount == 100:
                        appid = item.get('id', 0)
                        title = item.get('name', 'Unknown')
                        
                        # Изображение
                        header_img = item.get('header_image', '')
                        
                        # Оригинальная цена
                        orig_price = item.get('original_price', 0)
                        price_str = f"${orig_price/100:.2f}" if orig_price else "N/A"
                        
                        url = f"https://store.steampowered.com/app/{appid}/"
                        end_date = (datetime.now() + timedelta(days=7)).strftime("%Y-%m-%d")
                        
                        result.append(Giveaway(
                            platform="Steam",
                            title=title,
                            price=price_str,
                            url=url,
                            image=header_img,
                            desc="100% Off - Limited Time!",
                            end_date=end_date,
                            is_permanent=False
                        ))
    
    except Exception as e:
        print(f"Steam API error: {e}")
    
    # Если через API не получилось, пробуем через specials страницу
    if not result:
        result = await get_steam_specials_page(session)
    
    return result


async def get_steam_specials_page(session):
    """Steam - парсинг страницы special offers."""
    result = []
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "Accept": "text/html,application/xhtml+xml"
    }
    
    try:
        async with session.get(
            "https://store.steampowered.com/specials",
            headers=headers,
            timeout=10
        ) as r:
            if r.status != 200:
                return result
            
            from bs4 import BeautifulSoup
            html = await r.text()
            soup = BeautifulSoup(html, 'lxml')
            
            # Ищем игры с 100% скидкой
            for game in soup.select('.tab_item')[:30]:
                title_elem = game.select_one('.tab_item_name')
                discount_elem = game.select_one('.discount_pct')
                
                if not title_elem or not discount_elem:
                    continue
                
                discount_text = discount_elem.get_text(strip=True)
                
                if discount_text == "100%":
                    title = title_elem.get_text(strip=True)
                    
                    # Ссылка из data-ds-tag1
                    appid = game.get('data-ds-tag1', '')
                    if appid and appid.isdigit():
                        url = f"https://store.steampowered.com/app/{appid}/"
                    else:
                        link = game.select_one('a[href*="/app/"]')
                        url = link.get('href') if link else "https://store.steampowered.com/"
                    
                    # Цена
                    price_elem = game.select_one('.discount_original_price')
                    orig_price = price_elem.get_text(strip=True) if price_elem else "N/A"
                    
                    # Изображение
                    img_elem = game.select_one('img')
                    img_url = img_elem.get('src') if img_elem else None
                    
                    end_date = (datetime.now() + timedelta(days=7)).strftime("%Y-%m-%d")
                    
                    result.append(Giveaway(
                        platform="Steam",
                        title=title,
                        price=orig_price,
                        url=url,
                        image=img_url,
                        desc="100% Off!",
                        end_date=end_date,
                        is_permanent=False
                    ))
    
    except Exception as e:
        print(f"Steam page error: {e}")
    
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
            HTML_TEMPLATE = "<html><body><h1>Error</h1></body></html>"
    return HTML_TEMPLATE


class handler(BaseHTTPRequestHandler):
    """HTTP Request Handler for Vercel."""
    
    def do_GET(self):
        parsed = urlparse(self.path)
        path = parsed.path
        
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
            stats = {'total': len(giveaways), 'by_platform': {}, 'permanent': 0, 'limited': 0, 'expired': 0}
            for g in giveaways:
                stats['by_platform'][g['platform']] = stats['by_platform'].get(g['platform'], 0) + 1
                if g['is_permanent']:
                    stats['permanent'] += 1
                elif g['is_expired']:
                    stats['expired'] += 1
                else:
                    stats['limited'] += 1
            self.wfile.write(json.dumps(stats).encode())
        
        else:
            template = get_template()
            self.send_response(200)
            self.send_header('Content-Type', 'text/html; charset=utf-8')
            self.send_header('Cache-Control', 'no-cache')
            self.end_headers()
            self.wfile.write(template.encode('utf-8'))
    
    async def _collect_giveaways(self):
        """Собрать все временные раздачи."""
        async with aiohttp.ClientSession() as session:
            results = await asyncio.gather(
                get_epic(session),
                get_steam_specials(session),
                return_exceptions=True
            )
            all_games = []
            for r in results:
                if isinstance(r, list):
                    all_games.extend(r)
            # Удаляем дубликаты
            seen, unique = set(), []
            for g in all_games:
                if g.url not in seen:
                    seen.add(g.url)
                    unique.append(g)
            return [g.to_dict() for g in unique]
    
    def log_message(self, format, *args):
        print(f"{self.address_string()} - {format % args}")
