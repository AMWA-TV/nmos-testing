FROM ubuntu:noble

WORKDIR /home/nmos-testing
ADD . .
ADD .git .git

RUN apt-get update \
    && export DEBIAN_FRONTEND=noninteractive \
    && export PIP_BREAK_SYSTEM_PACKAGES=1 \
    && apt-get install -y wget \
    && wget https://deb.nodesource.com/setup_22.x \
    && chmod 755 setup_22.x \
    && /home/nmos-testing/setup_22.x \
    && apt-get install -y --no-install-recommends \
    gcc openssl libssl-dev wget ca-certificates avahi-daemon avahi-utils libnss-mdns libavahi-compat-libdnssd-dev \
    python3 python3-pip python3-dev nodejs \
    procps ldnsutils libidn12 git coreutils curl bsdmainutils \
    && pip3 install setuptools wheel \
    && pip3 install -r requirements.txt \
    && mkdir -p /config \
    && cp nmostesting/UserConfig.example.py /config/UserConfig.py \
    && ln -s /config/UserConfig.py nmostesting/UserConfig.py \
    && cd testssl \
    && wget https://github.com/drwetter/testssl.sh/archive/v3.0.7.tar.gz \
    && tar -xvzf v3.0.7.tar.gz --strip-components=1 \
    && rm v3.0.7.tar.gz \
    && npm install -g AMWA-TV/sdpoker#v0.3.0 \
    && rm /home/nmos-testing/setup_22.x \
    && apt-get remove -y wget \
    && apt-get clean -y --no-install-recommends \
    && apt-get autoclean -y --no-install-recommends \
    && apt-get autoremove -y \
    && rm -rf /var/lib/apt/lists/*

VOLUME /config

# ensure entrypoint script is executable
RUN chmod +x /home/nmos-testing/run_nmos_testing.sh

ENTRYPOINT ["/home/nmos-testing/run_nmos_testing.sh"]
