# Base image
ARG BUILD_FROM=ghcr.io/home-assistant/home-assistant:stable
FROM $BUILD_FROM

# Install runtime dependencies
RUN apk add --no-cache \
    curl \
    python3 \
    jq \
    rsync \
    yq \
    bash \
    busybox-suid \
    mc 

# Internal add-on directory structure
RUN mkdir -p /etc/nc_backup

# Copy entrypoints and scripts
COPY run.sh /
COPY backup.sh /
COPY rootfs/etc/nc_backup/ /etc/nc_backup/

# Make scripts executable
# Set executable permissions
RUN chmod a+x \
    /run.sh \
    /backup.sh \
    /etc/nc_backup/config.sh \
    /etc/nc_backup/logging.sh

    # Container entrypoint
CMD [ "/run.sh" ]