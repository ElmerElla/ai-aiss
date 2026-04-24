# ---- build stage ----
FROM python:3.11-slim AS builder

WORKDIR /app

# 换源：使用阿里云镜像加速 Debian 软件源 (APT)
RUN sed -i 's/deb.debian.org/mirrors.aliyun.com/g' /etc/apt/sources.list.d/debian.sources 

# Install build dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    default-libmysqlclient-dev \
    pkg-config \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
# 换源：使用阿里云镜像加速 Python 包安装 (Pip)
RUN pip config set global.index-url https://pypi.tuna.tsinghua.edu.cn/simple/
RUN pip install --no-cache-dir --prefix=/install --default-timeout=1000 --retries=10 -r requirements.txt


# ---- runtime stage ----
FROM python:3.11-slim AS runtime

# 换源：runtime 阶段也需要加速
RUN sed -i 's/deb.debian.org/mirrors.aliyun.com/g' /etc/apt/sources.list.d/debian.sources

# Install runtime MySQL client library and ffmpeg
RUN apt-get update && apt-get install -y --no-install-recommends \
    libmariadb3 \
    ffmpeg \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Copy installed packages from builder
COPY --from=builder /install /usr/local

# Copy application source
COPY app/ ./app/

# Create non-root user
RUN useradd -m appuser && chown -R appuser /app
USER appuser

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
