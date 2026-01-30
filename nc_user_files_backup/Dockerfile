ARG BUILD_FROM=ghcr.io/home-assistant/home-assistant:stable
FROM $BUILD_FROM

# Install dependencies. mc for testing
RUN apk add --no-cache curl python3 jq rsync yq mc 

# Create directory structure
RUN mkdir -p /etc/nc_backup

# Copy scripts and configs
COPY run.sh /
COPY backup.sh /
COPY rootfs/etc/nc_backup/ /etc/nc_backup/

# Make scripts executable
RUN chmod a+x /run.sh /backup.sh /etc/nc_backup/config.sh /etc/nc_backup/logging.sh

CMD [ "/run.sh" ]