# FNAI 微信发布功能 - 宝塔部署指南

## 📋 目录

1. [环境要求](#环境要求)
2. [宝塔面板准备](#宝塔面板准备)
3. [部署步骤](#部署步骤)
4. [配置说明](#配置说明)
5. [测试验证](#测试验证)
6. [常见问题](#常见问题)

---

## 🔧 环境要求

### 服务器配置
- **CPU**: 2核+
- **内存**: 4GB+
- **磁盘**: 20GB+
- **系统**: CentOS 7+ / Ubuntu 18.04+
- **宝塔版本**: 7.9.0+

### 软件要求
- Python 3.12+
- Node.js 22+
- PostgreSQL 15+
- Redis 7+
- Nginx 1.20+

---

## 🎯 宝塔面板准备

### 1. 安装宝塔面板（如未安装）

#### CentOS
```bash
yum install -y wget && wget -O install.sh https://download.bt.cn/install/install_6.0.sh && sh install.sh
```

#### Ubuntu
```bash
wget -O install.sh https://download.bt.cn/install/install-ubuntu_6.0.sh && sudo bash install.sh
```

### 2. 安装必要软件

登录宝塔面板（默认端口 8888）：
```
http://your-server-ip:8888
```

进入 **软件商店**，安装以下软件：

#### ✅ 必装软件
- **Nginx** 1.20+
- **PostgreSQL** 15+
- **Redis** 7+
- **Python项目管理器** (可选，推荐)
- **PM2管理器** 5.2+ (用于管理 Node.js 和 Python 进程)

#### 安装 Python 3.12
```bash
# SSH 登录服务器后执行
cd /www/server
wget https://www.python.org/ftp/python/3.12.0/Python-3.12.0.tgz
tar -xzf Python-3.12.0.tgz
cd Python-3.12.0
./configure --prefix=/usr/local/python3.12
make && make install

# 创建软链接
ln -s /usr/local/python3.12/bin/python3.12 /usr/bin/python3.12
ln -s /usr/local/python3.12/bin/pip3.12 /usr/bin/pip3.12
```

#### 安装 Node.js 22
```bash
# 通过宝塔面板 -> 软件商店 -> PM2管理器 -> 设置 -> 版本管理
# 或手动安装
curl -fsSL https://rpm.nodesource.com/setup_22.x | bash -
yum install -y nodejs
```

---

## 🚀 部署步骤

### 步骤 1: 创建网站

1. 登录宝塔面板
2. 点击 **网站** → **添加站点**
3. 填写信息：
   - **域名**: `fnai.yourdomain.com` 或服务器 IP
   - **根目录**: `/www/wwwroot/fnai`
   - **PHP 版本**: 纯静态
   - **数据库**: 不创建（后面单独创建）

### 步骤 2: 创建数据库

1. 点击 **数据库** → **添加数据库**
2. 填写信息：
   - **数据库名**: `fnai_prod`
   - **用户名**: `fnai`
   - **密码**: `your_secure_password`（建议使用随机密码）
   - **访问权限**: 本地服务器

### 步骤 3: 上传代码

#### 方法 A: 通过 Git（推荐）

```bash
# SSH 登录服务器
cd /www/wwwroot
rm -rf fnai  # 删除之前创建的空目录

# 克隆代码
git clone https://gitee.com/fengneng_2/geo.git fnai
cd fnai
git checkout feat/phase3-celery-and-search

# 设置权限
chown -R www:www /www/wwwroot/fnai
```

#### 方法 B: 通过宝塔面板上传

1. 在宝塔面板 **文件** 中进入 `/www/wwwroot/fnai`
2. 点击 **上传** → 上传代码压缩包
3. 解压后删除压缩包

### 步骤 4: 配置后端

#### 4.1 创建 Python 虚拟环境

```bash
cd /www/wwwroot/fnai/backend

# 创建虚拟环境
python3.12 -m venv .venv

# 激活虚拟环境
source .venv/bin/activate

# 升级 pip
pip install --upgrade pip

# 安装依赖
pip install -e .
```

#### 4.2 配置环境变量

```bash
cd /www/wwwroot/fnai/backend

# 创建 .env 文件
cat > .env << 'EOF'
# ----- App -----
APP_NAME=FNAI Backend
ENVIRONMENT=production
DEBUG=false

# ----- Database -----
DATABASE_URL=postgresql+asyncpg://fnai:your_secure_password@localhost:5432/fnai_prod
DATABASE_URL_SYNC=postgresql://fnai:your_secure_password@localhost:5432/fnai_prod

# ----- Redis -----
REDIS_URL=redis://localhost:6379/0
CELERY_BROKER_URL=redis://localhost:6379/1
CELERY_RESULT_BACKEND=redis://localhost:6379/2

# ----- Auth -----
JWT_SECRET=请更改为随机字符串
ACCESS_TOKEN_EXPIRE_MINUTES=15
REFRESH_TOKEN_EXPIRE_DAYS=7

# ----- AI -----
OPENAI_API_KEY=your_openai_key
OPENAI_BASE_URL=https://api.openai.com/v1
OPENAI_EMBEDDING_MODEL=text-embedding-3-small
OPENAI_CHAT_MODEL=gpt-4o-mini

# ----- CORS -----
CORS_ORIGINS=["http://fnai.yourdomain.com","http://your-server-ip"]
EOF

# 生成随机 JWT_SECRET
JWT_SECRET=$(openssl rand -hex 32)
sed -i "s/JWT_SECRET=请更改为随机字符串/JWT_SECRET=$JWT_SECRET/" .env

# 替换数据库密码
read -p "输入数据库密码: " DB_PASSWORD
sed -i "s/your_secure_password/$DB_PASSWORD/g" .env
```

#### 4.3 数据库迁移

```bash
cd /www/wwwroot/fnai/backend
source .venv/bin/activate

# 执行迁移
alembic upgrade head
```

#### 4.4 使用 PM2 管理后端进程

在宝塔面板中：

1. 点击 **软件商店** → **PM2管理器** → **设置**
2. 点击 **添加项目**
3. 填写信息：
   - **项目名称**: `fnai-backend`
   - **启动文件**: `/www/wwwroot/fnai/backend/.venv/bin/uvicorn`
   - **运行目录**: `/www/wwwroot/fnai/backend`
   - **启动参数**: `app.main:app --host 0.0.0.0 --port 8000`
   - **环境变量**: 留空（使用 .env 文件）

或通过命令行：

```bash
cd /www/wwwroot/fnai/backend

# 创建 PM2 配置文件
cat > ecosystem.config.js << 'EOF'
module.exports = {
  apps: [{
    name: 'fnai-backend',
    script: '.venv/bin/uvicorn',
    args: 'app.main:app --host 0.0.0.0 --port 8000',
    cwd: '/www/wwwroot/fnai/backend',
    interpreter: 'none',
    instances: 1,
    autorestart: true,
    watch: false,
    max_memory_restart: '1G',
    env: {
      NODE_ENV: 'production'
    }
  }]
};
EOF

# 启动
pm2 start ecosystem.config.js
pm2 save
pm2 startup
```

### 步骤 5: 配置前端

#### 5.1 安装依赖并构建

```bash
cd /www/wwwroot/fnai/frontend

# 安装依赖
npm install

# 构建生产版本
npm run build
```

构建完成后，静态文件在 `dist` 目录

#### 5.2 配置 Nginx

在宝塔面板中：

1. 点击 **网站** → 找到刚创建的站点 → 点击 **设置**
2. 点击 **网站目录** → 修改为 `/www/wwwroot/fnai/frontend/dist`
3. 点击 **配置文件**，替换为以下内容：

```nginx
server {
    listen 80;
    server_name fnai.yourdomain.com;  # 改为你的域名或 IP
    
    # 前端静态文件
    root /www/wwwroot/fnai/frontend/dist;
    index index.html;
    
    # 访问日志
    access_log /www/wwwlogs/fnai_access.log;
    error_log /www/wwwlogs/fnai_error.log;
    
    # Gzip 压缩
    gzip on;
    gzip_vary on;
    gzip_min_length 1024;
    gzip_types text/plain text/css text/xml text/javascript application/javascript application/json;
    
    # 前端路由
    location / {
        try_files $uri $uri/ /index.html;
    }
    
    # 后端 API 代理
    location /api/ {
        proxy_pass http://127.0.0.1:8000/api/;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection 'upgrade';
        proxy_set_header Host $host;
        proxy_cache_bypass $http_upgrade;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        
        # 超时设置
        proxy_connect_timeout 300;
        proxy_send_timeout 300;
        proxy_read_timeout 300;
    }
    
    # 静态资源缓存
    location ~* \.(jpg|jpeg|png|gif|ico|css|js|svg|woff|woff2|ttf|eot)$ {
        expires 30d;
        add_header Cache-Control "public, immutable";
    }
}
```

4. 点击 **保存** → **重载配置**

### 步骤 6: 配置 SSL（可选但推荐）

1. 在宝塔面板 → **网站** → 找到站点 → **设置**
2. 点击 **SSL** → **Let's Encrypt**
3. 勾选域名 → 点击 **申请**
4. 等待证书申请完成
5. 开启 **强制 HTTPS**

---

## ✅ 测试验证

### 1. 检查后端服务

```bash
# 检查进程
pm2 list

# 查看日志
pm2 logs fnai-backend

# 测试 API
curl http://localhost:8000/api/v1/health
```

### 2. 检查前端

访问：`http://your-server-ip` 或 `http://fnai.yourdomain.com`

### 3. 完整测试流程

1. **注册账号**
   - 访问 `/register`
   - 填写信息注册

2. **登录系统**
   - 使用注册的账号登录

3. **配置微信公众号**
   - 进入"发布目标管理"
   - 添加微信配置

4. **测试发布**
   - 创建或编辑文章
   - 点击"发布到微信公众号"
   - 验证发布状态

---

## 🔧 配置说明

### 防火墙配置

在宝塔面板 → **安全** → 放行以下端口：
- **80** (HTTP)
- **443** (HTTPS)
- **8888** (宝塔面板)

如果使用云服务器，还需在云服务商控制台配置安全组。

### 定时任务（可选）

在宝塔面板 → **计划任务** → 添加任务：

**任务 1: 更新微信发布状态**
```
类型: Shell脚本
任务名称: 更新微信发布状态
执行周期: 每5分钟
脚本内容:
cd /www/wwwroot/fnai/backend && \
source .venv/bin/activate && \
python -m app.scripts.update_wechat_status
```

**任务 2: 数据库备份**
```
类型: 备份数据库
任务名称: FNAI数据库备份
执行周期: 每天凌晨2点
选择数据库: fnai_prod
```

---

## 📊 监控和维护

### 查看服务状态

#### 后端服务
```bash
pm2 status
pm2 logs fnai-backend --lines 50
```

#### 数据库
在宝塔面板 → **数据库** → 点击数据库名称 → **性能监控**

#### Nginx
在宝塔面板 → **网站** → 点击站点 → **日志**

### 重启服务

#### 重启后端
```bash
pm2 restart fnai-backend
```

#### 重启 Nginx
在宝塔面板 → **软件商店** → **Nginx** → **重启**

### 更新代码

```bash
cd /www/wwwroot/fnai

# 拉取最新代码
git pull origin feat/phase3-celery-and-search

# 更新后端
cd backend
source .venv/bin/activate
pip install -e .
alembic upgrade head
pm2 restart fnai-backend

# 更新前端
cd ../frontend
npm install
npm run build
```

---

## ❓ 常见问题

### Q1: 后端启动失败

**检查日志**:
```bash
pm2 logs fnai-backend
```

**常见原因**:
- 数据库连接失败 → 检查 `.env` 中的数据库配置
- 端口被占用 → 修改端口或停止占用进程
- Python 版本不对 → 确认使用 Python 3.12+

### Q2: 前端显示 404

**检查 Nginx 配置**:
1. 网站目录是否指向 `/www/wwwroot/fnai/frontend/dist`
2. 配置文件中 `try_files` 是否正确

### Q3: API 请求 502

**原因**: 后端服务未启动

**解决**:
```bash
pm2 restart fnai-backend
```

### Q4: 数据库连接失败

**检查 PostgreSQL**:
```bash
# 查看数据库状态
systemctl status postgresql

# 测试连接
psql -h localhost -U fnai -d fnai_prod
```

### Q5: 静态文件无法加载

**检查权限**:
```bash
chown -R www:www /www/wwwroot/fnai
chmod -R 755 /www/wwwroot/fnai
```

---

## 📝 给同事的访问说明

### 邮件模板

```
主题: [通知] FNAI 测试环境已部署

Hi team,

FNAI 微信公众号发布功能测试环境已在宝塔服务器上部署完成。

访问地址: http://your-server-ip
(或 https://fnai.yourdomain.com)

测试账号: 
请自行注册，注册地址: http://your-server-ip/register

功能说明:
- 文章管理
- 微信公众号发布
- 发布状态查看

测试文档:
http://your-server-ip/docs/wechat-publish-status-guide.md

问题反馈:
请联系 [你的姓名] ([你的联系方式])

---
部署时间: [当前时间]
服务器: 宝塔面板
```

---

## 🔒 安全建议

### 1. 修改宝塔默认端口
```
面板设置 → 面板端口 → 改为非 8888 端口
```

### 2. 设置强密码
- 宝塔面板密码
- 数据库密码
- JWT_SECRET

### 3. 启用 IP 白名单（可选）
```
面板设置 → 授权IP → 添加允许访问的 IP
```

### 4. 定期备份
- 数据库每日备份
- 代码定期提交到 Git
- 备份文件下载到本地

---

## 📞 技术支持

部署过程中遇到问题，请联系：
- 开发负责人: [你的姓名]
- 钉钉/微信: [你的联系方式]
- 邮箱: [你的邮箱]

---

**部署完成，祝使用愉快！** 🎉
