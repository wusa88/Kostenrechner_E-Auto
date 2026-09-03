# Kostenberechnung E-Auto — schlankes Abbild, reine Standardbibliothek.
FROM python:3.12-slim

LABEL org.opencontainers.image.title="Kostenberechnung E-Auto" \
      org.opencontainers.image.description="Verbrauch, Ladekosten und Benzinvergleich fürs E-Auto" \
      org.opencontainers.image.licenses="MIT"

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    KOSTEN_DATEI=/daten/kosten.json \
    KOSTEN_HOST=0.0.0.0 \
    KOSTEN_PORT=8080

WORKDIR /app

# Kein pip, keine Abhängigkeiten — nur der Quelltext.
COPY app/ ./app/

# Eigener Benutzer; das Datenverzeichnis gehoert ihm.
RUN useradd --system --uid 10001 --home /app kosten \
    && mkdir -p /daten \
    && chown -R kosten:kosten /app /daten
USER kosten

VOLUME ["/daten"]
EXPOSE 8080

HEALTHCHECK --interval=30s --timeout=5s --start-period=5s --retries=3 \
    CMD ["python", "-c", "import os,sys,urllib.request; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:%s/gesundheit' % os.environ['KOSTEN_PORT'], timeout=4).status == 200 else 1)"]

CMD ["python", "-m", "app.server"]
