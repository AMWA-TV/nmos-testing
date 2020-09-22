FROM ubuntu:bionic

WORKDIR /home/nmos-testing
ADD . .

RUN apt-get update \
    && export DEBIAN_FRONTEND=noninteractive \
    && apt-get install -y wget \
    && wget https://deb.nodesource.com/setup_14.x \
    && chmod 755 setup_14.x \
    && /home/nmos-testing/setup_14.x \
    && apt-get install -y --no-install-recommends \
    gcc openssl libssl-dev wget ca-certificates avahi-daemon avahi-utils libnss-mdns libavahi-compat-libdnssd-dev \
    python3 python3-pip python3-dev nodejs \
    procps ldnsutils libidn11 git coreutils curl bsdmainutils \
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
    && npm install -g AMWA-TV/sdpoker#v0.2.0 \
    && rm /home/nmos-testing/setup_14.x \
    && apt-get remove -y wget \
    && apt-get clean -y --no-install-recommends \
    && apt-get autoclean -y --no-install-recommends \
    && apt-get autoremove -y \
    && rm -rf /var/lib/apt/lists/* 

VOLUME /config

ENTRYPOINT ["python3"]
CMD ["nmos-test.py"]
