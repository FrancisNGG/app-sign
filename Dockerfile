FROM python:3.9-slim

WORKDIR /app

# 安装系统依赖（仅为Playwright/Chromium）
RUN apt-get update && \
    apt-get install -y \
        libasound2 libatk1.0-0 libatk-bridge2.0-0 libcairo2 libcups2 \
        libdbus-1-3 libdrm2 libgbm1 libnspr4 libnss3 \
        libpango-1.0-0 libxcomposite1 libxdamage1 libxfixes3 libxrandr2 \
        libxkbcommon0 libxss1 libx11-6 libxcb1 libxext6 && \
    rm -rf /var/lib/apt/lists/*

# 安装 Python 依赖
COPY requirements.txt .
RUN pip install -r requirements.txt && \
    playwright install chromium

# 创建日志、配置和缓存目录
RUN mkdir -p /app/logs /app/cache && chmod 777 /app/logs /app/cache

# 设置语言和时区 UTF-8 编码
ENV LANG=C.UTF-8
ENV LC_ALL=C.UTF-8
ENV TZ=Asia/Shanghai
ENV PYTHONIOENCODING=utf-8

# 暴露Web服务端口
EXPOSE 21333

# 启动Web服务（自动管理签到任务）
CMD ["python", "-u", "run_sign.py"]
