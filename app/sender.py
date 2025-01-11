"""
Тут из базы данных отсылаем на эндпоинт данные. Пока только обменники. 
Нужно сделать эндпоинт для магазина (как и с обменникам Один на коменты, другой на данные ну или как будет удобнее).
А лучше вообще на стороне Джанго подтягивать данные из бд, но тут игрвет следующая проблема)
Тут структура одна, там другая, так как разные разработчики были)))))
"""

from datetime import datetime
import json
import time
import httpx
import asyncio
import aiosqlite

from config import DB_NAME, HOST


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
                

async def func_reviews():
    token = 'D38dlSmdjx3840sSs'

    url = f'{HOST}/api/v1/commentexchangers/'
    async with httpx.AsyncClient(timeout=60, verify=False) as client:
        r = client.post(url, data={'delete': True, 'token': token }, verify=False)

        json_data = await sql(
            """
            SELECT * FROM stores
            """
            )
        
        # Тут перекладывает json

        # Создаем словарь с параметрами
        data = {
            'token': token,
            # какая то структура данных -\_(~_~)_/-
            
        }

        # Отправляем запрос на сервер с файлом и другими данными
        response = await client.post(url, data=data)
        print(response)

async def func_exchangers():
    token = 'D38dlSmdjx3840sSs'
    is_active = False
    url = f'{HOST}/api/v1/changeexchangers/'
    async with httpx.AsyncClient(timeout=60, verify=False) as client:
        response = await client.post(url, data={'is_active': is_active, 'token': token})

        json_data = await sql(
            """
            SELECT * FROM stores
            """
            )
        # Тут перекладывает json 
        data = {
            'token': token,
            # какая то структура данных -\_(~_~)_/-
        }

        response = await client.post(url,  data=data)


"""
Запустить как только будет интеграция с сайтом
"""
# Запуск раз в 24 часа
# if __name__ == '__main__':
#     runned_at = datetime.now().strftime('%Y%m%d')
#     while True:
#         time.sleep(3600)
#         now = datetime.now().strftime('%Y%m%d')

#         if runned_at != now:
#             runned_at = datetime.now().strftime('%Y%m%d')
#             asyncio.run(func_exchangers())
#             asyncio.run(func_reviews())
