# 使用 Python 作为基础镜像
FROM python:3.9.12-slim

# 安装系统依赖
RUN apt-get update && apt-get install -y \
    build-essential \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# 设置工作目录
WORKDIR /generative_agents

# 复制项目文件到容器内
COPY . /generative_agents

# 安装依赖
RUN pip install --upgrade pip
RUN pip install --no-cache-dir -r requirements.txt

# 如果有前端依赖，可以在这里添加 Node.js 和 npm 的安装
# RUN apt-get update && apt-get install -y curl
# RUN curl -sL https://deb.nodesource.com/setup_16.x | bash - && apt-get install -y nodejs
# WORKDIR /generative_agents/environment/frontend_ui
# RUN npm install

# 收集静态文件
# 收集静态文件
RUN python /generative_agents/environment/frontend_server/manage.py collectstatic --noinput

# 暴露端口
EXPOSE 8000

# 启动命令（在docker-compose中覆盖）
CMD ["gunicorn", "--bind", "0.0.0.0:8000", "--workers", "3", "environment.frontend_server.wsgi:application"]

