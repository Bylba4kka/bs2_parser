"""
Тут из базы данных отсылаем на эндпоинт данные. Пока только обменники. 
Нужно сделать эндпоинт для магазина (как и с обменникам Один на коменты, другой на данные ну или как будет удобнее).
А лучше вообще на стороне Джанго подтягивать данные из бд, но тут игрвет следующая проблема)
Тут структура одна, там другая, так как разные разработчики были)))))
"""

import hashlib
import json
import logging
import time
import aiofiles
import httpx
import asyncio
import aiosqlite

log_path = "main.log"
logging.basicConfig(
    level=logging.INFO, 
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", 
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler(log_path, encoding="utf-8")],
)

logging.getLogger('httpx').setLevel(logging.INFO)
logging.getLogger('httpcore').setLevel(logging.INFO)
from config import DB_NAME, HOST


async def generate_hash(name, title, text):
    combined_string = f"{name}:{title}:{text}"
    hash_object = hashlib.sha256(combined_string.encode('utf-8'))
    return hash_object.hexdigest()


async def sql(query: str, params):
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
                

async def send_data():
    async with httpx.AsyncClient(timeout=60, verify=False) as client:
        rows = await sql(
            """
            SELECT name, reviews FROM stores WHERE sent = False LIMIT 1
            """,
            ()
            )
        try:
            async with aiofiles.open("reviews.json", "r") as f:
                reviews_send = json.loads(await f.read())
        except json.decoder.JSONDecodeError:
            reviews_send = []
        success = True
        for r in rows:
            reviews = json.loads(r["reviews"])
            for review in reviews:
                admin = review["admin"]
                comment_text = review["comment_text"]
                date = review["date"]
                nick_name = review["nickname"]
                purchases = review["purchases"]
                shop_name = r["name"]

                data = {
                    "admin": admin,
                    "comment_text": comment_text,
                    "date": date,
                    "nick_name": nick_name,
                    "purchases": purchases,
                    "shop_name": shop_name,
                    "token": "D38dlSmdjx3840sSs"
                    }
                hash = await generate_hash(nick_name, shop_name, comment_text)
                
                if not hash in reviews_send:
                    res  = await client.post("https://black-sprut.com/api/v1/commentstores/", data=data)

                    if res.status_code == 200:
                        reviews_send.append(hash)
                    else:
                        success = False

            async with aiofiles.open("reviews.json", "w") as f:
                await f.write(json.dumps(reviews_send))

            if success:
                print("success")
                # await sql(
                #     """
                #     UPDATE stores SET sent = True WHERE name = ?
                #     """,
                #     (r[0]["name"],)
                # )

asyncio.run(send_data())



