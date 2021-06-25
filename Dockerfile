FROM python:3.8
ENV IS_DOCKER=1
ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1
ENV HOME /home/terrygon
RUN useradd -m -d $HOME -s /bin/bash terrygon
WORKDIR $HOME
RUN apt update && apt install git -y
COPY ./requirements.txt .
RUN pip install --no-compile --no-cache-dir -r requirements.txt
USER terrygon
RUN mkdir -p logs
RUN touch logs/discordLogerrors.log  && touch logs/errors.log && touch logs/events.log && touch logs/main.log && \
touch logs/memes.log && touch logs/misc.log && touch logs/setupcog.log
COPY utils .
CMD ["python3", "main.py"]