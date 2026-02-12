FROM python:3.9-slim

WORKDIR /app

# 安装系统依赖（仅在构建时执行一次）
RUN apt-get update && \
    apt-get install -y wget gnupg && \
    rm -rf /var/lib/apt/lists/*

# 安装 Python 依赖（仅在构建时执行一次）
COPY requirements.txt .
RUN pip install -r requirements.txt

# 创建日志目录并设置权限
RUN mkdir -p /app/logs && chmod 777 /app/logs

# 设置时区
ENV TZ=Asia/Shanghai

# 启动应用（每次容器启动执行）
CMD ["python", "-u", "run_sign.py"]
