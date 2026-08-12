# FNAI 微信发布功能 - 超简单部署方案

## 🚀 方案对比

| 方案 | 难度 | 时间 | 费用 | 推荐度 | 适用场景 |
|------|------|------|------|--------|---------|
| **Docker 一键部署** | ⭐ | 5分钟 | 免费 | ⭐⭐⭐⭐⭐ | 最推荐 |
| **Vercel + Serverless** | ⭐⭐ | 10分钟 | 免费 | ⭐⭐⭐⭐ | 前端演示 |
| **Render 一键部署** | ⭐ | 5分钟 | 免费 | ⭐⭐⭐⭐⭐ | 全栈部署 |
| **Railway 一键部署** | ⭐ | 3分钟 | $5/月 | ⭐⭐⭐⭐ | 最简单 |
| **宝塔部署** | ⭐⭐⭐ | 30分钟 | 看服务器 | ⭐⭐⭐ | 已有服务器 |
| **内网穿透 + 本地** | ⭐⭐ | 10分钟 | 免费 | ⭐⭐⭐ | 临时测试 |

---

## 方案 1: Docker 一键部署 ⭐⭐⭐⭐⭐（最推荐）

### 为什么推荐？
- ✅ 一条命令启动全部服务
- ✅ 环境隔离，不污染系统
- ✅ 跨平台（Windows/Mac/Linux）
- ✅ 适合团队协作

### 部署步骤

#### 1. 安装 Docker

