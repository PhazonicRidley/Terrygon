FROM python:3.8
ENV IS_DOCKER=1
ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1
ENV BOT_PATH /opt/terrygon
WORKDIR $BOT_PATH
RUN apt update && apt install git -y
COPY ./requirements.txt .
RUN pip install --no-compile --no-cache-dir -r requirements.txt
RUN mkdir -p data/logs
RUN touch data/logs/error.log
RUN touch data/logs/console_output.log
COPY . .
ENTRYPOINT ["bash", "docker-entrypoint.sh"]
#ENTRYPOINT ["python3", "terrygon.py"]