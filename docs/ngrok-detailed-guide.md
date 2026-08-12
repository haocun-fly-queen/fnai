# Ngrok 内网穿透 - 详细部署指南

## 🎯 适用场景

- ✅ 快速给同事演示（今天就能用）
- ✅ 本地开发环境直接对外访问
- ✅ 无需购买服务器
- ✅ 完全免费（有限额）

---

## 📋 前置条件

- ✅ 本地项目已经能正常运行
- ✅ 前端能访问：http://localhost:5173
- ✅ 后端能访问：http://localhost:8000

---

## 🚀 部署步骤

### 步骤 1: 注册 Ngrok 账号

1. 访问：https://ngrok.com/
2. 点击右上角 **Sign up** 注册
3. 可以使用 Google/GitHub 账号快速注册
4. 注册完成后会跳转到 Dashboard

### 步骤 2: 下载 Ngrok

#### Windows 用户

1. 在 Dashboard 页面点击 **Download for Windows**
2. 或直接访问：https://ngrok.com/download
3. 下载 `ngrok-v3-stable-windows-amd64.zip`
4. 解压到任意目录（如 `C:\ngrok\`）

#### Mac 用户

```bash
# 使用 Homebrew 安装
brew install ngrok/ngrok/ngrok
```

#### Linux 用户

```bash
# 下载
wget https://bin.equinox.io/c/bNyj1mQVY4c/ngrok-v3-stable-linux-amd64.tgz

# 解压
tar -xvzf ngrok-v3-stable-linux-amd64.tgz

# 移动到系统路径
sudo mv ngrok /usr/local/bin/
```

### 步骤 3: 配置 Authtoken

1. 登录 Ngrok Dashboard：https://dashboard.ngrok.com/
2. 在左侧菜单点击 **Your Authtoken**
3. 复制 Authtoken（类似 `2abc...xyz`）
4. 在终端/命令行中执行：

**Windows（cmd 或 PowerShell）**:
```cmd
cd C:\ngrok
ngrok config add-authtoken YOUR_AUTHTOKEN
```

**Mac/Linux**:
```bash
ngrok config add-authtoken YOUR_AUTHTOKEN
```

执行成功后会显示：
```
Authtoken saved to configuration file: C:\Users\YourName\.ngrok2\ngrok.yml
```

---

## 🔧 方案选择

根据你的需求选择：

### 方案 A: 只穿透前端（最简单）⭐⭐⭐⭐⭐

**适用情况**：
- 后端已经部署在公网服务器
- 只需要演示前端界面

**步骤**：
```bash
# 1. 启动前端
cd E:\workingbuddy\2026-06-18-10-20-53\fnai-monorepo\frontend
npm run dev

# 2. 新开一个终端，启动 ngrok
cd C:\ngrok
ngrok http 5173
```

---

### 方案 B: 同时穿透前后端（推荐）⭐⭐⭐⭐⭐

**适用情况**：
- 前后端都在本地
- 需要完整功能演示

**步骤**：

#### 1. 启动后端（终端1）
```bash
cd E:\workingbuddy\2026-06-18-10-20-53\fnai-monorepo\backend
.venv\Scripts\activate
uvicorn app.main:app --reload --port 8000
```

#### 2. 启动前端（终端2）
```bash
cd E:\workingbuddy\2026-06-18-10-20-53\fnai-monorepo\frontend
npm run dev
```

#### 3. 穿透后端（终端3）
```bash
cd C:\ngrok
ngrok http 8000
```

会显示类似：
```
Forwarding   https://abc123.ngrok-free.app -> http://localhost:8000
```

**记下这个 URL**：`https://abc123.ngrok-free.app`

#### 4. 修改前端 API 地址

临时修改前端配置，让它连接到 ngrok 的后端地址：

**方法 1: 修改环境变量**（推荐）

编辑 `frontend/.env.local`:
```bash
# 创建或编辑 .env.local
VITE_API_BASE=https://abc123.ngrok-free.app/api/v1
```

**方法 2: 修改 Vite 配置**

编辑 `frontend/vite.config.ts`:
```typescript
export default defineConfig({
  // ...
  server: {
    proxy: {
      '/api': {
        target: 'https://abc123.ngrok-free.app',  // 改为你的 ngrok URL
        changeOrigin: true,
      },
    },
  },
});
```

