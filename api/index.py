
"""Vercel Serverless Function - Giveaway Tracker API."""

import asyncio
import json
import os
from datetime import datetime, timedelta
from http.server import BaseHTTPRequestHandler
from urllib.parse import quote, urlencode, urlparse

import aiohttp


class Giveaway:
    """Модель бесплатной игры или раздачи."""

    def __init__(
        self,
        platform,
        title,
        price,
        url,
        end_date=None,
        image=None,
        desc=None,
        is_permanent=False,
    ):
        self.platform = platform
        self.title = title
        self.original_price = price
        self.discount_price = "Free"
        self.url = url
        self.end_date = end_date
        self.image_url = image
        self.description = desc
        self.is_permanent = is_permanent

        if end_date:
            self.time_components = self._get_time()
            self.is_expired = self._is_expired()
        else:
            self.time_components = {
                "days": 0,
                "hours": 0,
                "minutes": 0,
                "seconds": 0,
                "expired": False,
            }
            self.is_expired = False

    def _parse_end_date(self):
        """Преобразует дату окончания в datetime."""
        if not self.end_date:
            return None

        value = self.end_date.strip()

        if value.endswith("Z"):
            value = value[:-1] + "+00:00"

        return datetime.fromisoformat(value)

    def _get_time(self):
        try:
            end = self._parse_end_date()

            if end is None:
                return {
                    "days": 0,
                    "hours": 0,
                    "minutes": 0,
                    "seconds": 0,
                    "expired": False,
                }

            now = (
                datetime.now(end.tzinfo)
                if end.tzinfo
                else datetime.now()
            )

            seconds = max(0, int((end - now).total_seconds()))

            return {
                "days": seconds // 86400,
                "hours": (seconds % 86400) // 3600,
                "minutes": (seconds % 3600) // 60,
                "seconds": seconds % 60,
                "expired": seconds <= 0,
            }

        except (ValueError, TypeError, OverflowError):
            return {
                "days": 0,
                "hours": 0,
                "minutes": 0,
                "seconds": 0,
                "expired": True,
            }

    def _is_expired(self):
        try:
            end = self._parse_end_date()

            if end is None:
                return False

            now = (
                datetime.now(end.tzinfo)
                if end.tzinfo
                else datetime.now()
            )

            return end <= now

        except (ValueError, TypeError, OverflowError):
            return True

    def to_dict(self):
        return {
            "platform": self.platform,
            "title": self.title,
            "original_price": self.original_price,
            "discount_price": self.discount_price,
            "url": self.url,
            "end_date": self.end_date,
            "description": self.description,
            "image_url": self.image_url,
            "is_expired": self.is_expired,
            "time_components": self.time_components,
            "is_permanent": self.is_permanent,
        }


def get_epic_game_url(game):
    """
    Возвращает прямую ссылку на игру в Epic Games Store.

    Пример:
    https://store.epicgames.com/p/sker-ritual-aac702

    Не использует устаревшую страницу поиска.
    """

    page_slug = None

    # 1. Основной источник: catalogNs.mappings
    catalog_ns = game.get("catalogNs") or {}
    mappings = catalog_ns.get("mappings") or []

    if isinstance(mappings, list):
        for mapping in mappings:
            if isinstance(mapping, dict):
                candidate = mapping.get("pageSlug")
                if candidate:
                    page_slug = candidate
                    break

    # 2. Дополнительный источник: offerMappings
    if not page_slug:
        offer_mappings = game.get("offerMappings") or []

        if isinstance(offer_mappings, list):
            for mapping in offer_mappings:
                if isinstance(mapping, dict):
                    candidate = mapping.get("pageSlug")
                    if candidate:
                        page_slug = candidate
                        break

    # 3. Резервные поля Epic API
    if not page_slug:
        for key in ("productSlug", "urlSlug", "slug"):
            candidate = game.get(key)

            if isinstance(candidate, str) and candidate.strip():
                page_slug = candidate.strip()
                break

    if page_slug:
        page_slug = str(page_slug).strip()

        # Если API вернул URL целиком, извлекаем путь.
        if page_slug.startswith(("https://", "http://")):
            parsed = urlparse(page_slug)
            page_slug = parsed.path.strip("/").split("/")[-1]

        # Убираем возможный префикс /p/ и другие части пути.
        page_slug = page_slug.strip("/").split("/")[-1]

        if page_slug and page_slug.lower() not in {
            "p",
            "search",
            "free-games",
        }:
            clean_slug = quote(page_slug, safe="-._~")

            # Именно такой формат нужен для прямой ссылки на игру.
            return f"https://store.epicgames.com/p/{clean_slug}"

    # Если slug отсутствует, не создаём ложную ссылку на конкретную игру.
    return "https://store.epicgames.com/free-games"


