FROM debian:stable-slim AS driver_dl

ARG DEBIAN_FRONTEND=noninteractive
ARG CNIJFILTER2_URL=https://gdlp01.c-wss.com/gds/0/0100012300/02/cnijfilter2-6.80-1-deb.tar.gz

RUN apt update &&\
    apt install -y wget &&\
    rm -rf /var/lib/apt/lists/* &&\
    mkdir /tmp/drivers

# Download and extract cnijfilter2 package
RUN wget -q -O /tmp/cnijfilter2.deb.tar.gz "${CNIJFILTER2_URL}" &&\
    tar -xvf /tmp/cnijfilter2.deb.tar.gz -C /tmp &&\
    for i in $(find /tmp/cnijfilter2-* -name "*.deb"); do \
        file=$(basename "$i" | sed -E 's/(cnijfilter2)_[0-9.]+-[0-9]+(_.*\.deb)/\1\2/'); \
        mv -v "$i" "/tmp/drivers/$file"; \
    done &&\
    ls -l /tmp/drivers

FROM debian:stable-slim

ARG TARGETARCH
ARG DEBIAN_FRONTEND=noninteractive

RUN apt update &&\
    apt -y --no-install-recommends install \
    cups-daemon \
    cups-client \
    cups-pdf \
    avahi-daemon \
    libnss-mdns \
# for cnijfilter2
    libcupsimage2 \
    libxml2 \
# for mkpasswd
    whois \
# for healthcheck
    curl \
# for avahi/airprint
    inotify-tools \
    libpng16-16 \
    python3-cups \
    python3-lxml \
    cups-tea4cups &&\
    apt autoremove -y &&\
    apt clean -y &&\
    rm -rf /var/lib/apt/lists/* &&\
    rm -rf /tmp/* &&\
    rm -rf /var/tmp/*

# Add and install cnijfilter2 package
RUN --mount=type=bind,from=driver_dl,source=/tmp/drivers,target=/tmp/drivers \
    dpkg -i /tmp/drivers/cnijfilter2_${TARGETARCH}.deb

# TODO: really needed?
#COPY mime/ /etc/cups/mime/

# setup airprint scripts
COPY airprint/ /opt/airprint/

COPY healthcheck.sh start-cups.sh pre-init-script.sh /root/
RUN chmod +x /root/*.sh
HEALTHCHECK \
    --interval=10s \
    --timeout=3s \
    CMD /root/healthcheck.sh

ENV TZ="GMT" \
    CUPS_ADMIN_USER="admin" \
    CUPS_ADMIN_PASSWORD="secr3t" \
    CUPS_WEBINTERFACE="yes" \
    CUPS_SHARE_PRINTERS="yes" \
    CUPS_REMOTE_ADMIN="yes" \
    CUPS_ENV_DEBUG="no" \
    # defaults to $(hostname -i)
    CUPS_IP="" \
    CUPS_ACCESS_LOGLEVEL="config" \
    # example: lpadmin -p Epson-RX520 -D 'my RX520' -m 'gutenprint.5.3://escp2-rx620/expert' -v ipp://10.1.2.3/"
    CUPS_LPADMIN_PRINTER1=""

ENTRYPOINT ["/root/start-cups.sh"]
