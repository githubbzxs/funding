# Funding Rate Arbitrage Monitor

基于 FastAPI 的资金费率套利监控工具，聚合 Binance / OKX / zkLighter / GRVT 的永续合约资金费率，统一为 8h 口径，计算多空最大价差并排序，通过 REST API 和一个简洁的前端展示。

## 一键部署（Linux + systemd）

仓库内附带 `deploy.sh`，在服务器仓库根目录直接执行即可跑起来：

```bash
sudo bash deploy.sh
```

可选环境变量（执行前导出）：

- `APP_NAME`：systemd 服务名，默认 `funding-monitor`
- `PORT`：监听端口，默认 `8000`
- `HOST`：监听地址，默认 `0.0.0.0`
- `WORKERS`：uvicorn worker 数，默认 `1`
- `APP_DIR`：项目路径，默认当前目录
- `APP_USER`：运行用户，默认当前用户
- `VENV_PATH`：虚拟环境路径，默认 `<APP_DIR>/.venv`

部署完成后可通过 `systemctl status APP_NAME.service` 查看状态，访问 `http://HOST:PORT/` 打开前端。

## 手动运行（开发/本地）

```bash
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

- 启动 API/前端：`uvicorn app:app --reload`，访问 `http://127.0.0.1:8000/`
- 启动 CLI 表格：`python main_cli.py`
- API 测试：`curl http://127.0.0.1:8000/api/funding/ranking`

## 其他说明

- 使用公开接口，无需 API Key。
- 自动刷新间隔由 `app.py` 中的 `REFRESH_INTERVAL` 控制。
- OKX 交易对列表在 `exchanges/okx.py` 的 `OKX_INSTRUMENTS`。