#### 5. 重启前端
```bash
# Ctrl+C 停止前端
# 重新启动
npm run dev
```

#### 6. 穿透前端（终端4）
```bash
cd C:\ngrok
ngrok http 5173
```

会显示：
```
Forwarding   https://xyz789.ngrok-free.app -> http://localhost:5173
```

**这就是给同事的链接**：`https://xyz789.ngrok-free.app`

---

## 📝 给同事的访问说明

### 邮件/消息模板

```
Hi team,

FNAI 微信发布功能已可测试，请访问：

🔗 访问地址: https://xyz789.ngrok-free.app

⚠️ 首次访问说明:
1. 点击链接后，可能会看到 ngrok 警告页面
2. 点击 "Visit Site" 按钮继续访问
3. 即可看到登录页面

📝 测试账号:
- 请自行注册，或使用以下测试账号：
- 邮箱: test@company.com
- 密码: Test123456

🧪 测试重点:
1. 登录功能
2. 文章列表
3. 微信发布功能
4. 发布状态显示

⏰ 有效期: 今天下班前（需保持我的电脑开机）

📞 问题反馈: [你的联系方式]

---
[你的姓名]
```

---

## 🎨 优化体验

### 1. 使用自定义域名（免费版不支持）

免费版 ngrok 会生成随机域名，每次重启都会变化。

**升级到付费版**（$8/月）可以获得：
- 固定域名
- 无警告页面
- 更多并发连接

### 2. 去掉警告页面

免费版首次访问会显示警告页面，付费版可去掉。

**临时方案**：告诉同事点击 "Visit Site" 即可。

### 3. 配置 CORS

确保后端 `.env` 中的 CORS 配置包含 ngrok 域名：

```bash
CORS_ORIGINS=["http://localhost:5173","https://xyz789.ngrok-free.app"]
```

---

## 📊 多窗口管理（推荐）

为了方便管理，推荐使用 Windows Terminal 或 Tmux：

### Windows Terminal（推荐）

1. 下载：https://aka.ms/terminal
2. 打开后按 `Ctrl+Shift+2` 创建新窗格
3. 每个服务一个窗格：

```
┌─────────────┬─────────────┐
│  后端服务   │ 前端服务    │
├─────────────┼─────────────┤
│ Ngrok后端   │ Ngrok前端   │
└─────────────┴─────────────┘
```

### 启动脚本（自动化）

创建 `start-ngrok.bat`:

```batch
@echo off
echo 启动 FNAI 服务...

:: 启动后端
start "后端服务" cmd /k "cd E:\workingbuddy\2026-06-18-10-20-53\fnai-monorepo\backend && .venv\Scripts\activate && uvicorn app.main:app --reload --port 8000"

:: 等待 5 秒
timeout /t 5

:: 启动前端
start "前端服务" cmd /k "cd E:\workingbuddy\2026-06-18-10-20-53\fnai-monorepo\frontend && npm run dev"

:: 等待 10 秒
timeout /t 10

:: 启动 Ngrok - 后端
start "Ngrok后端" cmd /k "cd C:\ngrok && ngrok http 8000"

:: 等待 3 秒
timeout /t 3

:: 启动 Ngrok - 前端
start "Ngrok前端" cmd /k "cd C:\ngrok && ngrok http 5173"

echo.
echo 所有服务已启动！
echo 请在 Ngrok 窗口中查看公网地址
pause
```

双击 `start-ngrok.bat` 即可一键启动所有服务！

---

## 🔍 检查清单

启动后检查：

### ✅ 后端检查
```bash
# 访问本地后端
curl http://localhost:8000/api/v1/health

# 访问 ngrok 后端
curl https://abc123.ngrok-free.app/api/v1/health
```

### ✅ 前端检查
1. 本地访问：http://localhost:5173
2. Ngrok 访问：https://xyz789.ngrok-free.app
3. 查看浏览器控制台，确认 API 请求正常

### ✅ 数据库检查
```bash
# 确认数据库运行
# 如果使用 Docker
docker ps | grep postgres

# 如果本地安装
# 查看 PostgreSQL 服务状态
```

