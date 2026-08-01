FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV APP_ENV=production

WORKDIR /app

# Dependências do sistema usadas pelo WeasyPrint para gerar PDFs.
RUN apt-get update \
    && apt-get install --no-install-recommends -y \
        fonts-dejavu-core \
        libcairo2 \
        libgdk-pixbuf-2.0-0 \
        libpango-1.0-0 \
        libpangocairo-1.0-0 \
        shared-mime-info \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .

RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir -r requirements.txt

COPY . .

# Em produção, esta pasta deve ser montada num volume persistente. Mantemos a
# criação local para desenvolvimento e para o primeiro arranque.
RUN mkdir -p frontend/static/uploads/branding frontend/static/uploads/jogadores

EXPOSE 8000

CMD ["python", "run.py"]
