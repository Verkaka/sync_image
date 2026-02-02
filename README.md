# Docker 镜像同步工具

一个用于批量同步 Docker 镜像到指定仓库的命令行工具，支持跨架构（ARM/AMD64）镜像同步。

## 功能特性

- 🚀 批量同步多个 Docker 镜像
- 🏗️ 支持指定目标架构（ARM64/AMD64）
- 📊 实时显示同步进度和结果报告
- ✅ 自动处理镜像标签和命名转换
- 🌐 Web 界面支持，可视化操作
- 🔍 镜像版本搜索功能，快速查找可用tags

## 使用方法

### Web 界面（推荐）

1. **安装依赖**
   ```bash
   pip install -r requirements.txt
   ```

2. **启动 Web 服务**
   ```bash
   python app.py
   ```

3. **访问界面**
   打开浏览器访问 `http://localhost:8080`

4. **使用界面**
   - **Docker Hub 认证（推荐）**：
     - 在搜索区域或同步表单中输入 Docker Hub 用户名和密码/Token
     - 使用认证可以避免速率限制（匿名用户：100次/6小时，认证用户：200次/6小时）
     - 可以使用 Access Token 代替密码（更安全）
   - **搜索镜像**：
     - **Docker Hub**：支持两种搜索模式
       - 搜索镜像名称：输入关键词（如 `nginx`），选择"搜索镜像名称"，可模糊搜索所有匹配的镜像
       - 搜索版本Tags：输入完整镜像名（如 `nginx`），选择"搜索版本Tags"，可查看该镜像的所有版本
     - **私有仓库**：在Registry框中输入仓库地址（如 `registry.example.com`），输入镜像名称，搜索该镜像的所有版本
   - **添加镜像**：
     - 搜索镜像名称时，点击镜像可查看其所有版本
     - 点击搜索结果中的版本标签，可自动添加到镜像列表
   - **手动输入**：在文本框中输入镜像列表（每行一个，格式：`image:tag`）
   - **设置参数**：设置目标仓库和架构
   - **开始同步**：点击"开始同步"按钮
   - **查看结果**：实时查看同步日志和结果报告

### 命令行界面

### 基本用法

```bash
python sync_image.py <镜像1> <镜像2> ... [选项]
```

### 示例

```bash
# 同步单个镜像（默认 ARM 架构）
python sync_image.py nginx:latest

# 同步多个镜像
python sync_image.py nginx:latest redis:7.0 alpine:3.18

# 指定 AMD64 架构
python sync_image.py nginx:latest --arch amd64

# 指定目标仓库
python sync_image.py nginx:latest --repo your-registry.com/namespace
```

### 参数说明

- `images`: 一个或多个原始镜像名（必需），格式为 `image:tag`
- `--repo`: 目标仓库地址（可选），默认为 `devops-docker-bkrepo.glmszq.com/l10b3a/docker-local`
- `--arch`: 目标架构（可选），可选值：`arm`（默认）或 `amd64`

## 工作原理

工具会为每个镜像执行以下步骤：

1. **拉取镜像**: `docker pull --platform <架构> <源镜像>`
2. **标记镜像**: `docker tag <源镜像> <目标镜像>`
3. **推送镜像**: `docker push <目标镜像>`

镜像名称会自动转换：源镜像 `registry.com/namespace/image:tag` 会被转换为 `目标仓库/image:tag`

## 项目结构

```
sync_image/
├── sync_image.py      # 核心同步逻辑
├── image_search.py    # 镜像搜索模块
├── app.py             # Flask Web 应用
├── templates/
│   └── index.html     # Web 前端界面
├── requirements.txt   # Python 依赖
└── README.md          # 项目文档
```

## 前置要求

- Python 3.6+
- Docker CLI（已安装并配置）
- 对目标仓库的推送权限
- （Web 界面）Flask 和 flask-cors 库

## 注意事项

- **Docker Hub 速率限制**：
  - 匿名用户：100次拉取/6小时
  - 认证用户：200次拉取/6小时
  - 建议使用 Docker Hub 用户名和密码/Token 进行认证
- **获取 Docker Hub Access Token**：
  1. 登录 Docker Hub (https://hub.docker.com)
  2. 进入 Account Settings > Security
  3. 创建新的 Access Token
  4. 使用 Token 作为密码进行认证（更安全）
- 确保已登录到目标 Docker 仓库（用于推送）
- 镜像格式必须包含标签（`image:tag`），否则会被跳过
- 同步失败时会返回非零退出码
