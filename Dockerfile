FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1 PYTHONPATH=/app/src
WORKDIR /app

# dependencies first (layer cache), then source
COPY pyproject.toml ./
RUN mkdir -p src/laptop_agent && touch src/laptop_agent/__init__.py && pip install --prefer-binary -e . \
    && rm -rf src
COPY src ./src
COPY scripts ./scripts
COPY ui ./ui
COPY data/policies ./data/policies
COPY docker/entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh && useradd -m app && chown -R app /app
USER app

EXPOSE 8000 8501 8765
ENTRYPOINT ["/entrypoint.sh"]
CMD ["api"]
