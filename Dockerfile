FROM python:alpine

WORKDIR /home/nmos-testing
ADD . .

RUN apk update \
 && apk add gcc musl-dev linux-headers git libffi-dev \
 && rm -rf /var/cache/apk/* \
 && pip3 install -r requirements.txt \
 && mkdir -p /config \
 && mv Config.py /config/Config.py \
 && ln -s /config/Config.py Config.py \
 && cd testssl \
 && wget https://github.com/drwetter/testssl.sh/archive/3.0rc5.tar.gz \
 && tar -xvzf 3.0rc5.tar.gz --strip-components=1 \
 && rm 3.0rc5.tar.gz

VOLUME /config

ENTRYPOINT ["python3"]
CMD ["nmos-test.py"]
