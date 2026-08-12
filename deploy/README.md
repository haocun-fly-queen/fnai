# FNAI 内容平台 - 部署包

一键启动的 AI 辅助内容创作与发布平台。

## 功能特性

- 📝 AI 辅助写作（文章生成、改写、润色）
- 📚 知识库管理（文档上传、智能检索）
- 🚀 一键发布（微信公众号、微博）
- 👥 多租户支持（多团队独立使用）

---

## 系统要求

- **Windows 10/11** (64位)
- **Docker Desktop** (必须安装)
- **8GB+ 内存**（推荐 16GB）
- **20GB+ 可用磁盘空间**

---

## 安装步骤

### 1. 安装 Docker Desktop（首次使用）

如果还没安装 Docker Desktop：

1. 访问 https://www.docker.com/products/docker-desktop/
2. 下载 Windows 版本并安装
3. 安装完成后**重启电脑**
4. 启动 Docker Desktop，等待右下角托盘图标显示绿色

### 2. 配置环境变量

1. 双击运行 `启动.bat`
2. 首次运行会自动创建 `.env` 文件并用记事本打开
3. **必须填写**以下配置：

   ```ini
   # 你的阿里云 DashScope API Key（访问 https://dashscope.console.aliyun.com/ 获取）
   OPENAI_API_KEY=sk-xxxxxxxxxxxxxxx
   
   # 安全密钥（随便改成一个长字符串，比如键盘乱按 32 个字符）
   JWT_SECRET=随机生成的长字符串请替换这里
   ```

4. 保存并关闭记事本

### 3. 启动应用

1. 再次双击 `启动.bat`
2. **首次启动**会下载 Docker 镜像（约 2-5 分钟，取决于网速）
3. 看到"✅ All services started!"后，浏览器会自动打开 http://localhost:3000

---

## 使用

### 启动应用

双击 `启动.bat`，等待浏览器自动打开。

### 停止应用

双击 `停止.bat`。数据会保存，下次启动时恢复。

### 访问地址

- **前端页面**: http://localhost:3000
- **后端 API**: http://localhost:8000
- **API 文档**: http://localhost:8000/docs

### 首次登录

1. 访问 http://localhost:3000
2. 点击"注册"创建管理员账号
3. 登录后即可使用

---

## 常见问题

### 启动时提示"Docker Desktop is not running"

**解决**: 先启动 Docker Desktop（桌面图标或开始菜单），等托盘图标变绿后再运行 `启动.bat`。

### 启动很慢或卡住

**可能原因**:
1. 首次启动需要下载镜像（耐心等待 5-10 分钟）
2. 电脑内存不足（关闭其他占内存的程序）
3. Docker Desktop 配置的资源太少（设置 → Resources → 调高 Memory 到 6GB+）

### 浏览器打开后显示"无法连接"

**解决**:
1. 等待 1-2 分钟（后端启动需要时间）
2. 检查 Docker Desktop 是否所有容器都在运行（绿色图标）
3. 手动访问 http://localhost:8000/api/v1/health 看是否返回 `{"status":"ok"}`

### 端口被占用（3000 或 8000）

**解决**: 
1. 关闭占用端口的其他程序
2. 或修改 `docker-compose.yml` 中的端口映射：
   ```yaml
   ports:
     - "13000:80"  # 改成其他端口，如 13000
   ```

### 微博"自动获取 Cookie"无法使用

这是正常的——该功能依赖本机浏览器，只能在开发者本机使用。

**同事使用时**: 让他们手动打开 https://m.weibo.cn 登录后，F12 → Network → 复制任意请求的 Cookie，粘贴进配置页面即可。

---

## 数据管理

### 数据存储位置

所有数据（数据库、上传文件）存在 Docker volumes 中，通过以下命令查看：

```bash
docker volume ls
# 会看到 fnai-app_postgres-data、fnai-app_storage-data 等
```

### 备份数据

```bash
# 停止服务
停止.bat

# 导出数据库
docker run --rm -v fnai-app_postgres-data:/data -v %cd%:/backup busybox tar czf /backup/postgres-backup.tar.gz -C /data .

# 导出文件存储
docker run --rm -v fnai-app_storage-data:/data -v %cd%:/backup busybox tar czf /backup/storage-backup.tar.gz -C /data .
```

### 清空所有数据（重新开始）

⚠️ **警告：会删除所有文章、用户、配置，无法恢复！**

```bash
# 停止并删除所有容器和数据
cd deploy
docker-compose down -v
```

---

## 技术支持

遇到问题请联系开发者，提供以下信息：

1. 错误截图
2. `启动.bat` 窗口的完整输出
3. Docker Desktop 容器状态截图

---

## 更新应用

收到新版本后：

1. 停止应用：`停止.bat`
2. 替换整个 `deploy` 文件夹（数据在 Docker volumes 里，不会丢）
3. 启动应用：`启动.bat`（会自动拉取新镜像）

---

**祝使用愉快！** 🎉
