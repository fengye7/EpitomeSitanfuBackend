FROM python:3.9.12-slim

# 安装系统依赖
RUN apt-get update && apt-get install -y \
    build-essential \
    libpq-dev \
    && apt-get clean && rm -rf /var/lib/apt/lists/*

# 设置工作目录（后续会被 docker-compose 覆盖）
WORKDIR /app

# 复制项目文件
COPY . .

# 安装依赖
RUN pip install --no-cache-dir -r requirements.txt

# 收集静态文件
RUN python environment/frontend_server/manage.py collectstatic --noinput

# 暴露端口
EXPOSE 8000

# 默认启动命令（会被 docker-compose 覆盖）
CMD ["gunicorn", "--bind", "0.0.0.0:8000", "frontend_server.wsgi:application"]