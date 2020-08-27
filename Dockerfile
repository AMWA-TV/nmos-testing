FROM python:alpine

WORKDIR /home/nmos-testing
ADD . .

RUN apk update \
 && apk add bash gcc musl-dev linux-headers git libffi-dev openssl-dev procps drill git coreutils libidn nodejs npm \
 && rm -rf /var/cache/apk/* \
 && pip3 install -r requirements.txt \
 && mkdir -p /config \
 && mv nmostesting/Config.py /config/Config.py \
 && ln -s /config/Config.py nmostesting/Config.py \
 && cd testssl \
 && wget https://github.com/drwetter/testssl.sh/archive/3.0rc5.tar.gz \
 && tar -xvzf 3.0rc5.tar.gz --strip-components=1 \
 && rm 3.0rc5.tar.gz \
 && npm config set unsafe-perm true \
 && npm install -g AMWA-TV/sdpoker#v0.2.0

VOLUME /config

ENTRYPOINT ["python3"]
CMD ["nmos-test.py"]
