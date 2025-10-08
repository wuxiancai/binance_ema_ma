"""Web 主入口

职责：
- 加载配置，初始化交易引擎
- 拉取历史 K 线并订阅实时 K 线
- 提供 Web 状态页与 JSON API
"""
from __future__ import annotations

import json
import threading
import time
from pathlib import Path
from typing import Any

from flask import Flask, jsonify, Response
import queue

from binance_client import BinanceClient
from binance_websocket import BinanceWebSocket
from trading import TradingEngine


def load_config() -> dict:
    cfg_path = Path("config.json")
    with cfg_path.open("r", encoding="utf-8") as f:
        return json.load(f)


def start_ws(
    engine: TradingEngine,
    symbol: str,
    interval: str,
    events_q: queue.Queue | None = None,
    *,
    client: BinanceClient,
    enable_fallback_poller: bool = True,
):
    """启动 Binance WS，并在 WS 异常/关闭时自动启用价格轮询作为回退。

    - enable_fallback_poller: True 时，WS 不稳定会自动启用轮询；WS 恢复后关闭轮询
    """

    poller_stop = {"fn": None}

    def start_poller_once():
        if poller_stop["fn"] is None and enable_fallback_poller:
            print("[Fallback] start price poller due to WS issue")
            poller_stop["fn"] = start_price_poller(engine=engine, client=client, events_q=events_q)

    def stop_poller_if_running():
        if poller_stop["fn"] is not None:
            try:
                poller_stop["fn"]()
            except Exception:
                pass
            poller_stop["fn"] = None

    def on_kline(k: dict):
        engine.on_realtime_kline(k)
        # 推送最新状态到前端（与 Binance WS 同步节奏）
        if events_q is not None:
            try:
                s = engine.status()
                s["recent_trades"] = engine.recent_trades(5)
                s["recent_klines"] = engine.recent_klines(5)
                s["server_time"] = int(time.time() * 1000)
                events_q.put_nowait(s)
            except Exception:
                pass

    def on_open():
        # WS 恢复，关闭回退轮询
        stop_poller_if_running()

    def on_error(_err):
        # WS 异常，启动回退轮询
        start_poller_once()

    def on_close():
        # WS 关闭，启动回退轮询
        start_poller_once()

    ws = BinanceWebSocket(
        symbol,
        interval,
        on_kline=on_kline,
        on_open_cb=on_open,
        on_error_cb=on_error,
        on_close_cb=on_close,
    )
    ws.start()
    return ws


def start_price_poller(engine: TradingEngine, client: BinanceClient, events_q: queue.Queue | None = None):
    """轮询最新价格作为 WebSocket 的回退方案，保证页面与策略实时性。

    每 2 秒获取一次价格，并更新引擎的当前价与未收盘K线价格。
    """
    stop_flag = threading.Event()

    def run():
        while not stop_flag.is_set():
            try:
                price = client.get_price(engine.symbol)
                # 组装一个非最终的kline，close_time沿用最近一条，避免推进序列
                close_time = engine.timestamps[-1] if engine.timestamps else int(time.time() * 1000)
                k = {
                    "event_time": int(time.time() * 1000),
                    "open_time": close_time,
                    "close_time": close_time,
                    "interval": engine.interval,
                    "is_final": False,
                    "open": price,
                    "high": price,
                    "low": price,
                    "close": price,
                    "volume": 0.0,
                }
                engine.on_realtime_kline(k)
                # 推送状态，保证 WS 不稳定时仍能更新前端
                if events_q is not None:
                    try:
                        s = engine.status()
                        s["recent_trades"] = engine.recent_trades(5)
                        s["recent_klines"] = engine.recent_klines(5)
                        s["server_time"] = int(time.time() * 1000)
                        events_q.put_nowait(s)
                    except Exception:
                        pass
            except Exception:
                pass
            time.sleep(2)

    th = threading.Thread(target=run, daemon=True)
    th.start()
    return stop_flag


