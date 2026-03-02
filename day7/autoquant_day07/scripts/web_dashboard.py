#!/usr/bin/env python3
"""
Web Dashboard: Flask-based web interface for viewing trade journal.
Access at: http://localhost:5000
"""
import json
import sys
from pathlib import Path
from datetime import datetime

sys.path.insert(0, str(Path(__file__).parent.parent))

try:
    from flask import Flask, render_template_string, jsonify
except ImportError:
    print("Flask not installed. Installing...")
    import subprocess
    subprocess.check_call([sys.executable, "-m", "pip", "install", "flask"])
    from flask import Flask, render_template_string, jsonify

app = Flask(__name__)
JOURNAL = Path("logs/trade_journal.jsonl")


def read_journal() -> list[dict]:
    """Read all records from trade journal."""
    if not JOURNAL.exists():
        return []
    records = []
    for line in JOURNAL.read_text().splitlines():
        if line.strip():
            try:
                records.append(json.loads(line))
            except json.JSONDecodeError:
                pass
    return records


def get_stats(records: list[dict]) -> dict:
    """Calculate statistics from journal records."""
    fills = [r for r in records if r.get("msg") == "ORDER_FILL"]
    if not fills:
        return {
            "total_records": len(records),
            "total_fills": 0,
            "avg_slippage": 0,
            "avg_latency": 0,
        }
    
    slippages = [r.get("slippage_bps", 0) for r in fills if r.get("slippage_bps") is not None]
    latencies = [r.get("latency_ms", 0) for r in fills if r.get("latency_ms") is not None]
    
    return {
        "total_records": len(records),
        "total_fills": len(fills),
        "avg_slippage": sum(slippages) / len(slippages) if slippages else 0,
        "avg_latency": sum(latencies) / len(latencies) if latencies else 0,
        "min_slippage": min(slippages) if slippages else 0,
        "max_slippage": max(slippages) if slippages else 0,
    }