async def get_epic(session):
    """Epic Games Store — временные бесплатные игры."""

    result = []

    api_url = (
        "https://store-site-backend-static.ak.epicgames.com/"
        "freeGamesPromotions"
    )

    params = {
        "locale": "ru-RU",
        "country": "RU",
        "allowCountries": "RU",
    }

    try:
        async with session.get(
            api_url,
            params=params,
            timeout=aiohttp.ClientTimeout(total=15),
        ) as response:

            if response.status != 200:
                print(f"Epic API status: {response.status}")
                return result

            data = await response.json(content_type=None)

        games = (
            data.get("data", {})
            .get("Catalog", {})
            .get("searchStore", {})
            .get("elements", [])
        )

        for game in games:
            try:
                promotions = game.get("promotions")

                if not promotions:
                    continue

                promotional_groups = (
                    promotions.get("promotionalOffers") or []
                )

                game_added = False

                for group in promotional_groups:
                    offers = group.get("promotionalOffers") or []

                    for offer in offers:
                        discount_setting = (
                            offer.get("discountSetting") or {}
                        )

                        discount = discount_setting.get(
                            "discountPercentage", 100
                        )

                        # Только игры с действующей скидкой 100%.
                        if discount != 0:
                            continue

                        title = game.get("title", "Unknown")

                        end_date = offer.get("endDate") or None

                        original_price = discount_setting.get(
                            "originalPrice"
                        )

                        # В некоторых ответах цена находится
                        # в другом объекте.
                        if original_price is None:
                            price_info = (
                                game.get("price", {})
                                .get("totalPrice", {})
                            )
                            original_price = price_info.get(
                                "originalPrice"
                            )

                        if isinstance(original_price, (int, float)):
                            price = f"${original_price / 100:.2f}"
                        else:
                            price = "N/A"

                        images = game.get("keyImages") or []

                        image = next(
                            (
                                item.get("url")
                                for image_type in (
                                    "OfferImageWide",
                                    "DieselStoreFrontWide",
                                    "Thumbnail",
                                )
                                for item in images
                                if item.get("type") == image_type
                                and item.get("url")
                            ),
                            None,
                        )

                        # Исправленная генерация прямой ссылки.
                        url = get_epic_game_url(game)

                        description = (
                            game.get("description") or ""
                        )[:300]

                        result.append(
                            Giveaway(
                                platform="Epic Games",
                                title=title,
                                price=price,
                                url=url,
                                end_date=end_date,
                                image=image,
                                desc=description,
                                is_permanent=False,
                            )
                        )

                        game_added = True
                        break

                    if game_added:
                        break

            except Exception as error:
                print(
                    f"Epic game parse error "
                    f"({game.get('title', 'Unknown')}): {error}"
                )

    except Exception as error:
        print(f"Epic error: {error}")

    return result


async def get_steam(session):
    """Steam — бесплатные игры и игры с временной скидкой 100%."""

    result = []

    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/131.0.0.0 Safari/537.36"
        ),
        "Accept": (
            "text/html,application/xhtml+xml,"
            "application/xml;q=0.9,*/*;q=0.8"
        ),
    }

    search_url = "https://store.steampowered.com/search/"

    params = {
        "maxprice": "free",
        "specials": "1",
        "l": "english",
    }

    try:
        async with session.get(
            search_url,
            params=params,
            headers=headers,
            timeout=aiohttp.ClientTimeout(total=15),
            allow_redirects=True,
        ) as response:

            if response.status != 200:
                print(f"Steam status: {response.status}")
                return result

            html = await response.text()

        from bs4 import BeautifulSoup

        soup = BeautifulSoup(html, "html.parser")

        game_rows = soup.select(
            "#search_resultsRows .search_result_row"
        )

        for game in game_rows[:30]:
            try:
                title_element = game.select_one(".title")

                if not title_element:
                    continue

                title = title_element.get_text(strip=True)

                link = game.get("href", "").strip()

                if not link:
                    continue

                # Убираем параметры отслеживания из ссылки.
                parsed_link = urlparse(link)

                if parsed_link.scheme not in ("http", "https"):
                    continue

                image_element = game.select_one("img")

                image_url = None

                if image_element:
                    image_url = (
                        image_element.get("src")
                        or image_element.get("data-src")
                    )

                discount_element = game.select_one(
                    ".discount_pct"
                )

                if (
                    discount_element
                    and discount_element.get_text(strip=True) == "-100%"
                ):
                    original_element = game.select_one(
                        ".discount_original_price"
                    )

                    original_price = (
                        original_element.get_text(strip=True)
                        if original_element
                        else "N/A"
                    )

                    # В исходном HTML нет надёжной даты окончания.
                    # Сохраняем прежнюю логику на 7 дней.
                    end_date = (
                        datetime.now() + timedelta(days=7)
                    ).isoformat(timespec="seconds")

                    is_permanent = False
                    description = "100% Off - Limited Time!"

                else:
                    original_price = "N/A"
                    end_date = None
                    is_permanent = True
                    description = "Free to Play"

                result.append(
                    Giveaway(
                        platform="Steam",
                        title=title,
                        price=original_price,
                        url=link,
                        image=image_url,
                        desc=description,
                        end_date=end_date,
                        is_permanent=is_permanent,
                    )
                )

            except Exception as error:
                print(f"Steam parse error: {error}")
                continue

    except Exception as error:
        print(f"Steam error: {error}")

    return result


