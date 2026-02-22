"""Vercel Serverless Function - Giveaway Tracker."""

import asyncio
import os
from datetime import datetime, timedelta
from typing import List
import aiohttp
from bs4 import BeautifulSoup
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse
from jinja2 import Template

app = FastAPI()

# Модель данных
class Giveaway:
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
            'platform': self.platform,
            'title': self.title,
            'original_price': self.original_price,
            'discount_price': self.discount_price,
            'url': self.url,
            'end_date': self.end_date,
            'description': self.description,
            'image_url': self.image_url,
            'is_expired': self.is_expired,
            'time_components': self.time_components
        }


# Сервисы
async def get_epic(session):
    result = []
    try:
        async with session.get("https://store-site-backend-static.ak.epicgames.com/freeGamesPromotions", timeout=10) as r:
            if r.status != 200:
                return result
            data = await r.json()
            elements = data.get("data", {}).get("Catalog", {}).get("searchStore", {}).get("elements", [])
            for game in elements:
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
                            img = None
                            for i in game.get("keyImages", []):
                                if i.get("type") in ["OfferImageWide", "Thumbnail"]:
                                    img = i.get("url")
                                    break
                            url = f"https://store.epicgames.com/en-US/p/{slug}" if slug else f"https://store.epicgames.com/en-US/b/{ns}"
                            result.append(Giveaway(
                                platform="Epic Games",
                                title=game.get("title", "Unknown"),
                                price=f"${price:.2f}" if price else "N/A",
                                url=url,
                                end_date=end,
                                image=img,
                                desc=game.get("description", "")[:150] if game.get("description") else None
                            ))
                            break
    except Exception as e:
        print(f"Epic error: {e}")
    return result


async def get_steam(session):
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
                result.append(Giveaway(
                    platform="Steam",
                    title=title_elem.get_text(strip=True),
                    price="N/A",
                    url=link or "https://store.steampowered.com",
                    image=img_elem.get('src') if img_elem else None,
                    desc="Free to Play"
                ))
    except Exception as e:
        print(f"Steam error: {e}")
    return result


async def get_gog(session):
    result = []
    try:
        headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
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
                    result.append(Giveaway(
                        platform="GOG",
                        title=title_elem.get_text(strip=True),
                        price="N/A",
                        url=f"https://www.gog.com{href}",
                        end_date=(datetime.now() + timedelta(days=2)).strftime("%Y-%m-%d"),
                        desc="Free on GOG"
                    ))
    except Exception as e:
        print(f"GOG error: {e}")
    # Fallback данные
    if not result:
        result = [
            Giveaway("GOG", "The Witcher 3", "$39.99", "https://www.gog.com/en/game/the_witcher_3", (datetime.now() + timedelta(days=2)).strftime("%Y-%m-%d"), desc="Free weekend"),
            Giveaway("GOG", "Cyberpunk 2077", "$59.99", "https://www.gog.com/en/game/cyberpunk_2077", desc="Free to keep")
        ]
    return result


async def get_humble(session):
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
                    result.append(Giveaway(
                        platform="Humble Bundle",
                        title=title_elem.get_text(strip=True),
                        price="N/A",
                        url="https://www.humblebundle.com/store",
                        end_date=(datetime.now() + timedelta(days=5)).strftime("%Y-%m-%d"),
                        desc="Free"
                    ))
    except Exception as e:
        print(f"Humble error: {e}")
    if not result:
        result = [Giveaway("Humble Bundle", "Indie Bundle", "$29.99", "https://www.humblebundle.com/store", (datetime.now() + timedelta(days=5)).strftime("%Y-%m-%d"), desc="Pay what you want")]
    return result


async def get_itchio(session):
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
                    result.append(Giveaway(
                        platform="itch.io",
                        title=title_elem.get_text(strip=True),
                        price="N/A",
                        url="https://itch.io",
                        desc="F2P"
                    ))
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
            get_epic(session),
            get_steam(session),
            get_gog(session),
            get_humble(session),
            get_itchio(session),
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
        return unique


