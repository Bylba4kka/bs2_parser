import asyncio
import time

# Синхронная функция, требующая пользовательского ввода
def captcha_solver():
    user_input = input("Введите данные: ")
    return user_input

# Асинхронная функция для работы с captcha_solver
async def parse_data():
    loop = asyncio.get_event_loop()
    print("Ожидание ввода...")
    x = await loop.run_in_executor(None, captcha_solver)  # Запуск синхронной функции в отдельном потоке
    some_data = x
    print(f"Получены данные: {some_data}")
    return some_data

# Основная асинхронная функция
async def main():
    tasks = [parse_data() for _ in range(3)]  # Запуск нескольких задач
    results = await asyncio.gather(*tasks)   # Ожидание завершения всех задач
    print("Все задачи завершены!")
    print(results)

# Запуск
if __name__ == "__main__":
    asyncio.run(main())
defaultdict(<class 'list'>, {'http://RACE4z:QfeSTq@45.147.101.245:8000': 
                             ['https://m.bs2site.at/exchanges/11', 'https://m.bs2site.at/exchanges/22', 'https://m.bs2site.at/exchanges/26', 'https://m.bs2site.at/exchanges/6', 'https://m.bs2site.at/exchanges/34', 'https://m.bs2site.at/exchanges/29', 'https://m.bs2site.at/exchanges/32', 'https://m.bs2site.at/exchanges/31', 'https://m.bs2site.at/exchanges/28', 'https://m.bs2site.at/exchanges/18', 'https://m.bs2site.at/exchanges/3'], 
                             'http://RACE4z:QfeSTq@170.83.233.60:8000': ['https://m.bs2site.at/exchanges/5', 'https://m.bs2site.at/exchanges/2', 'https://m.bs2site.at/exchanges/20', 'https://m.bs2site.at/exchanges/15', 'https://m.bs2site.at/exchanges/10', 'https://m.bs2site.at/exchanges/36'], 
                             'http://RACE4z:QfeSTq@45.147.101.134:8000': ['https://m.bs2site.at/exchanges/33', 'https://m.bs2site.at/exchanges/25', 'https://m.bs2site.at/exchanges/35', 'https://m.bs2site.at/exchanges/19', 'https://m.bs2site.at/exchanges/17'], 
                             'http://RACE4z:QfeSTq@45.147.102.219:8000': ['https://m.bs2site.at/exchanges/30', 'https://m.bs2site.at/exchanges/23', 'https://m.bs2site.at/exchanges/21', 'https://m.bs2site.at/exchanges/12', 'https://m.bs2site.at/exchanges/14'], 
                             'http://RACE4z:QfeSTq@45.147.103.116:8000': ['https://m.bs2site.at/exchanges/9', 'https://m.bs2site.at/exchanges/37', 'https://m.bs2site.at/exchanges/13', 'https://m.bs2site.at/exchanges/27', 'https://m.bs2site.at/exchanges/24']})