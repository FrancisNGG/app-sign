FROM python:3.9-slim

WORKDIR /app

# 安装系统依赖（仅在构建时执行一次）
RUN apt-get update && \
    apt-get install -y \
        wget gnupg \
        libasound2 libatk1.0-0 libatk-bridge2.0-0 libcairo2 libcups2 \
        libdbus-1-3 libdrm2 libgbm1 libnspr4 libnss3 \
        libpango-1.0-0 libxcomposite1 libxdamage1 libxfixes3 libxrandr2 \
        libxkbcommon0 libxss1 libx11-6 libxcb1 libxext6 && \
    rm -rf /var/lib/apt/lists/*

# 安装 Python 依赖（仅在构建时执行一次）
COPY requirements.txt .
RUN pip install -r requirements.txt && \
    playwright install chromium

# 创建日志目录并设置权限
RUN mkdir -p /app/logs && chmod 777 /app/logs

# 设置语言和时区 UTF-8 编码
ENV LANG=C.UTF-8
ENV LC_ALL=C.UTF-8
ENV TZ=Asia/Shanghai
ENV PYTHONIOENCODING=utf-8

# 启动应用（每次容器启动执行）
CMD ["python", "-u", "run_sign.py"]