---

## ❓ 常见问题

### Q1: 访问时显示 "Tunnel not found"

**原因**: Ngrok 进程已停止

**解决**: 重新运行 `ngrok http 端口号`

### Q2: 每次重启 URL 都会变

**原因**: 免费版不支持固定域名

**解决方案**:
- **方案 A**: 升级到付费版（$8/月）
- **方案 B**: 每次重启后更新链接发给同事
- **方案 C**: 使用其他工具（Serveo、LocalTunnel）

### Q3: 访问速度慢

**原因**: 
- Ngrok 免费版服务器在国外
- 流量需要绕行

**解决**:
- 升级到付费版
- 或使用国内的类似工具（花生壳、FRP）

### Q4: 同事访问提示连接后端失败

**检查步骤**:
1. 确认后端 ngrok 正在运行
2. 确认前端配置了正确的后端 ngrok 地址
3. 检查 CORS 配置

### Q5: 数据库连接失败

**原因**: 数据库未启动或连接配置错误

**解决**:
```bash
# 检查数据库
psql -h localhost -U fnai -d fnai_dev

# 或启动 Docker 数据库
docker-compose up postgres redis
```

---

## 🛡️ 安全注意事项

### ⚠️ 重要提醒

1. **不要暴露敏感信息**
   - 生产环境数据库
   - 真实的 API Key
   - 用户真实数据

2. **使用测试数据**
   - 创建专门的测试账号
   - 使用测试数据库
   - 测试用的微信配置

3. **及时关闭**
   - 演示结束后关闭 ngrok
   - 不要长期开放本地服务

4. **监控访问**
   - Ngrok 终端会显示访问日志
   - 注意异常访问

---

## 🔄 停止服务

演示结束后：

```bash
# 1. 停止 Ngrok
# 在两个 ngrok 终端按 Ctrl+C

# 2. 停止前端
# 在前端终端按 Ctrl+C

# 3. 停止后端
# 在后端终端按 Ctrl+C
```

---

## 📞 备用方案

如果 Ngrok 不好用，可以试试这些：

### Serveo（无需注册）
```bash
ssh -R 80:localhost:5173 serveo.net
```

### LocalTunnel
```bash
npm install -g localtunnel
lt --port 5173
```

### Cloudflare Tunnel（推荐）
```bash
cloudflared tunnel --url http://localhost:5173
```

---

## 🎉 快速启动模板

### 完整启动流程（复制粘贴）

```bash
# ===== 终端 1: 后端 =====
cd E:\workingbuddy\2026-06-18-10-20-53\fnai-monorepo\backend
.venv\Scripts\activate
uvicorn app.main:app --reload --port 8000

# ===== 终端 2: 前端 =====
cd E:\workingbuddy\2026-06-18-10-20-53\fnai-monorepo\frontend
npm run dev

# ===== 终端 3: Ngrok 后端 =====
cd C:\ngrok
ngrok http 8000
# 复制显示的 URL，如: https://abc123.ngrok-free.app

# ===== 终端 4: 修改前端配置 =====
# 编辑 frontend/.env.local
# VITE_API_BASE=https://abc123.ngrok-free.app/api/v1

# ===== 终端 4: Ngrok 前端 =====
cd C:\ngrok
ngrok http 5173
# 复制显示的 URL，如: https://xyz789.ngrok-free.app
# 这个 URL 发给同事！
```

---

## 📸 截图示例

启动 Ngrok 后看到的界面：

```
ngrok                                                                                           

Session Status                online
Account                       your@email.com (Plan: Free)
Version                       3.0.0
Region                        United States (us)
Latency                       45ms
Web Interface                 http://127.0.0.1:4040
Forwarding                    https://xyz789.ngrok-free.app -> http://localhost:5173

Connections                   ttl     opn     rt1     rt5     p50     p90
                              0       0       0.00    0.00    0.00    0.00
```

**重要信息**:
- `Forwarding` 这行的 `https://xyz789.ngrok-free.app` 就是公网地址
- `Web Interface` 可以在浏览器打开查看访问日志

---

**准备好了吗？开始部署吧！** 🚀

如果有任何问题，随时问我！
