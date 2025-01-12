"""
Мрдуль отвечает за непосредственный парсинг сайта
"""

import json
import logging
import random
import re
import traceback
import httpx 
import asyncio
import aiosqlite

from datetime import datetime
from bs4 import BeautifulSoup
from typing import Any, Optional
from tenacity import retry, stop_after_attempt, wait_fixed
from config import BASE_URL, DB_NAME, REVIEWS_AMOUNT
from cookie import cookie_manager
from user_agents import user_agents
logging.basicConfig(
    level=logging.INFO, 
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", 
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler("main.log", encoding="utf-8")],
)
logger = logging.getLogger(__name__)

class Parser:
    def __init__(self):
        self.proxies_list = self.get_proxies()
        self.cookies = None
        self.base_url = BASE_URL
        self.link_list = []
        self.headers = {"User-Agent": random.choice(user_agents)}

    def get_proxies(self):
        """Получить прокси из текстового файла"""
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

    async def database_init(self):
        """Создание таблиц в БД если их нет"""
        await self.sql(
        """
        CREATE TABLE IF NOT EXISTS exchanges (
        name TEXT PRIMARY KEY,
        link TEXT NOT NULL,
        directions TEXT NOT NULL,
        deposite FLOAT NOT NULL,
        reviews JSON,
        ts DATETIME DEFAULT CURRENT_TIMESTAMP
        );
        """
        )

        await self.sql(
        """
        CREATE TABLE IF NOT EXISTS stores (
        name TEXT PRIMARY KEY,
        link TEXT,
        sales INT,
        deposite FLOAT,
        rating FLOAT,
        rules TEXT,
        vacancy TEXT,
        promotions TEXT,
        products JSON,
        reviews JSON,
        ts DATETIME DEFAULT CURRENT_TIMESTAMP
        );
        """
        )

    
    # @retry(stop=stop_after_attempt(5), wait=wait_fixed(3))
    async def process_request(self, link, session: httpx.AsyncClient) -> httpx.Response:
        """
        Проходит вылезающую капчу при парсинге.
        """
        # чтобы не дудосить сайт
        await asyncio.sleep(random.randint(1,3))
        try:
            r = await session.get(link)
        except ValueError:
            r = await session.get(BASE_URL + link)
        if r.status_code == 301:
            print(r.url, "process_request")
        r.raise_for_status()
        if r.url == f"{self.base_url}/pass":
            await cookie_manager.process_captcha(session, pass_flag=True)
            r = await session.get(link)
        if r.url == f"{self.base_url}/login":
            await cookie_manager.do_auth(session)
            r = await session.get(link)
        return r



    async def parse(self, session: httpx.AsyncClient):
        """Парсинг сайта немного другаю логика без разделения ссылок по прокси, а каждый раз новое"""
        await self.get_links(session)
        tasks = []
        for link in self.link_list:
            tasks.append(self.parse_data(link))
            if len(tasks) == 10:
                await asyncio.gather(*tasks)
                tasks = []
        if len(tasks) != 0:
            await asyncio.gather(*tasks)
            tasks = []        
        logger.info("Парсинг произведён успешно")
 


    async def get_links(self, session: httpx.AsyncClient):
        """
        Получает целевые ссылки, с которым парсим инфу.
        """
        # exchanges
        r = await session.get(f"{BASE_URL}/exchanges", headers=self.headers)
        soup = BeautifulSoup(r.text, 'html.parser')
        table = soup.find("table")
        for row in table.find_all("tr"):
            if row.find("th"):
                continue
            link = row.find('a', class_="link-hover text-sm")['href']
            self.link_list.append(link)
            break

        # stores
        r = await session.get(f"{self.base_url}/stores")
        soup = BeautifulSoup(r.text, "lxml")
        try:
            paginate = int(soup.find("a", class_="page--last").text)
        except:
            paginate = 1
        tasks = []
        for page in range(1, paginate + 1):
            tasks.append(self.process_get_links_stores(page, session))
            if len(tasks) == 10:
                await asyncio.gather(*tasks)
                tasks = []
            break
        if len(tasks) != 0:
            await asyncio.gather(*tasks)
            tasks = []

    async def process_get_links_stores(self, page, session: httpx.AsyncClient):
        link = f"{self.base_url}/stores?page={page}"
        r = await self.process_request(link, session)
        soup = BeautifulSoup(r.text, "lxml")
        cards = soup.find_all("a", class_="group grid gap-3 px-4 py-4 relative")
        for card in cards:
            self.link_list.append(card["href"])


    async def process_comments(self, main_link, page, session: httpx.AsyncClient, exchanges=False):
        """
        Парсинг комментариев.
        """
        review_info_list = []

        if exchanges:
            link = main_link
        else:
            link = main_link + f"/reviews?page={page}"
            
        r = await self.process_request(link, session)
        soup = BeautifulSoup(r.text, "lxml")
        reviews_div = soup.find_all("div", class_="comment-wrapper")
        if not reviews_div:
            logger.info(f"Нет отзывов - {link}")
            return
        for review_div in reviews_div:
            nickname = review_div.find("h3", class_="text-[14px] font-semibold text-truncate").text.strip()
            comment_text = review_div.find("div", class_="comment__text ws-pl").text.strip()
            rating = review_div.find("svg", style=True)["style"].split(":")[1].strip()
            try:
                purchases = review_div.find("svg", class_="sm:hidden align-bottom mr-0.5").next_sibling.strip()
                purchases = int(purchases.strip())
            except Exception as ex:
                # logger.error(f"Нет purchases на ссылке {link}. Ошибка: {ex}")
                purchases = None
            date_string = review_div.find("span", class_='text-default-150').text.replace("в", " ").strip()
            date = datetime.strptime(date_string, "%d/%m/%y %H:%M")
            date = date.strftime("%d/%m/%y %H:%M")
            img_link = review_div.find("img", class_='rounded-full w-12 mr-4')["src"]
            if "no-img.png" in img_link:
                img = None
            else:
                img = BASE_URL + img_link
                # r = await session.get(BASE_URL + img_link)
                # random_string = ''.join(random.choices(string.ascii_letters + string.digits, k=10))
                # # Проверяем, существует ли директория, и если нет, создаем ее
                # if not os.path.exists('media'):
                #     os.makedirs('media')
                # path = f'./media/{random_string}.jpg'
                # async with aiofiles.open(path, 'wb') as f:
                #     # Записываем содержимое ответа в файл
                #     await f.write(r.content)
                #     img = path
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
                'rating': float(rating.strip())
            }
            review_info_list.append(review_info)
        return review_info_list

             
    # @retry(stop=stop_after_attempt(5), wait=wait_fixed(3))
    async def parse_data(self, link):
        """
        Парсинг всей интерисующей нас информации
        """
        proxy = random.choice(self.proxies_list)

        async with httpx.AsyncClient(proxy=proxy, cookies=self.cookies, timeout=120, follow_redirects=True, headers=self.headers) as session:
            try:
                r = await self.process_request(link, session)
                soup = BeautifulSoup(r.text, "lxml")
                if "exchanges" in link:
                    name = soup.find("h1", class_="m-0 text-2xl lg:text-3xl").text.strip()
                    directions = soup.find("select", {"id": "method"}).text
                    directions = directions.replace("\n", "").strip()
                    directions = re.sub(r"\s{2,}", " ", directions)
                    deposite_div = soup.find("div", "mt-5 bg-default-50 rounded-xl py-3 px-5 my-6 inline-flex<")
                    deposite = deposite_div.find('b', class_='font-semibold').text.strip()
                    exchanges_data = {
                        "name": name,
                        "link": BASE_URL + link,
                        "directions": directions,
                        "deposite": float(deposite.replace("₿","").strip()),
                        }
                    
                    exchanges_reviews = await self.process_comments(link, 1, session, exchanges=True)
                    exchanges_data["reviews"] = exchanges_reviews
                    

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
                    (exchanges_data["name"], exchanges_data["link"], exchanges_data["directions"], exchanges_data["deposite"], json.dumps(exchanges_data["reviews"], ensure_ascii=False))
                )
                    logger.info(f"Данные успешно записаны в БД (exchanges) - {link}")

                elif "stores" in link:
                    link = BASE_URL + link
                    # Витрина
                    r = await session.get(link)
                    products_data = []
                    soup = BeautifulSoup(r.text, "lxml")
                    header = soup.find("header", class_="flex flex-wrap items-center text-default-50/m gap-4 justify-between lg:px-4")
                    name = header.find("h1", class_="text-default-50 text-3xl").text.strip()
                    spans = header.find_all('span')
                    rating = soup.find('span', {'class': 'flex items-center gap-1 mr-auto lg:mr-0'}).text.strip()
                    sales = int(spans[1].get_text().split(":")[1].strip())
                    deposite = spans[2].get_text(strip=True).split(":")[1].strip()
                    try:
                        paginate = int(soup.find("a", class_="page--last").text)
                    except:
                        paginate = 1
                    for page in range(1, paginate + 1):
                        showcase_link = link + f"?page={page}#main"
                        r = await self.process_request(showcase_link, session)
                        soup = BeautifulSoup(r.text, "lxml")

                        products = soup.find_all("a", class_="group grid gap-2 px-4 py-4 rounded-2xl border focus:ring-1 hover:ring-1")
                        for product in products:
                            product_name = product.find("div", class_="uppercase text-center text-default-150 text-[10px] text-truncate").text.strip()
                            product_link = product["href"].strip()
                            description = soup.find('h3', class_='text-center leading-tight text-default-200 text-[14px] group-focus:text-blue-150 group-hover:text-blue-150 transition-colors text-truncate').text.strip()
                            price_div = product.find("div", class_="flex flex-col text-center text-xs")
                            price_weight = price_div.find("span", class_="text-default-200").text.strip()
                            price = price_weight.split("/")[0].strip()
                            price_btc = soup.find('div', class_='flex flex-col text-center text-xs').text.strip().split("\n")[-1].strip()
                            unit = price_weight.split("/")[1].strip()
                            img_link = product.find("img", class_="rounded-3xl justify-self-center product-image")["src"].strip()
                            product_data = {
                                "name": product_name,
                                "link": product_link,
                                "description": description,
                                "price": int(price.replace("₽", "").strip()),
                                "price_btc": float(price_btc.replace("₿", "").replace("~", "").strip()),
                                "unit ": unit,
                                "img_link": img_link
                                }
                            products_data.append(product_data)

                    # Правила
                    r = await session.get(link + f"/rules")
                    soup = BeautifulSoup(r.text, "lxml")
                    rules = soup.find("div", class_="ws-pl").text.strip()

                    # Вакансии
                    r = await session.get(link + f"/vacancy")
                    soup = BeautifulSoup(r.text, "lxml")
                    vacancy = soup.find("div", class_="ws-pl").text.strip()

                    # Акции
                    r = await session.get(link + f"/promotions")
                    soup = BeautifulSoup(r.text, "lxml")
                    promotions = soup.find("div", class_="ws-pl").text.strip()

                    store_data = {
                        "name": name,
                        "link": link,
                        "sales": sales,
                        "deposite": float(deposite.replace("₿","").strip()),
                        "rating": float(rating.strip()),
                        "rules": rules,
                        "vacancy": vacancy,
                        "promotions": promotions,
                        "products": products_data,
                    }

                    # Отзывы
                    stores_reviews = await self.gather_reviews(link, session)
                    store_data["reviews"] = stores_reviews
                    
                    await self.sql(
                    """
                    INSERT INTO stores
                    (name, link, sales, deposite, rating, rules, vacancy, promotions, products, reviews) 
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?) ON CONFLICT (name) 
                    DO UPDATE SET
                        name = EXCLUDED.name,
                        link = EXCLUDED.link,
                        sales = EXCLUDED.sales,
                        deposite = EXCLUDED.deposite,
                        rating = EXCLUDED.rating,
                        rules = EXCLUDED.rules,
                        vacancy = EXCLUDED.vacancy,
                        promotions = EXCLUDED.promotions,
                        products = EXCLUDED.products,
                        reviews = EXCLUDED.reviews;
                    """,
                    (
                    store_data["name"], store_data["link"], store_data["sales"], store_data["deposite"], 
                    store_data["rating"], store_data["rules"], store_data["vacancy"], 
                    store_data["promotions"], json.dumps(store_data["products"], ensure_ascii=False), 
                    json.dumps(store_data["reviews"], ensure_ascii=False)
                    )
                )   
                    logger.info(f"Данные успешно записаны в БД (stores) - {link}")
                else:
                    logger.info(f"Недопустимая ссылка - {link}")
            except Exception as ex:
                logger.error(f"Произошла ошибка при парсинге {link}. Ошибка: {ex}. Детали ошибки: {traceback.format_exc()}")

        

    async def gather_reviews(self, link, session):
        """Костыль для сохранения отзывов. Возможно он тут уже и не нужен, но как говориться работает - не трогай"""
        stores_reviews = []
        r = await session.get(link + "/reviews")
        soup = BeautifulSoup(r.text, "lxml")

        try:
            paginate = int(soup.find("a", class_="page--last").text.strip())
        except:
            paginate = 1
        paginate = min(paginate, REVIEWS_AMOUNT)

        tasks = []
        for page in range(1, paginate + 1):
            tasks.append(self.process_comments(link, page, session))
            if len(tasks) == 5:
                results = await asyncio.gather(*tasks)
                for result in results:
                    if isinstance(result, Exception):
                        tb = ''.join(traceback.format_tb(result.__traceback__))
                        err = f'{result.__class__.__name__}: {str(result)}\n{tb}'
                        logging.error(err)
                    else:
                        stores_reviews.extend(result)
                tasks = []
        
        if tasks:
            results = await asyncio.gather(*tasks)
            for result in results:
                if isinstance(result, Exception):
                    tb = ''.join(traceback.format_tb(result.__traceback__))
                    err = f'{result.__class__.__name__}: {str(result)}\n{tb}'
                    logging.error(err)
                else:
                    stores_reviews.extend(result)
        
        return stores_reviews

    async def sql(self, query: str, params: Optional[tuple] = None) -> list[dict[str, Any]]:
        """
        Асинхронная функция для выполнения SQL-запросов в SQLite.
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
                
    async def main(self):
        """Главная точка входа парсинга."""
        await self.database_init()
        proxy = random.choice(self.proxies_list)
        self.cookies = await cookie_manager.get_cookies()
        async with httpx.AsyncClient(cookies=self.cookies, proxy=proxy, headers=self.headers, timeout=120, follow_redirects=True) as session:
            await self.parse(session)

x = Parser()
asyncio.run(x.main())


