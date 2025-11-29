# Funding Rate Arbitrage Monitor

基于 FastAPI 的资金费率套利监控工具，聚合 Binance / OKX / zkLighter / GRVT 的永续合约资金费率，统一为 8h 口径，计算多空最大价差并排序，通过 REST API 和一个简洁的前端展示。

## 一行部署（全新服务器）

直接在新服务器执行一行命令完成克隆 + 安装依赖 + systemd 运行：

```bash
bash -c "git clone https://github.com/githubbzxs/funding funding && cd funding && sudo APP_USER=$(whoami) bash deploy.sh"
```

如果服务器还没有安装 git，可以用这一行（自动检测 apt/dnf/yum）：

```bash
bash -c "pm=$(command -v apt-get || command -v dnf || command -v yum); if [ -n \"$pm\" ]; then sudo $pm update -y >/dev/null 2>&1 || true; sudo $pm install -y git; fi; git clone https://github.com/githubbzxs/funding funding && cd funding && sudo APP_USER=$(whoami) bash deploy.sh"
```

说明：
- `deploy.sh` 会自动用 apt/dnf/yum 安装 python3/pip/git/systemd（需要 sudo 权限）。
- 默认监听 `0.0.0.0:8000`，服务名 `funding-monitor`，使用虚拟环境 `<APP_DIR>/.venv`。
- 自定义参数可在一行命令前添加，例如：

```bash
APP_NAME=funding-prod PORT=9000 WORKERS=2 bash -c "git clone <REPO_URL> funding && cd funding && sudo APP_USER=$(whoami) bash deploy.sh"
```

部署完成后：
- 查看状态：`systemctl status funding-monitor.service`
- 访问前端：`http://服务器IP:端口/`
- 如果提示 “ensurepip is not available” 或建议安装 `python3.x-venv`，在 Debian/Ubuntu 上执行：`sudo apt-get update -y && sudo apt-get install -y python3-venv python3.<版本>-venv`，然后重新运行一行部署命令。脚本已自动尝试安装，但极少数精简镜像可能仍需手动确认。

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
