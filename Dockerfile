FROM ubuntu:bionic

WORKDIR /home/nmos-testing
ADD . .

RUN apt-get update \
    && export DEBIAN_FRONTEND=noninteractive \
    && apt-get install -y --no-install-recommends \
    gcc openssl libssl1.0-dev wget ca-certificates avahi-daemon avahi-utils libnss-mdns libavahi-compat-libdnssd-dev \
    python3 python3-pip nodejs nodejs-dev node-gyp npm \
    bash procps ldnsutils libidn11 git coreutils curl bsdmainutils \
    && rm -rf /var/lib/apt/lists/* \
    && apt-get clean -y --no-install-recommends \
    && apt-get autoclean -y --no-install-recommends \
    && pip3 install setuptools wheel \
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