# HTML template
HTML_TEMPLATE = None


def get_template():
    """Загружает HTML-шаблон сайта."""

    global HTML_TEMPLATE

    if HTML_TEMPLATE is None:
        template_path = os.path.join(
            os.path.dirname(__file__),
            "..",
            "templates",
            "index.html",
        )

        try:
            with open(
                template_path,
                "r",
                encoding="utf-8",
            ) as file:
                HTML_TEMPLATE = file.read()

        except OSError as error:
            print(f"Template error: {error}")

            HTML_TEMPLATE = (
                "<!DOCTYPE html>"
                "<html><head><meta charset='utf-8'>"
                "<title>Giveaway Tracker</title></head>"
                "<body><h1>Template not found</h1></body></html>"
            )

    return HTML_TEMPLATE


class handler(BaseHTTPRequestHandler):
    """HTTP Request Handler for Vercel."""

    def do_GET(self):
        parsed = urlparse(self.path)
        path = parsed.path

        if path == "/api/giveaways":
            self._send_json(self._run_collection())

        elif path == "/api/stats":
            giveaways = self._run_collection()

            stats = {
                "total": len(giveaways),
                "by_platform": {},
                "permanent": 0,
                "limited": 0,
                "expired": 0,
            }

            for game in giveaways:
                platform = game["platform"]

                stats["by_platform"][platform] = (
                    stats["by_platform"].get(platform, 0) + 1
                )

                if game["is_permanent"]:
                    stats["permanent"] += 1
                elif game["is_expired"]:
                    stats["expired"] += 1
                else:
                    stats["limited"] += 1

            self._send_json(stats)

        else:
            template = get_template()

            self.send_response(200)
            self.send_header(
                "Content-Type",
                "text/html; charset=utf-8",
            )
            self.send_header("Cache-Control", "no-cache")
            self.end_headers()
            self.wfile.write(template.encode("utf-8"))

    def _send_json(self, data):
        """Отправляет JSON-ответ."""

        payload = json.dumps(
            data,
            ensure_ascii=False,
        ).encode("utf-8")

        self.send_response(200)
        self.send_header(
            "Content-Type",
            "application/json; charset=utf-8",
        )
        self.send_header(
            "Cache-Control",
            "public, max-age=60, s-maxage=300",
        )
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def _run_collection(self):
        """Запускает асинхронный сбор данных."""

        try:
            return asyncio.run(self._collect_giveaways())

        except Exception as error:
            print(f"Collection error: {error}")
            return []

    async def _collect_giveaways(self):
        """Собирает раздачи с поддерживаемых платформ."""

        timeout = aiohttp.ClientTimeout(total=20)

        async with aiohttp.ClientSession(
            timeout=timeout
        ) as session:

            results = await asyncio.gather(
                get_epic(session),
                get_steam(session),
                return_exceptions=True,
            )

        all_games = []

        for result in results:
            if isinstance(result, list):
                all_games.extend(result)
            elif isinstance(result, Exception):
                print(f"Source error: {result}")

        # Удаляем дубликаты по URL.
        seen = set()
        unique_games = []

        for game in all_games:
            if game.url not in seen:
                seen.add(game.url)
                unique_games.append(game)

        return [
            game.to_dict()
            for game in unique_games
        ]

    def log_message(self, format, *args):
        print(
            f"{self.address_string()} - "
            f"{format % args}"
        )
