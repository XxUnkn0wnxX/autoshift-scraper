FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

# Install deps (add tzdata so ZoneInfo works in slim images)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt \
    && pip install --no-cache-dir tzdata

COPY . .

# Shell form so ${PARSER_ARGS} expands at runtime
CMD python ./autoshift_scraper.py --user "${GITHUB_USER}" --repo "${GITHUB_REPO}" --token "${GITHUB_TOKEN}" ${PARSER_ARGS}
