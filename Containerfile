FROM ghcr.io/ublue-os/base-main:latest

COPY build.sh /tmp/build.sh
COPY chi-agent/ /usr/share/chi-agent/
COPY chi-overlay/ /usr/share/chi-overlay/
COPY chi-voice/ /usr/share/chi-voice/
COPY chi-shell/ /usr/share/chi-shell/
COPY quadlets/ /usr/share/chi-quadlets/
COPY configs/ /usr/share/chi-configs/
COPY post-install/ /usr/share/chi-post-install/

RUN /tmp/build.sh && rm /tmp/build.sh

LABEL org.opencontainers.image.title="chiOS"
LABEL org.opencontainers.image.description="AI-native OS for software engineers"
LABEL org.opencontainers.image.source="https://github.com/matoval/chios"
