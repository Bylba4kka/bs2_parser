from collections import defaultdict
import json
import logging
import os
import random
import re
import string
import httpx 
import asyncio
import aiofiles
import aiosqlite

from datetime import datetime
from bs4 import BeautifulSoup
from typing import Any, Optional
from config import BASE_URL, DB_NAME
from cookie import cookie_manager

logging.basicConfig(
    level=logging.INFO, 
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", 
    handlers=[logging.StreamHandler()],
)
logger = logging.getLogger(__name__)

class Parser:
    def __init__(self):
        self.proxies_list = self.get_proxies()
        self.cookies = None
        self.base_url = BASE_URL
        self.headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:130.0) Gecko/20100101 Firefox/130.0",
        }

    def get_proxies(self):
        proxies = []
        with open("proxies.txt", 'r') as file:
            for line in file:
                parts = line.strip().split(':')
                host = parts[0]
                port = parts[1]
                user = parts[2]
                password = parts[3]
                proxy = f"http://{user}:{password}@{host}:{port}"
                proxies.append(proxy)
        return proxies


    async def distribute_links_among_proxies(self, session: httpx.AsyncClient):
        result = defaultdict(list)
        self.links = await self.get_links(session)
        for i, link in enumerate(self.links):
            proxy = self.proxies_list[i % len(self.proxies_list)]
            result[proxy].append(link)
        return result
        
    async def parse(self):
        tasks = []
        for proxy, links in self.links_with_proxy.items():
            print(f"Proxy: {proxy}, Links: {links}")
            tasks.append(self.parse_data(proxy, links))
            print(f"{len(tasks)=}")
            if len(tasks) == 10:
                await asyncio.gather(*tasks)
                tasks = []
        if len(tasks) != 0:
            await asyncio.gather(*tasks)
            tasks = []

    # async def parse(self, session: httpx.AsyncClient):
    #     for link in self.links:
    #         await asyncio.sleep(3)
    #         await self.parse_data(link, session)

    async def get_links(self, session: httpx.AsyncClient):
        link_list = []
        r = await session.get(f"{BASE_URL}/exchanges", headers=self.headers)
        soup = BeautifulSoup(r.text, 'html.parser')
        table = soup.find("table")
        for row in table.find_all("tr"):
            if row.find("th"):
                continue
            link = row.find('a', class_="link-hover text-sm")['href']
            link_list.append(link)
        return link_list


    async def parse_data(self, proxy, links):
        reviews_list = []
        async with httpx.AsyncClient(proxy=proxy, cookies=self.cookies, timeout=60, follow_redirects=True, headers=self.headers) as session:
            for link in links:
                r = await session.get(link)
                r.raise_for_status()
                if r.url == f"{self.base_url}/pass":
                    await cookie_manager.process_captcha(session, pass_flag=True)
                    r = await session.get(link)
                print(f"{r.status_code=}")
                soup = BeautifulSoup(r.text, "lxml")
                name = soup.find("h1", class_="m-0 text-2xl lg:text-3xl").text.strip()
                print(f"{name=}")
                directions = soup.find("select", {"id": "method"}).text
                directions = directions.replace("\n", "").strip()
                directions = re.sub(r"\s{2,}", " ", directions)
                print(directions)
                deposite_div = soup.find("div", "mt-5 bg-default-50 rounded-xl py-3 px-5 my-6 inline-flex<")
                deposite = deposite_div.find('b', class_='font-semibold').text.strip()
                reviews_div = soup.find_all("div", class_="comment-wrapper")
                data = {
                    "name": name,
                    "link": link,
                    "directions": directions,
                    "deposite": deposite,
                    }
                if not reviews_div:
                    logger.info("no reviews")
                    return
                for review_div in reviews_div:
                    nickname = review_div.find("h3", class_="text-[14px] font-semibold text-truncate").text.strip()
                    comment_text = review_div.find("div", class_="comment__text ws-pl").text.strip()
                    rating = review_div.find("svg", style=True)["style"].split(":")[1].strip()
                    purchases = review_div.find("svg", class_="sm:hidden align-bottom mr-0.5").next_sibling.strip()
                    date_string = review_div.find("span", class_='text-default-150').text.replace("в", " ").strip()
                    date = datetime.strptime(date_string, "%d/%m/%y %H:%M")
                    date = date.strftime("%d/%m/%y %H:%M")
                    img_link = review_div.find("img", class_='rounded-full w-12 mr-4')["src"]
                    if "no-img.png" in img_link:
                        img = None
                    else:
                        r = await session.get(BASE_URL + img_link)
                        random_string = ''.join(random.choices(string.ascii_letters + string.digits, k=10))
                        # Проверяем, существует ли директория, и если нет, создаем ее
                        if not os.path.exists('media'):
                            os.makedirs('media')
                        path = f'./media/{random_string}.jpg'
                        async with aiofiles.open(path, 'wb') as f:
                            # Записываем содержимое ответа в файл
                            await f.write(r.content)
                            img = path
                    try:
                        admin = review_div.find_element("div", class_='comment__text ws-pl content').text.strip()
                    except:
                        admin = None

                    review_info = {
                        'nickname': nickname,
                        'comment_text': comment_text,
                        'purchases': purchases,
                        'datе': date,
                        'img': img,
                        'admin': admin,
                        'rating': rating
                    }
                    reviews_list.append(review_info)
                data["reviews"] = reviews_list

                await self.sql(
                    """
                    INSERT INTO exchanges
                    (name, link, directions, deposite, reviews) 
                    VALUES (?, ?, ?, ?, ?) ON CONFLICT (name) 
                    DO UPDATE SET
                        link = EXCLUDED.link,
                        directions = EXCLUDED.directions,
                        deposite = EXCLUDED.deposite,
                        reviews = EXCLUDED.reviews;
                    """,
                    (data["name"], data["link"], data["directions"], data["deposite"], json.dumps(data["reviews"], ensure_ascii=False))
                )
                logger.info("Данные успешно записаны в БД")

    async def main(self):
        proxy = random.choice(self.proxies_list)
        self.cookies = await cookie_manager.get_cookies()
        async with httpx.AsyncClient(cookies=self.cookies, proxy=proxy, headers=self.headers, timeout=60, follow_redirects=True) as session:
            self.links_with_proxy = await self.distribute_links_among_proxies(session)
        await self.parse()


    async def sql(self, query: str, params: Optional[tuple] = None) -> list[dict[str, Any]]:
        """
        Асинхронная функция для выполнения SQL-запросов в SQLite.
        
        :param query: SQL-запрос.
        :param params: Параметры для SQL-запроса (по умолчанию None).
        """
        database = DB_NAME + ".sqlite3"
        params = params or ()
        async with aiosqlite.connect(database) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(query, params) as cursor:
                if query.strip().lower().startswith("select"):
                    result = await cursor.fetchall()
                    return [dict(row) for row in result]
                else:
                    await db.commit()  # Для запросов INSERT, UPDATE, DELETE
                    return None

x = Parser()



print(asyncio.run(x.main()))

# asyncio.run(x.sql(
# """
# CREATE TABLE IF NOT EXISTS exchanges (
# name TEXT PRIMARY KEY,
# link TEXT NOT NULL,
# directions TEXT NOT NULL,
# deposite TEXT NOT NULL,
# reviews JSON,
# ts DATETIME DEFAULT CURRENT_TIMESTAMP
# );
# """
# ))

