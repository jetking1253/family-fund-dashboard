FROM python:3.11-slim

WORKDIR /app

# 安装依赖（先拷贝 requirements 利用 Docker 缓存层）
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 拷贝全部源码
COPY . .

# Streamlit 默认端口
EXPOSE 8501

# 健康检查（Render 会用这个判断容器是否就绪）
HEALTHCHECK CMD curl --fail http://localhost:8501/_stcore/health || exit 1

# 启动命令
CMD ["streamlit", "run", "app.py", \
     "--server.port=8501", \
     "--server.address=0.0.0.0", \
     "--server.headless=true", \
     "--browser.gatherUsageStats=false"]
