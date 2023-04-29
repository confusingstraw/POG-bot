FROM python:3.9

RUN apt-get update && apt-get install -y git

RUN python3 -m pip install pdm

ENV BASE_DIR=/pog-bot
ENV LOGGING_DIR=/POG-data/logging
ENV MATCHES_DIR=/POG-data/matches
ENV VIRTUAL_ENV=$BASE_DIR/.venv

RUN mkdir -p $BASE_DIR
RUN mkdir -p $LOGGING_DIR
RUN mkdir -p $MATCHES_DIR

COPY pyproject.toml pdm.lock $BASE_DIR/

WORKDIR $BASE_DIR
RUN python3 -m pdm sync
ENV PATH="$VIRTUAL_ENV/bin:$PATH"

COPY doc/ $BASE_DIR/doc
COPY fonts/ $BASE_DIR/fonts
COPY logos/ $BASE_DIR/logos
COPY media/ $BASE_DIR/media
COPY commands/ $BASE_DIR/commands
COPY bot/ $BASE_DIR/bot
COPY CHANGELOG.md README.md $BASE_DIR/

ENTRYPOINT python3 commands/pog_launcher.py