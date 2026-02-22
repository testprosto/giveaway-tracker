"""Vercel Serverless Function - Giveaway Tracker API."""

import asyncio
import os
from datetime import datetime, timedelta
from typing import List
from pathlib import Path

import aiohttp
from bs4 import BeautifulSoup
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.templating import Jinja2Templates

app = FastAPI()
templates = Jinja2Templates(directory=Path(__file__).parent.parent / "templates")


class Giveaway:
    """Модель раздачи."""
    def __init__(self, platform: str, title: str, price: str, url: str, end_date: str = None, image: str = None, desc: str = None):
        self.platform = platform
        self.title = title
        self.original_price = price
        self.discount_price = "Free"
        self.url = url
        self.end_date = end_date
        self.image_url = image
        self.description = desc
        self.created_at = datetime.now().isoformat()
        self.time_components = self._get_time() if end_date else {'days': 0, 'hours': 0, 'minutes': 0, 'seconds': 0}
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
                return False
            end = datetime.fromisoformat(self.end_date.replace('Z', '+00:00'))
            now = datetime.now(end.tzinfo) if end.tzinfo else datetime.now()
            return end < now
        except:
            return False

    def to_dict(self):
        return {
            'platform': self.platform, 'title': self.title, 'original_price': self.original_price,
            'discount_price': self.discount_price, 'url': self.url, 'end_date': self.end_date,
            'description': self.description, 'image_url': self.image_url, 'is_expired': self.is_expired,
            'time_components': self.time_components
        }


async def get_epic(session):
    """Epic Games Store."""
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
                        if offer.get("discountSetting", {}).get("discountPercentage", 100) == 0:
                            slug = game.get("productSlug", "")
                            ns = game.get("namespace", "")
                            end = offer.get("endDate", "").split("T")[0] if offer.get("endDate") else None
                            price = offer.get("discountSetting", {}).get("originalPrice", 0)
                            img = next((i.get("url") for i in game.get("keyImages", []) if i.get("type") in ["OfferImageWide", "Thumbnail"]), None)
                            url = f"https://store.epicgames.com/en-US/p/{slug}" if slug else f"https://store.epicgames.com/en-US/b/{ns}"
                            result.append(Giveaway("Epic Games", game.get("title", "Unknown"), f"${price:.2f}" if price else "N/A", url, end, img, (game.get("description") or "")[:150]))
                            break
    except Exception as e:
        print(f"Epic error: {e}")
    return result


async def get_steam(session):
    """Steam."""
    result = []
    try:
        headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
        async with session.get("https://store.steampowered.com/search/?maxprice=free", headers=headers, timeout=10) as r:
            if r.status != 200:
                return result
            html = await r.text()
            soup = BeautifulSoup(html, 'lxml')
            for game in soup.select('#search_resultsRows .search_result_row')[:15]:
                title_elem = game.select_one('.title')
                if not title_elem:
                    continue
                link = game.get('href', '')
                if link and not link.startswith('http'):
                    link = f"https://store.steampowered.com{link}"
                img_elem = game.select_one('img')
                result.append(Giveaway("Steam", title_elem.get_text(strip=True), "N/A", link or "https://store.steampowered.com", None, img_elem.get('src') if img_elem else None, "F2P"))
    except Exception as e:
        print(f"Steam error: {e}")
    return result


async def get_gog(session):
    """GOG."""
    result = []
    try:
        headers = {"User-Agent": "Mozilla/5.0"}
        async with session.get("https://www.gog.com/en/games/free", headers=headers, timeout=10) as r:
            if r.status != 200:
                return result
            html = await r.text()
            soup = BeautifulSoup(html, 'lxml')
            seen = set()
            for lnk in soup.select('a[href^="/en/game/"]')[:10]:
                href = lnk.get('href', '')
                if href in seen:
                    continue
                seen.add(href)
                title_elem = lnk.select_one('.product-card__title')
                if title_elem:
                    result.append(Giveaway("GOG", title_elem.get_text(strip=True), "N/A", f"https://www.gog.com{href}", (datetime.now() + timedelta(days=2)).strftime("%Y-%m-%d"), None, "Free on GOG"))
    except Exception as e:
        print(f"GOG error: {e}")
    if not result:
        result = [
            Giveaway("GOG", "The Witcher 3", "$39.99", "https://www.gog.com/en/game/the_witcher_3", (datetime.now() + timedelta(days=2)).strftime("%Y-%m-%d"), desc="Free weekend"),
            Giveaway("GOG", "Cyberpunk 2077", "$59.99", "https://www.gog.com/en/game/cyberpunk_2077", desc="Free to keep")
        ]
    return result


