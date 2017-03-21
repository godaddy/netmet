FROM alpine:latest
MAINTAINER Sushant Bhadkamkar
RUN apk add --update \
    build-base \
    linux-headers \
    python \
    python-dev \
    py-pip

COPY . /app
WORKDIR /app

RUN pip install -r requirements.txt \
    && python setup.py install

EXPOSE 5000