def create_app(engine: TradingEngine, port: int, tz_offset: int, events_q: queue.Queue):
    app = Flask(__name__)

    @app.route("/status")
    def api_status():
        s = engine.status()
        s["recent_trades"] = engine.recent_trades(5)
        s["recent_klines"] = engine.recent_klines(5)
        s["server_time"] = int(time.time() * 1000) + tz_offset * 3600 * 1000
        return jsonify(s)

    @app.route("/")
    def index():
        # 前端：使用 SSE 订阅 /events/status，随 WS 推送实时更新
        html = """
        <!doctype html>
        <html lang=zh>
        <head>
          <meta charset=utf-8>
          <meta name=viewport content="width=device-width, initial-scale=1">
          <title>EMA/MA 自动交易系统</title>
          <style>
            body { font-family: -apple-system, BlinkMacSystemFont, Segoe UI, Roboto, Helvetica, Arial, sans-serif; margin: 24px; }
            h1 { font-size: 20px; }
            .grid { display: grid; grid-template-columns: repeat(2, minmax(300px, 1fr)); gap: 16px; }
            .card { border: 1px solid #ddd; border-radius: 8px; padding: 12px; }
            table { width: 100%; border-collapse: collapse; }
            th, td { border-bottom: 1px solid #eee; padding: 6px 8px; text-align: left; }
            .green { color: #16a34a; }
            .red { color: #dc2626; }
            code { background: #f5f5f5; padding: 2px 6px; border-radius: 4px; }
          </style>
        </head>
        <body>
          <h1>EMA/MA 自动交易系统 · __SYM__ · __INTERVAL__</h1>
          <div id="meta"></div>
          <div class="grid">
            <div class="card">
              <h2>实时状态</h2>
              <div id="status"></div>
            </div>
            <div class="card">
              <h2>当前仓位</h2>
              <div id="position"></div>
            </div>
            <div class="card">
              <h2>最近交易</h2>
              <table id="trades"><thead><tr><th>时间</th><th>方向</th><th>价格</th><th>数量</th><th>手续费</th><th>盈亏</th></tr></thead><tbody></tbody></table>
            </div>
            <div class="card">
              <h2>最新K线 (5条)</h2>
              <table id="klines"><thead><tr><th>收盘时间</th><th>开</th><th>高</th><th>低</th><th>收</th><th>量</th></tr></thead><tbody></tbody></table>
            </div>
          </div>
          <script>
          function render(s) {
            const price = s.current_price ? s.current_price.toFixed(2) : '-';
            const ema = s.ema ? s.ema.toFixed(2) : '-';
            const ma = s.ma ? s.ma.toFixed(2) : '-';
            const bal = s.balance?.toFixed(2);
            document.getElementById('meta').innerHTML = `
              <p>服务器时间: <code>${new Date(s.server_time).toLocaleString()}</code></p>
            `;
            document.getElementById('status').innerHTML = `
              <p>价格: <b>${price}</b> · EMA(5): <b>${ema}</b> · MA(15): <b>${ma}</b></p>
              <p>余额: <b>${bal}</b> / 初始: ${s.initial_balance} · 杠杆: ${s.leverage}x · 手续费率: ${(s.fee_rate*100).toFixed(3)}%</p>
            `;
            const pos = s.position || {};
            const side = pos.side || '-';
            const entry = pos.entry_price ? pos.entry_price.toFixed(2) : '-';
            const qty = pos.qty ? pos.qty.toFixed(6) : '-';
            const val = pos.value ? pos.value.toFixed(2) : '-';
            document.getElementById('position').innerHTML = `
              <p>方向: <b>${side}</b> · 开仓价: ${entry} · 数量: ${qty} · 当前价值: ${val}</p>
            `;
            const tb = document.querySelector('#trades tbody');
            tb.innerHTML = '';
            (s.recent_trades||[]).forEach(t => {
              const d = new Date(t.time).toLocaleString();
              const pnl = t.pnl === null ? '-' : Number(t.pnl).toFixed(4);
              tb.innerHTML += `<tr><td>${d}</td><td>${t.side}</td><td>${Number(t.price).toFixed(2)}</td><td>${Number(t.qty).toFixed(6)}</td><td>${Number(t.fee).toFixed(6)}</td><td>${pnl}</td></tr>`;
            });
            const kb = document.querySelector('#klines tbody');
            kb.innerHTML = '';
            // 先渲染未收盘的实时K线作为第一行（完整 O/H/L/C/Vol）
            if (s.latest_kline) {
              const k = s.latest_kline;
              const d = new Date(k.close_time).toLocaleString();
              kb.innerHTML += `<tr style="font-weight:600"><td>${d}</td><td>${Number(k.open).toFixed(2)}</td><td>${Number(k.high).toFixed(2)}</td><td>${Number(k.low).toFixed(2)}</td><td>${Number(k.close).toFixed(2)}</td><td>${Number(k.volume||0).toFixed(6)}</td></tr>`;
            }
            (s.recent_klines||[]).forEach(k => {
              const d = new Date(k.close_time).toLocaleString();
              kb.innerHTML += `<tr><td>${d}</td><td>${k.open.toFixed(2)}</td><td>${k.high.toFixed(2)}</td><td>${k.low.toFixed(2)}</td><td>${k.close.toFixed(2)}</td><td>${(k.volume||0).toFixed(6)}</td></tr>`;
            });
          }
          // 首屏初始化一次
          (async () => { const r = await fetch('/status'); const s = await r.json(); render(s); })();
          // 订阅服务端事件，实现与 Binance WS 同步节奏的实时更新
          const es = new EventSource('/events/status');
          es.onmessage = (e) => { try { const s = JSON.parse(e.data); render(s); } catch (_) {} };
          </script>
        </body>
        </html>
        """
        html = html.replace("__SYM__", engine.symbol).replace("__INTERVAL__", engine.interval)
        return Response(html, mimetype="text/html")

    @app.route('/events/status')
    def events_status():
        def stream():
            while True:
                try:
                    s = events_q.get()
                    yield f"data: {json.dumps(s)}\n\n"
                except Exception:
                    time.sleep(0.1)
        return Response(stream(), mimetype='text/event-stream')

    return app