**Windows/Mac**: 下载 [Docker Desktop](https://www.docker.com/products/docker-desktop/)

**Linux**:
```bash
curl -fsSL https://get.docker.com | bash
sudo usermod -aG docker $USER
```

#### 2. 创建部署脚本

在项目根目录创建 `docker-compose.yml`:

```yaml
version: '3.8'

services:
  # 数据库
  postgres:
    image: pgvector/pgvector:pg15
    environment:
      POSTGRES_DB: fnai_prod
      POSTGRES_USER: fnai
      POSTGRES_PASSWORD: fnai_password
    volumes:
      - postgres_data:/var/lib/postgresql/data
    ports:
      - "5432:5432"

  # Redis
  redis:
    image: redis:7-alpine
    ports:
      - "6379:6379"

  # 后端
  backend:
    build: 
      context: ./backend
      dockerfile: Dockerfile
    environment:
      DATABASE_URL: postgresql+asyncpg://fnai:fnai_password@postgres:5432/fnai_prod
      REDIS_URL: redis://redis:6379/0
      JWT_SECRET: your-secret-key-change-me
      CORS_ORIGINS: '["http://localhost:3000","http://localhost"]'
    ports:
      - "8000:8000"
    depends_on:
      - postgres
      - redis
    volumes:
      - ./backend:/app
    command: uvicorn app.main:app --host 0.0.0.0 --port 8000

  # 前端
  frontend:
    build:
      context: ./frontend
      dockerfile: Dockerfile
    ports:
      - "80:80"
    depends_on:
      - backend

volumes:
  postgres_data:
```

#### 3. 创建 Dockerfile

**后端 Dockerfile** (`backend/Dockerfile`):
```dockerfile
FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

RUN alembic upgrade head

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
```

**前端 Dockerfile** (`frontend/Dockerfile`):
```dockerfile
FROM node:22-alpine as builder

WORKDIR /app
COPY package*.json ./
RUN npm install
COPY . .
RUN npm run build

FROM nginx:alpine
COPY --from=builder /app/dist /usr/share/nginx/html
COPY nginx.conf /etc/nginx/nginx.conf
EXPOSE 80
CMD ["nginx", "-g", "daemon off;"]
```

#### 4. 一键启动
```bash
# 启动所有服务
docker-compose up -d

# 查看日志
docker-compose logs -f

# 停止服务
docker-compose down
```

#### 5. 访问
```
http://localhost
```

### 给同事使用
```bash
# 1. 克隆代码
git clone https://gitee.com/fengneng_2/geo.git fnai
cd fnai

# 2. 启动（一条命令）
docker-compose up -d

# 3. 访问
打开浏览器: http://localhost
```

---

## 方案 2: Render 一键部署 ⭐⭐⭐⭐⭐（最简单）

### 为什么推荐？
- ✅ 完全免费（有限额）
- ✅ 自动 HTTPS
- ✅ 持续部署（Git 推送自动更新）
- ✅ 无需管理服务器

### 部署步骤

#### 1. 注册 Render
访问: https://render.com/
使用 GitHub/GitLab/Gitee 账号登录

#### 2. 连接仓库
- 点击 **New +** → **Web Service**
- 连接你的 Gitee 仓库
- 选择 `feat/phase3-celery-and-search` 分支

#### 3. 配置服务

**后端服务**:
```
Name: fnai-backend
Environment: Python 3
Build Command: pip install -e .
Start Command: uvicorn app.main:app --host 0.0.0.0 --port 8000
```

**环境变量**:
```
DATABASE_URL=postgresql://...  (Render 自动提供)
REDIS_URL=redis://...          (Render 自动提供)
JWT_SECRET=random_secret_here
```

**前端服务**:
```
Name: fnai-frontend
Environment: Node
Build Command: npm install && npm run build
Start Command: npm run preview
```

#### 4. 部署数据库
- 点击 **New +** → **PostgreSQL**
- 选择免费方案
- 自动连接到后端

#### 5. 访问
Render 会提供一个 URL，如：
```
https://fnai-backend.onrender.com
https://fnai-frontend.onrender.com
```

### 优势
- 自动 SSL 证书
- 免费域名
- 自动备份
- 零维护

---

## 方案 3: Railway 一键部署 ⭐⭐⭐⭐（最快）

### 为什么推荐？
- ✅ 3 分钟部署
- ✅ 一键部署全栈
- ✅ 自动配置所有服务
- ✅ 超简单

### 部署步骤

#### 1. 注册 Railway
访问: https://railway.app/
使用 GitHub 账号登录

#### 2. 创建项目
```
1. 点击 "New Project"
2. 选择 "Deploy from GitHub repo"
3. 连接你的仓库
4. Railway 自动检测并部署
```

#### 3. 添加数据库
```
1. 点击 "Add Plugin"
2. 选择 "PostgreSQL"
3. 自动配置连接
```

#### 4. 访问
Railway 提供域名：
```
https://fnai-production.up.railway.app
```

### 费用
- $5/月（包含数据库、Redis、服务器）
- 前 $5 免费试用

---

## 方案 4: 内网穿透 + 本地部署（临时测试）

### 为什么推荐？
- ✅ 完全免费
- ✅ 使用本地电脑
- ✅ 适合临时演示
- ✅ 10 分钟搞定

### 部署步骤

#### 1. 本地启动服务
```bash
# 启动后端
cd backend
uvicorn app.main:app --port 8000

# 启动前端
cd frontend
npm run dev
```

#### 2. 安装内网穿透工具

**方案 A: Ngrok**（推荐）
```bash
# 下载: https://ngrok.com/download
# 注册并获取 authtoken

# 启动前端穿透
ngrok http 5173

# 启动后端穿透（另一个终端）
ngrok http 8000
```

**方案 B: Cloudflare Tunnel**（免费）
```bash
# 下载: https://developers.cloudflare.com/cloudflare-one/connections/connect-apps/install-and-setup/tunnel-guide

cloudflared tunnel --url http://localhost:5173
```

**方案 C: Serveo**（最简单）
```bash
# 无需安装，直接使用 SSH
ssh -R 80:localhost:5173 serveo.net
```

#### 3. 访问
Ngrok 会给你一个公网地址：
```
https://abc123.ngrok.io
```

发给同事即可访问！

### 优缺点
✅ 完全免费  
✅ 无需配置服务器  
❌ 需要保持电脑开机  
❌ URL 每次重启会变化（免费版）

---

## 方案 5: 虚拟机 + 一键脚本

### 为什么推荐？
- ✅ 公司内网部署
- ✅ 一键安装脚本
- ✅ 适合长期使用

### 一键部署脚本

创建 `deploy.sh`:
```bash
#!/bin/bash

echo "🚀 FNAI 一键部署脚本"

# 检查是否为 root
if [ "$EUID" -ne 0 ]; then 
    echo "请使用 sudo 运行此脚本"
    exit
fi

# 更新系统
apt update && apt upgrade -y

# 安装 Docker
curl -fsSL https://get.docker.com | bash

# 安装 Docker Compose
curl -L "https://github.com/docker/compose/releases/latest/download/docker-compose-$(uname -s)-$(uname -m)" -o /usr/local/bin/docker-compose
chmod +x /usr/local/bin/docker-compose

# 克隆代码
cd /opt
git clone https://gitee.com/fengneng_2/geo.git fnai
cd fnai
git checkout feat/phase3-celery-and-search

# 启动服务
docker-compose up -d

echo "✅ 部署完成！"
echo "访问地址: http://$(hostname -I | awk '{print $1}')"
```

### 使用方法
```bash
# 1. 上传脚本到服务器
# 2. 执行
sudo bash deploy.sh

# 3. 等待完成（约 5 分钟）
```

---

## 🎯 推荐方案选择指南

### 给开发人员测试
→ **Docker 一键部署**（方案 1）
```bash
docker-compose up -d
```

### 给产品/运营测试
→ **内网穿透**（方案 4）
```bash
ngrok http 5173
# 发送链接给他们
```

### 正式部署
→ **Render**（方案 2）或 **Railway**（方案 3）
- 自动 HTTPS
- 稳定可靠
- 持续部署

### 已有宝塔服务器
→ **宝塔部署**
按照之前的宝塔指南操作

---

## 📊 快速对比总结

| 需求 | 推荐方案 | 理由 |
|------|---------|------|
| 最快速度 | Railway | 3分钟 |
| 完全免费 | Docker本地 + Ngrok | 0成本 |
| 最稳定 | 宝塔部署 | 企业级 |
| 最简单 | Render | 零配置 |
| 团队协作 | Docker Compose | 环境一致 |

---

## 🎬 演示视频脚本（可录制给同事）

### 场景 1: Docker 部署演示（5分钟）
```
1. 打开终端
2. git clone 项目
3. cd fnai
4. docker-compose up -d
5. 打开浏览器访问 localhost
6. 演示登录、发布功能
```

### 场景 2: Ngrok 演示（3分钟）
```
1. 本地启动项目
2. ngrok http 5173
3. 复制链接
4. 发送给同事
5. 同事打开链接即可测试
```

---

## ❓ 选择建议

**如果你想让同事快速测试（今天就能用）：**
→ 使用 **内网穿透**（方案 4）

**如果要正式部署给团队使用：**
→ 使用 **Docker** 或 **宝塔**

**如果要对外演示：**
→ 使用 **Render** 或 **Railway**

---

需要我帮你准备其中哪个方案的详细步骤？