HTML_TEMPLATE = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>AutoQuant-Alpha | Day 7 Dashboard</title>
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body {
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Oxygen, Ubuntu, sans-serif;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: #333;
            padding: 20px;
            min-height: 100vh;
        }
        .container {
            max-width: 1400px;
            margin: 0 auto;
        }
        .header {
            background: white;
            padding: 30px;
            border-radius: 10px;
            box-shadow: 0 10px 30px rgba(0,0,0,0.2);
            margin-bottom: 20px;
        }
        .header h1 {
            color: #667eea;
            margin-bottom: 10px;
        }
        .stats {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
            gap: 15px;
            margin-bottom: 20px;
        }
        .stat-card {
            background: white;
            padding: 20px;
            border-radius: 8px;
            box-shadow: 0 5px 15px rgba(0,0,0,0.1);
        }
        .stat-card h3 {
            color: #666;
            font-size: 14px;
            margin-bottom: 10px;
            text-transform: uppercase;
        }
        .stat-card .value {
            font-size: 32px;
            font-weight: bold;
            color: #667eea;
        }
        .table-container {
            background: white;
            padding: 20px;
            border-radius: 10px;
            box-shadow: 0 10px 30px rgba(0,0,0,0.2);
            overflow-x: auto;
        }
        table {
            width: 100%;
            border-collapse: collapse;
        }
        th {
            background: #667eea;
            color: white;
            padding: 12px;
            text-align: left;
            font-weight: 600;
        }
        td {
            padding: 10px 12px;
            border-bottom: 1px solid #eee;
        }
        tr:hover {
            background: #f8f9ff;
        }
        .badge {
            display: inline-block;
            padding: 4px 8px;
            border-radius: 4px;
            font-size: 12px;
            font-weight: 600;
        }
        .badge-info { background: #e3f2fd; color: #1976d2; }
        .badge-success { background: #e8f5e9; color: #388e3c; }
        .badge-error { background: #ffebee; color: #c62828; }
        .badge-warning { background: #fff3e0; color: #f57c00; }
        .slippage-positive { color: #c62828; font-weight: 600; }
        .slippage-negative { color: #388e3c; font-weight: 600; }
        .refresh-btn {
            background: #667eea;
            color: white;
            border: none;
            padding: 10px 20px;
            border-radius: 5px;
            cursor: pointer;
            font-size: 14px;
            margin-top: 10px;
        }
        .refresh-btn:hover {
            background: #5568d3;
        }
        .auto-refresh {
            margin-top: 10px;
            color: #666;
            font-size: 14px;
        }
    </style>
    <script>
        function refreshData() {
            fetch('/api/data')
                .then(response => response.json())
                .then(data => {
                    updateStats(data.stats);
                    updateTable(data.records);
                });
        }
        
        function updateStats(stats) {
            document.getElementById('total-records').textContent = stats.total_records;
            document.getElementById('total-fills').textContent = stats.total_fills;
            document.getElementById('avg-slippage').textContent = stats.avg_slippage.toFixed(4) + ' bps';
            document.getElementById('avg-latency').textContent = stats.avg_latency.toFixed(2) + ' ms';
        }
        
        function updateTable(records) {
            const tbody = document.getElementById('journal-body');
            tbody.innerHTML = '';
            
            records.slice(-20).reverse().forEach(r => {
                const row = document.createElement('tr');
                const ts = new Date(r.ts).toLocaleString();
                const level = r.level || '—';
                const msg = r.msg || '—';
                const symbol = r.symbol || '—';
                const side = r.side || '—';
                const slippage = r.slippage_bps !== undefined ? r.slippage_bps.toFixed(4) : '—';
                const latency = r.latency_ms !== undefined ? r.latency_ms.toFixed(2) : '—';
                
                const levelClass = level === 'ERROR' ? 'badge-error' : 
                                  level === 'WARNING' ? 'badge-warning' : 
                                  level === 'INFO' ? 'badge-info' : 'badge-success';
                
                const slippageClass = r.slippage_bps !== undefined && Math.abs(r.slippage_bps) > 5 ? 
                                     'slippage-positive' : 'slippage-negative';
                
                row.innerHTML = `
                    <td>${ts}</td>
                    <td><span class="badge ${levelClass}">${level}</span></td>
                    <td>${msg}</td>
                    <td>${symbol}</td>
                    <td>${side}</td>
                    <td class="${slippageClass}">${slippage}</td>
                    <td>${latency}</td>
                `;
                tbody.appendChild(row);
            });
        }
        
        // Auto-refresh every 2 seconds
        setInterval(refreshData, 2000);
        // Initial load
        window.onload = refreshData;
    </script>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>🚀 AutoQuant-Alpha | Day 7 Dashboard</h1>
            <p>Real-time Trade Journal Monitor</p>
            <button class="refresh-btn" onclick="refreshData()">🔄 Refresh</button>
            <div class="auto-refresh">Auto-refreshing every 2 seconds...</div>
        </div>
        
        <div class="stats">
            <div class="stat-card">
                <h3>Total Records</h3>
                <div class="value" id="total-records">0</div>
            </div>
            <div class="stat-card">
                <h3>Total Fills</h3>
                <div class="value" id="total-fills">0</div>
            </div>
            <div class="stat-card">
                <h3>Avg Slippage</h3>
                <div class="value" id="avg-slippage">0 bps</div>
            </div>
            <div class="stat-card">
                <h3>Avg Latency</h3>
                <div class="value" id="avg-latency">0 ms</div>
            </div>
        </div>
        
        <div class="table-container">
            <h2 style="margin-bottom: 15px;">Trade Journal (Last 20 Records)</h2>
            <table>
                <thead>
                    <tr>
                        <th>Timestamp</th>
                        <th>Level</th>
                        <th>Message</th>
                        <th>Symbol</th>
                        <th>Side</th>
                        <th>Slippage (bps)</th>
                        <th>Latency (ms)</th>
                    </tr>
                </thead>
                <tbody id="journal-body">
                    <tr><td colspan="7" style="text-align: center; padding: 20px;">Loading...</td></tr>
                </tbody>
            </table>
        </div>
    </div>
</body>
</html>
"""


@app.route('/')
def index():
    """Main dashboard page."""
    return render_template_string(HTML_TEMPLATE)


@app.route('/favicon.ico')
def favicon():
    """Handle favicon requests to prevent 404 errors."""
    from flask import Response
    # Return empty 204 No Content response
    return Response(status=204)


@app.route('/api/data')
def api_data():
    """API endpoint for journal data."""
    records = read_journal()
    stats = get_stats(records)
    return jsonify({
        "records": records,
        "stats": stats
    })


def main():
    """Start the web server."""
    import socket
    
    # Get local IP address
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        local_ip = s.getsockname()[0]
        s.close()
    except Exception:
        local_ip = "127.0.0.1"
    
    print("\n" + "="*70)
    print("🚀 AutoQuant-Alpha Web Dashboard")
    print("="*70)
    print(f"\n📊 Dashboard URLs:")
    print(f"   • http://localhost:5000")
    print(f"   • http://127.0.0.1:5000")
    if local_ip != "127.0.0.1":
        print(f"   • http://{local_ip}:5000")
    print(f"\n📈 API Endpoint: http://localhost:5000/api/data")
    print(f"\n📝 Journal file: {JOURNAL.resolve()}")
    print(f"\n⚡ Server starting on 0.0.0.0:5000...")
    print(f"   Press Ctrl+C to stop\n")
    print("="*70 + "\n")
    
    app.run(host='0.0.0.0', port=5000, debug=False)


if __name__ == "__main__":
    main()