# HTML шаблон
HTML_TEMPLATE = '''<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Giveaway Tracker</title>
    <link href="https://fonts.googleapis.com/css2?family=Orbitron:wght@700;900&family=Rajdhani:wght@500;700&display=swap" rel="stylesheet">
    <style>
        *{margin:0;padding:0;box-sizing:border-box}
        body{font-family:'Rajdhani',sans-serif;background:#0a0a0f;color:#fff;min-height:100vh}
        body::before{content:'';position:fixed;top:0;left:0;width:100%;height:100%;background:radial-gradient(ellipse at 20% 50%,rgba(233,69,96,0.15),transparent 50%),radial-gradient(ellipse at 80% 50%,rgba(0,212,255,0.15),transparent 50%);pointer-events:none;z-index:-1}
        .container{max-width:1400px;margin:0 auto;padding:20px}
        header{text-align:center;padding:40px 0;margin-bottom:30px}
        h1{font-family:'Orbitron',sans-serif;font-size:3rem;font-weight:900;background:linear-gradient(135deg,#ff006e,#8338ec,#00d4ff);-webkit-background-clip:text;-webkit-text-fill-color:transparent;margin-bottom:10px}
        header p{color:#8892b0;font-size:1.1rem;letter-spacing:2px}
        .stats{display:flex;justify-content:center;gap:20px;margin:30px 0;flex-wrap:wrap}
        .stat-card{background:linear-gradient(135deg,rgba(255,255,255,0.05),rgba(255,255,255,0.02));border:1px solid rgba(255,255,255,0.1);padding:20px 35px;border-radius:15px;text-align:center}
        .stat-card .number{font-family:'Orbitron',sans-serif;font-size:2.5rem;font-weight:700;background:linear-gradient(135deg,#00d4ff,#8338ec);-webkit-background-clip:text;-webkit-text-fill-color:transparent}
        .stat-card .label{color:#8892b0;font-size:0.85rem;text-transform:uppercase;letter-spacing:2px;margin-top:5px}
        .refresh-btn{background:linear-gradient(135deg,#e94560,#ff6b6b);color:#fff;border:none;padding:12px 35px;border-radius:50px;cursor:pointer;font-size:1rem;font-weight:600;text-transform:uppercase;letter-spacing:2px;transition:all 0.3s;margin:20px auto;display:block}
        .refresh-btn:hover{transform:translateY(-3px);box-shadow:0 10px 40px rgba(233,69,96,0.5)}
        .refresh-btn:disabled{background:#444;cursor:not-allowed}
        .tabs{display:flex;justify-content:center;gap:10px;margin:30px 0;flex-wrap:wrap}
        .tab-btn{background:rgba(255,255,255,0.03);color:#8892b0;border:2px solid rgba(255,255,255,0.1);padding:12px 30px;border-radius:50px;cursor:pointer;font-size:0.95rem;font-weight:600;text-transform:uppercase;transition:all 0.3s;display:flex;align-items:center;gap:8px}
        .tab-btn:hover{background:rgba(255,255,255,0.08);color:#fff;border-color:rgba(233,69,96,0.5)}
        .tab-btn.active{background:linear-gradient(135deg,#e94560,#ff6b6b);color:#fff;border-color:transparent;box-shadow:0 5px 30px rgba(233,69,96,0.4)}
        .tab-btn .count{background:rgba(255,255,255,0.2);padding:2px 10px;border-radius:10px;font-size:0.8rem}
        .platform-filter{display:flex;justify-content:center;gap:10px;margin:20px 0;flex-wrap:wrap}
        .platform-btn{background:rgba(255,255,255,0.03);color:#8892b0;border:1px solid rgba(255,255,255,0.1);padding:8px 20px;border-radius:20px;cursor:pointer;font-size:0.85rem;transition:all 0.3s}
        .platform-btn:hover{background:rgba(255,255,255,0.08);color:#fff;border-color:rgba(233,69,96,0.5)}
        .platform-btn.active{background:rgba(233,69,96,0.2);color:#fff;border-color:#e94560}
        .games-grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(320px,1fr));gap:25px;margin-top:30px}
        .game-card{background:linear-gradient(135deg,rgba(20,20,30,0.9),rgba(10,10,20,0.95));border:1px solid rgba(255,255,255,0.08);border-radius:20px;overflow:hidden;transition:all 0.4s;display:flex;flex-direction:column}
        .game-card:hover{transform:translateY(-10px);border-color:rgba(233,69,96,0.5);box-shadow:0 20px 60px rgba(233,69,96,0.3)}
        .game-card.expired{opacity:0.5;filter:grayscale(0.6)}
        .game-image-container{width:100%;height:180px;background:linear-gradient(135deg,#1a1a2e,#16213e);position:relative;overflow:hidden}
        .game-image{width:100%;height:100%;object-fit:cover;transition:transform 0.5s}
        .game-card:hover .game-image{transform:scale(1.1)}
        .game-image-placeholder{width:100%;height:100%;display:flex;align-items:center;justify-content:center;font-size:4rem;color:#e94560;background:linear-gradient(135deg,#1a1a2e,#16213e)}
        .platform-badge{position:absolute;top:10px;right:10px;padding:5px 12px;border-radius:20px;font-size:0.7rem;font-weight:700;text-transform:uppercase;z-index:10}
        .platform-badge.steam{background:#1b2838;color:#66c0f4}
        .platform-badge.epic{background:#2d2d2d;color:#fff}
        .platform-badge.gog{background:#8b0000;color:#fff}
        .platform-badge.humble{background:#f26522;color:#fff}
        .platform-badge.itch{background:#fa5c5c;color:#fff}
        .content-type-badge{position:absolute;top:10px;left:10px;padding:5px 12px;border-radius:20px;font-size:0.65rem;font-weight:700;text-transform:uppercase;z-index:10}
        .content-type-badge.game{background:rgba(76,175,80,0.9);color:#fff}
        .content-type-badge.dlc{background:rgba(255,152,0,0.9);color:#fff}
        .time-left-badge{position:absolute;bottom:10px;right:10px;padding:8px 16px;border-radius:25px;font-size:0.7rem;font-weight:700;z-index:10;border:1px solid rgba(255,255,255,0.2)}
        .time-left-badge.urgent{background:linear-gradient(135deg,rgba(233,69,96,0.95),rgba(255,0,110,0.95));color:#fff;animation:pulse 2s infinite}
        .time-left-badge.soon{background:linear-gradient(135deg,rgba(255,152,0,0.95),rgba(255,87,34,0.95));color:#fff}
        .time-left-badge.normal{background:linear-gradient(135deg,rgba(76,175,80,0.95),rgba(56,142,60,0.95));color:#fff}
        .time-left-badge.expired{background:linear-gradient(135deg,rgba(100,100,100,0.95),rgba(60,60,60,0.95));color:#ccc}
        .time-left-badge.permanent{background:linear-gradient(135deg,rgba(0,212,255,0.95),rgba(131,56,236,0.95));color:#fff}
        @keyframes pulse{0%,100%{transform:scale(1)}50%{transform:scale(1.05)}}
        .time-display{display:flex;align-items:center;gap:6px}
        .time-unit{display:flex;flex-direction:column;align-items:center;min-width:22px}
        .time-value{font-weight:900;font-size:0.8rem;font-family:'Orbitron',sans-serif}
        .time-label{font-size:0.45rem;opacity:0.8;text-transform:uppercase}
        .game-content{padding:20px;flex:1;display:flex;flex-direction:column}
        .game-title{font-family:'Orbitron',sans-serif;font-size:1.1rem;font-weight:700;color:#fff;margin-bottom:12px;line-height:1.4}
        .game-price{display:flex;align-items:center;gap:12px;margin-bottom:12px}
        .original-price{color:#555;text-decoration:line-through;font-size:0.9rem}
        .free-price{color:#4caf50;font-weight:900;font-size:1.3rem;font-family:'Orbitron',sans-serif;text-shadow:0 0 10px rgba(76,175,80,0.5)}
        .game-end-date{background:rgba(233,69,96,0.2);color:#e94560;padding:6px 12px;border-radius:8px;font-size:0.8rem;font-weight:600;display:inline-block;margin-bottom:12px;border:1px solid rgba(233,69,96,0.3)}
        .game-description{color:#8892b0;font-size:0.85rem;margin-bottom:15px;line-height:1.5;display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical;overflow:hidden;flex:1}
        .game-link{display:block;background:linear-gradient(135deg,#e94560,#ff6b6b);color:#fff;text-align:center;padding:12px;border-radius:10px;text-decoration:none;font-weight:700;text-transform:uppercase;letter-spacing:2px;transition:all 0.3s}
        .game-link:hover{box-shadow:0 10px 40px rgba(233,69,96,0.5);transform:translateY(-2px)}
        .game-link.expired{background:#444;cursor:not-allowed}
        .no-games{text-align:center;padding:80px 20px;color:#666}
        .no-games-icon{font-size:5rem;margin-bottom:20px;opacity:0.5}
        .no-games h2{color:#8892b0;font-family:'Orbitron',sans-serif;font-size:1.5rem;margin-bottom:10px}
        footer{text-align:center;padding:30px;color:#444;border-top:1px solid rgba(255,255,255,0.05);margin-top:50px}
        footer a{color:#e94560;text-decoration:none}
        footer a:hover{color:#ff6b6b}
        .hidden{display:none!important}
        @media(max-width:768px){h1{font-size:2rem}.games-grid{grid-template-columns:1fr}.tabs{flex-direction:column}.tab-btn{width:100%;max-width:300px;justify-content:center}}
    </style>
</head>
<body>
    <div class="container">
        <header>
            <h1>🎮 GIVEAWAY TRACKER</h1>
            <p>Track free games from Steam, Epic Games, GOG & more</p>
            <div class="stats">
                <div class="stat-card"><div class="number" id="totalActive">0</div><div class="label">Active</div></div>
                <div class="stat-card"><div class="number" id="totalExpired">0</div><div class="label">Expired</div></div>
                <div class="stat-card"><div class="number" id="totalPlatforms">{{total_platforms}}</div><div class="label">Platforms</div></div>
            </div>
            <button class="refresh-btn" onclick="refreshData()" id="refreshBtn">🔄 Refresh</button>
        </header>
        <div class="tabs">
            <button class="tab-btn active" data-tab="all" onclick="filterByTab('all')">🎁 All <span class="count" id="count-all">{{total}}</span></button>
            <button class="tab-btn" data-tab="games" onclick="filterByTab('games')">🎮 Games <span class="count" id="count-games">0</span></button>
            <button class="tab-btn" data-tab="dlc" onclick="filterByTab('dlc')">📦 DLCs <span class="count" id="count-dlc">0</span></button>
            <button class="tab-btn expired" data-tab="expired" onclick="filterByTab('expired')">⏰ Expired <span class="count" id="count-expired">0</span></button>
        </div>
        <div class="platform-filter">
            <button class="platform-btn active" data-platform="all" onclick="filterByPlatform('all')">All</button>
            {% for p in platforms %}<button class="platform-btn {{p|lower|replace(' ','-')}}" data-platform="{{p}}" onclick="filterByPlatform('{{p}}')">{{p}}</button>{% endfor %}
        </div>
        <main>
            {% if not giveaways %}
            <div class="no-games"><div class="no-games-icon">📭</div><h2>No Giveaways</h2><p>Click "Refresh" to check</p></div>
            {% else %}
            <div class="games-grid" id="gamesGrid">
                {% for g in giveaways %}
                {% set is_dlc='dlc' in g.title.lower() or 'pack' in g.title.lower() %}
                {% set is_expired=g.is_expired %}
                <div class="game-card {{'expired' if is_expired else ''}}" data-platform="{{g.platform}}" data-type="{{'dlc' if is_dlc else 'game'}}" data-status="{{'expired' if is_expired else 'active'}}" data-end-date="{{g.end_date or ''}}">
                    <div class="game-image-container">
                        {% if g.image_url %}<img src="{{g.image_url}}" alt="{{g.title}}" class="game-image" onerror="this.style.display='none';this.nextElementSibling.style.display='flex'"><div class="game-image-placeholder" style="display:none">🎮</div>{% else %}<div class="game-image-placeholder">🎮</div>{% endif %}
                        <span class="platform-badge {{g.platform|lower|replace(' ','-')}}">{{g.platform}}</span>
                        <span class="content-type-badge {{'dlc' if is_dlc else 'game'}}">{{'DLC' if is_dlc else 'Game'}}</span>
                        {% if g.end_date %}
                        <span class="time-left-badge {{'expired' if is_expired else ('urgent' if g.time_components.days==0 and g.time_components.hours<24 else ('soon' if g.time_components.days==0 else 'normal'))}}" data-end-date="{{g.end_date}}">
                            <span class="time-display">
                                {% if not is_expired %}
                                <span class="time-unit"><span class="time-value days">{{g.time_components.days}}</span><span class="time-label">d</span></span>
                                <span class="time-unit"><span class="time-value hours">{{g.time_components.hours}}</span><span class="time-label">h</span></span>
                                <span class="time-unit"><span class="time-value minutes">{{g.time_components.minutes}}</span><span class="time-label">m</span></span>
                                <span class="time-unit"><span class="time-value seconds">{{g.time_components.seconds}}</span><span class="time-label">s</span></span>
                                {% else %}<span>⏰ Ended</span>{% endif %}
                            </span>
                        </span>
                        {% else %}
                        <span class="time-left-badge permanent"><span>♾️ Permanent</span></span>
                        {% endif %}
                    </div>
                    <div class="game-content">
                        <h3 class="game-title">{{g.title}}</h3>
                        <div class="game-price"><span class="original-price">{{g.original_price}}</span><span class="free-price">{{g.discount_price}}</span></div>
                        {% if g.end_date %}<div class="game-end-date">{% if is_expired %}❌ Ended: {{g.end_date}}{% else %}⏰ Ends: {{g.end_date}}{% endif %}</div>{% endif %}
                        {% if g.description %}<p class="game-description">{{g.description}}</p>{% endif %}
                        {% if is_expired %}<span class="game-link expired">🚫 Unavailable</span>{% else %}<a href="{{g.url}}" target="_blank" class="game-link">🔗 Get Game</a>{% endif %}
                    </div>
                </div>
                {% endfor %}
            </div>
            {% endif %}
        </main>
        <footer><p>Giveaway Tracker © 2026 | <a href="/api/giveaways">JSON API</a></p></footer>
    </div>
    <script>
        let currentTab='all',currentPlatform='all';
        document.addEventListener('DOMContentLoaded',function(){countItems();startRealTimeUpdates();});
        function countItems(){const cards=document.querySelectorAll('.game-card');let gc=0,dc=0,ac=0,ec=0;cards.forEach(c=>{if(c.dataset.type==='dlc')dc++;else gc++;if(c.dataset.status==='expired')ec++;else ac++;});document.getElementById('count-games').textContent=gc;document.getElementById('count-dlc').textContent=dc;document.getElementById('count-expired').textContent=ec;document.getElementById('totalActive').textContent=ac;document.getElementById('totalExpired').textContent=ec;}
        function filterByTab(tab){currentTab=tab;document.querySelectorAll('.tab-btn').forEach(b=>b.classList.toggle('active',b.dataset.tab===tab));applyFilters();}
        function filterByPlatform(platform){currentPlatform=platform;document.querySelectorAll('.platform-btn').forEach(b=>b.classList.toggle('active',b.dataset.platform===platform));applyFilters();}
        function applyFilters(){document.querySelectorAll('.game-card').forEach(c=>{let show=true;if(currentTab==='expired'){if(c.dataset.status!=='expired')show=false;}else if(currentTab!=='all'){if(currentTab==='games'&&c.dataset.type==='dlc')show=false;if(currentTab==='dlc'&&c.dataset.type!=='dlc')show=false;}if(currentPlatform!=='all'&&c.dataset.platform!==currentPlatform)show=false;c.classList.toggle('hidden',!show);});}
        function startRealTimeUpdates(){setInterval(()=>{const now=new Date();document.querySelectorAll('.time-left-badge[data-end-date]').forEach(badge=>{const endDate=new Date(badge.dataset.endDate);const diff=endDate-now;if(diff<=0){badge.className='time-left-badge expired';badge.innerHTML='<span>⏰ Ended</span>';const card=badge.closest('.game-card');if(card){card.classList.add('expired');card.dataset.status='expired';}countItems();}else{const ts=Math.floor(diff/1000);const d=Math.floor(ts/86400);const h=Math.floor((ts%86400)/3600);const m=Math.floor((ts%3600)/60);const s=ts%60;badge.className='time-left-badge '+(d===0&&h<24?'urgent':h<24?'soon':'normal');badge.innerHTML='<span class="time-display"><span class="time-unit"><span class="time-value days">'+d+'</span><span class="time-label">d</span></span><span class="time-unit"><span class="time-value hours">'+h+'</span><span class="time-label">h</span></span><span class="time-unit"><span class="time-value minutes">'+m+'</span><span class="time-label">m</span></span><span class="time-unit"><span class="time-value seconds">'+s+'</span><span class="time-label">s</span></span></span>';}});},1000);}
        async function refreshData(){const btn=document.getElementById('refreshBtn');btn.disabled=true;btn.textContent='⏳ Refreshing...';try{const r=await fetch('/api/giveaways?refresh=1');const d=await r.json();if(d.status==='success'){btn.textContent='✅ Updated '+d.count;setTimeout(()=>location.reload(),1000);}else{btn.textContent='❌ Error';btn.disabled=false;}}catch(e){btn.textContent='❌ Error';btn.disabled=false;}}
        setInterval(()=>refreshData(),600000);
    </script>
</body>
</html>'''


# Routes
@app.get("/")
async def root(request: Request):
    """Главная страница."""
    try:
        giveaways = await collect_all()
        platforms = list(set(g.platform for g in giveaways))
        template = Template(HTML_TEMPLATE)
        html = template.render(
            giveaways=giveaways,
            platforms=platforms,
            total=len(giveaways),
            total_platforms=len(platforms)
        )
        return HTMLResponse(content=html, headers={"Cache-Control": "no-cache, no-store, must-revalidate"})
    except Exception as e:
        return HTMLResponse(content=f"<h1>Error: {str(e)}</h1>", status_code=500)


@app.get("/api/giveaways")
async def api_giveaways(refresh: int = None, platform: str = None):
    """API для получения раздач."""
    try:
        giveaways = await collect_all()
        if platform:
            giveaways = [g for g in giveaways if platform.lower() in g.platform.lower()]
        return JSONResponse(
            [g.to_dict() for g in giveaways],
            headers={"Cache-Control": "max-age=3600"}
        )
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
