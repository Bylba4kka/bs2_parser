"""
Модуль отвечает за авторизацию на сайте
"""

import base64
import json
import logging
import os
import random
import string
import httpx
from bs4 import BeautifulSoup
from twocaptcha import TwoCaptcha
import aiofiles
import asyncio
from functools import partial

from tenacity import retry, stop_after_attempt, wait_fixed
from config import BASE_URL, LOGIN, PASSWORD, RUCAPTCHA_API_KEY, MANUAL
from user_agents import user_agents

logging.basicConfig(
    level=logging.INFO, 
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", 
    handlers=[logging.StreamHandler()],
)
logger = logging.getLogger(__name__)



class CookieManager:
    """Точка входа для получения cookie файлов"""
    def __init__(self):
        self.proxies_list = self.get_proxies()
        self.base_url = BASE_URL
        self.login = LOGIN
        self.password = PASSWORD
        self.cookie_file = "cookies.json"
        self.rucaptcha_api_key = RUCAPTCHA_API_KEY
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


    def random_string(self, length):
        """Рандомное название"""
        letters = string.ascii_lowercase
        return ''.join(random.choice(letters) for i in range(length))


    async def save_captcha_image(self, captcha):
        """Сохранять изображение капчи (для откладки)"""
        if not os.path.exists("images"):
            os.makedirs("images")
        # filename = self.random_string(3)
        filename = "captcha.jpg"
        async with aiofiles.open(filename, "wb") as file:
            await file.write(captcha)
        logger.info(f"Капча успешно сохранена под названием: {filename}")


    async def save_cookies(self, cookies_list):
        """Сохранение куки файлов"""
        async with aiofiles.open(self.cookie_file, "w") as file:
            json_data = json.dumps(cookies_list, ensure_ascii=False, indent=4)
            await file.write(json_data)
        logger.info("Cookies-файлы успешно сохранены")


    async def load_cookies(self):
        """Подгрузка ранее загруженых куки"""
        async with aiofiles.open(self.cookie_file, "r") as file:
            cookies_list = await file.read()

        cookies = httpx.Cookies()
        for cookie in json.loads(cookies_list):
            cookies.set(
                cookie['name'],
                cookie['value'],
                domain=cookie['domain'],
                path=cookie['path'],
            )
        return cookies
    

    async def validate_cookies(self, session: httpx.AsyncClient):
        """Действительны ли куки"""
        r = await session.get(f"{self.base_url}/stores", headers=self.headers)
        if r.status_code == 401:
            return False
        if r.status_code == 200:
            if r.url == f"{self.base_url}/login":
                return False
            if r.url == f"{self.base_url}/stores":
                return True
        return False


    async def get_captcha_image(self, html, session: httpx.AsyncClient):
        """Получить изображение капчи и секретный токен"""
        soup = BeautifulSoup(html, "html.parser")
        captcha_url = BASE_URL + soup.find("img", id="captcha-img")["src"]
        captcha_token = soup.find("input",{'type': 'hidden', 'name': '_token'})["value"]
        r = await session.get(captcha_url, headers=self.headers)
        r.raise_for_status()
        captcha_image = r.read()
        if MANUAL:
            await self.save_captcha_image(r.content)
        captcha_base64 = base64.b64encode(captcha_image).decode('utf-8')
        return captcha_base64, captcha_token


    def captcha_solver(self, captcha_base64):
        """Решение капчи"""
        if MANUAL:
            captcha_solution = input("Введите решение капчи:")
            return captcha_solution
        logger.info("Обращение к RUCatcha")
        solver = TwoCaptcha(self.rucaptcha_api_key)
        result = solver.normal(captcha_base64)
        captcha_solution = result.get("code")
        return captcha_solution


    async def process_captcha(self, session: httpx.AsyncClient, pass_flag=False, login_flag=False):
        """Обработка выплывающей капчи"""
        if login_flag:
            url = f"{self.base_url}/login"
        else:
            url = f"{self.base_url}/"
        for i in range(1, 100):
            if i == 6:
                logger.info("Не удалось пройти капчу")
                return False
            r = await session.get(url=url, headers=self.headers)
            r.raise_for_status()
            html = r.text
            soup = BeautifulSoup(html, "html.parser")
            captcha_base64, captcha_token = await self.get_captcha_image(html, session)
            loop = asyncio.get_event_loop()
            solver_with_args = partial(self.captcha_solver, captcha_base64)
            captcha_solution = await loop.run_in_executor(None, solver_with_args)
            logger.info(f"Решение капчи - {captcha_solution}")
            # <input class="hidden" name="En&amp;Sq%c" value="$8ci%VWsla"></form>
            if pass_flag:
                secret_key =  soup.find("input", {'class': 'hidden'})["name"].strip() 
                secret_value = soup.find("input", {'class': 'hidden'})["value"].strip() 
                data = {"_token": captcha_token, "captcha": captcha_solution, secret_key: secret_value}
            else:
                {"_token": captcha_token, "captcha": captcha_solution}
            
            if pass_flag:
                url_condition = self.base_url + "/login/"
                r = await session.post(
                        url=f"{self.base_url}/pass",
                        headers=self.headers | {"Accept": "application/json, text/plain, */*", "Referer": "https://m.bs2site.at/pass"},
                        data=data
                        )
            if login_flag:
                url_condition = self.base_url + "/"
                r = await session.post(
                    f"{self.base_url}/login", 
                    headers=self.headers | {"Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8", "Referer": "https://m.bs2site.at/login"}, 
                    data={"_token": captcha_token, "login": self.login, "password": self.password, "captcha":str(captcha_solution), "v1":"1"}
                    )
            print(f"{r.url=}")
            if not r.url == url_condition:
                with open("error.html", "w", encoding="utf-8") as f:
                    f.write(r.text)
                logger.info(f"Неверная капча, попытка {i}/100")
                await asyncio.sleep(1)
                continue
            else:
                logger.info("Капча пройдена")
                return True


    # @retry(stop=stop_after_attempt(5), wait=wait_fixed(1))
    async def do_auth(self, session: httpx.AsyncClient):
        """Главная логика авторизации на сайте"""
        session.cookies.clear()
        await self.process_captcha(session, pass_flag=True)
        await self.process_captcha(session, login_flag=True)     
        cookies = session.cookies.jar
        cookies_list = [
            {
                'name': cookie.name,
                'value': cookie.value,
                'domain': cookie.domain,
                'path': cookie.path,
                **(
                    {'expires': cookie.expires}
                    if cookie.expires is not None
                    else {}
                ),
            }
            for cookie in cookies
        ]
        await self.save_cookies(cookies_list)

        cookies = httpx.Cookies()
        for cookie in cookies_list:
            cookies.set(
                cookie['name'],
                cookie['value'],
                domain=cookie['domain'],
                path=cookie['path'],
            )
        return cookies


    async def get_cookies(self):
        """Точка входа для получения куки"""
        proxy = random.choice(self.proxies_list)
        async with httpx.AsyncClient(proxy=proxy, headers=self.headers, timeout=60, follow_redirects=True) as session:
            return await self.do_auth(session)
            cookies = await self.load_cookies()
            self.proxies_list = self.get_proxies()
            valid = await self.validate_cookies(session)
            if valid:
                return cookies
            else:
                return await self.do_auth(session)
            
    # async def __call__(self):
    #     return await self.get_cookies()
            

cookie_manager = CookieManager()