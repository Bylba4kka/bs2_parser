FROM python:3.11
 
WORKDIR /app

RUN apt-get update && apt-get install -y --fix-missing supervisor

COPY ./requirements.txt /app/requirements.txt

RUN pip install --no-cache-dir --upgrade -r /app/requirements.txt

COPY ./app /app
COPY supervisord.conf supervisord.conf

ENTRYPOINT ["supervisord", "-c", "/app/supervisord.conf"]
