FROM python:alpine

WORKDIR /home/nmos-testing
ADD . .

RUN apk update \
 && apk add gcc musl-dev linux-headers git \
 && rm -rf /var/cache/apk/* \
 && pip3 install -r requirements.txt \
 && mkdir -p /config \
 && mv Config.py /config/Config.py \
 && ln -s /config/Config.py Config.py

VOLUME /config

ENTRYPOINT ["python3"]
CMD ["nmos-test.py"]
