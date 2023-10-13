FROM python:3.11.0-alpine3.15

RUN apk add git
RUN pip install --no-cache-dir --prefer-binary lxml

COPY cover2cover.py /opt/cover2cover.py
