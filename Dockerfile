FROM python:3.11
 
WORKDIR /app

RUN apt-get update && apt-get install -y --fix-missing supervisor

COPY ./requirements.txt /app/requirements.txt

RUN pip install --no-cache-dir --upgrade -r /app/requirements.txt

COPY ./app /app

ENTRYPOINT ["supervisord", "-c", "/app/supervisord.conf"]