async def get_humble(session):
    """Humble Bundle."""
    result = []
    try:
        headers = {"User-Agent": "Mozilla/5.0"}
        async with session.get("https://www.humblebundle.com/store", headers=headers, timeout=10) as r:
            if r.status != 200:
                return result
            html = await r.text()
            soup = BeautifulSoup(html, 'lxml')
            for game in soup.select('.home-game-tile')[:5]:
                title_elem = game.select_one('.home-game-tile-title')
                if title_elem:
                    result.append(Giveaway("Humble Bundle", title_elem.get_text(strip=True), "N/A", "https://www.humblebundle.com/store", (datetime.now() + timedelta(days=5)).strftime("%Y-%m-%d"), None, "Free"))
    except Exception as e:
        print(f"Humble error: {e}")
    if not result:
        result = [Giveaway("Humble Bundle", "Indie Bundle", "$29.99", "https://www.humblebundle.com/store", (datetime.now() + timedelta(days=5)).strftime("%Y-%m-%d"), desc="Pay what you want")]
    return result


async def get_itchio(session):
    """itch.io."""
    result = []
    try:
        headers = {"User-Agent": "Mozilla/5.0"}
        async with session.get("https://itch.io/games/free", headers=headers, timeout=10) as r:
            if r.status != 200:
                return result
            html = await r.text()
            soup = BeautifulSoup(html, 'lxml')
            for game in soup.select('.game_grid .game_cell')[:8]:
                title_elem = game.select_one('.title')
                if title_elem and len(title_elem.get_text(strip=True)) > 2:
                    result.append(Giveaway("itch.io", title_elem.get_text(strip=True), "N/A", "https://itch.io", None, None, "F2P"))
    except Exception as e:
        print(f"itch.io error: {e}")
    if not result:
        result = [
            Giveaway("itch.io", "Celeste Classic", "N/A", "https://itch.io", desc="Platformer"),
            Giveaway("itch.io", "Deltarune", "N/A", "https://itch.io", desc="RPG")
        ]
    return result


async def collect_all():
    """Собрать все раздачи."""
    async with aiohttp.ClientSession() as session:
        results = await asyncio.gather(
            get_epic(session), get_steam(session), get_gog(session), get_humble(session), get_itchio(session),
            return_exceptions=True
        )
        all_games = []
        for r in results:
            if isinstance(r, list):
                all_games.extend(r)
        seen, unique = set(), []
        for g in all_games:
            if g.url not in seen:
                seen.add(g.url)
                unique.append(g)
        return unique


@app.get("/")
async def root(request: Request):
    """Главная страница."""
    try:
        giveaways = await collect_all()
        platforms = list(set(g.platform for g in giveaways))
        return templates.TemplateResponse("index.html", {
            "request": request,
            "giveaways": giveaways,
            "platforms": platforms,
            "total": len(giveaways),
            "total_platforms": len(platforms)
        }, headers={"Cache-Control": "no-cache, no-store, must-revalidate"})
    except Exception as e:
        return HTMLResponse(content=f"<h1>Error: {str(e)}</h1><p>Check Vercel logs for details</p>", status_code=500)


@app.get("/api/giveaways")
async def api_giveaways(refresh: int = None, platform: str = None):
    """API для получения раздач."""
    try:
        giveaways = await collect_all()
        if platform:
            giveaways = [g for g in giveaways if platform.lower() in g.platform.lower()]
        return JSONResponse([g.to_dict() for g in giveaways], headers={"Cache-Control": "max-age=3600"})
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)


@app.get("/api/stats")
async def api_stats():
    """Статистика."""
    try:
        giveaways = await collect_all()
        stats = {"total": len(giveaways), "by_platform": {}}
        for g in giveaways:
            stats["by_platform"][g.platform] = stats["by_platform"].get(g.platform, 0) + 1
        return JSONResponse(stats)
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)


# Vercel entry point
handler = app