def main():
    cfg = load_config()
    tcfg = cfg.get("trading", {})
    wcfg = cfg.get("web", {})

    engine = TradingEngine(cfg)

    # 拉取历史 K 线初始化指标
    client = BinanceClient(base_url=tcfg.get("base_url", "https://fapi.binance.com"))
    hist = client.get_klines(
        symbol=tcfg.get("symbol", "BTCUSDT"),
        interval=tcfg.get("interval", "1m"),
        limit=200,
    )
    engine.ingest_historical(hist)

    # 事件队列供前端 SSE 使用
    events_q: queue.Queue = queue.Queue(maxsize=1000)
    enable_poller = bool(wcfg.get("enable_price_poller", False))
    # 启动 WS；当未开启价格轮询时，WS 出问题会自动启用轮询作回退
    ws = start_ws(
        engine,
        engine.symbol,
        engine.interval,
        events_q=events_q,
        client=client,
        enable_fallback_poller=not enable_poller,
    )
    if enable_poller:
        start_price_poller(engine, client, events_q=events_q)

    app = create_app(engine, port=wcfg.get("port", 5001), tz_offset=wcfg.get("timezone_offset_hours", 8), events_q=events_q)
    port = int(wcfg.get("port", 5001))
    print(f"Preview URL: http://localhost:{port}/")
    # 生产建议使用 WSGI；此处使用 Flask 内建服务器即可
    app.run(host="0.0.0.0", port=port, debug=False)


if __name__ == "__main__":
    main()