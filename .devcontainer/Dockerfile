FROM mcr.microsoft.com/devcontainers/python:3.14

# uv, copied as a static binary (matches astral's own recommended devcontainer pattern) —
# no curl/install-script needed at build time.
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

# Rename the base image's pre-created non-root user/group to something generic — this
# devcontainer is deliberately editor-agnostic end to end, not just at the tool level. Same
# UID/GID, just relabeled, so this doesn't change any of the permission behavior already
# verified to work.
RUN old_user=$(id -nu 1000) \
    && old_group=$(id -ng 1000) \
    && usermod -l dev -d /home/dev -m "$old_user" \
    && groupmod -n dev "$old_group"

USER dev
