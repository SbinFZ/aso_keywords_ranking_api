# macOS 本地一键启动（中文）

以下步骤适用于 macOS，目标是“一键跑起来”（`make run`）。

## 1. 安装依赖

确保已经安装 `python3`（推荐 3.10+）。

## 2. 进入项目目录并安装依赖

```bash
cd /Users/sbin/Downloads/aso_keywords_ranking_api
make install
```

## 3. 一键启动服务

```bash
make run
```

默认监听 `http://127.0.0.1:8000`，API 文档：`http://127.0.0.1:8000/docs`

## 4. 可选：运行本地测试

```bash
make test
```

## 常见问题

* 如果 `make install` 失败，请先升级 pip：`python3 -m pip install --upgrade pip`
* 如果端口被占用：`export PORT=8001` 后手动运行 `uvicorn app.main:app --reload --port $PORT`
