import os

path = 'static/app.js'
with open(path, 'r', encoding='utf-8') as f:
    js = f.read()

polling_logic = """
// Live Training Status Poller
let liveChartInstance = null;
let liveLossSeries = null;

async function pollTrainingStatus() {
    try {
        const res = await fetch("/api/training_status");
        if(!res.ok) return;
        const data = await res.json();
        
        const widget = document.getElementById("training-monitor-widget");
        if(!widget) return;
        
        if (data.is_training || (data.logs && data.logs.length > 0)) {
            widget.style.display = "block";
            document.getElementById("training-ticker-badge").textContent = data.ticker || "RUNNING";
            
            if (!liveChartInstance) {
                liveChartInstance = LightweightCharts.createChart(document.getElementById("training-chart-container"), {
                    layout: { backgroundColor: "transparent", textColor: "#9ca3af" },
                    grid: { vertLines: { color: "rgba(255,255,255,0.05)" }, horzLines: { color: "rgba(255,255,255,0.05)" } },
                    rightPriceScale: { borderVisible: false },
                    timeScale: { borderVisible: false, timeVisible: true }
                });
                liveLossSeries = liveChartInstance.addLineSeries({ color: "#ef4444", lineWidth: 2 });
            }
            
            if (data.logs && data.logs.length > 0) {
                const latestLog = data.logs[data.logs.length - 1];
                document.getElementById("training-status-text").innerHTML = `<b>Epoch ${latestLog.episode}</b> | Loss: ${latestLog.avg_loss.toFixed(5)} | Train Ret: ${(latestLog.train_return*100).toFixed(2)}% | Val Ret: ${(latestLog.val_return*100).toFixed(2)}%`;
                
                const baseTime = 1700000000;
                const chartData = data.logs.map(log => ({
                    time: baseTime + log.episode * 3600, // 1 hour step per epoch fake time
                    value: log.avg_loss || 0
                }));
                liveLossSeries.setData(chartData);
                liveChartInstance.timeScale().fitContent();
            } else {
                document.getElementById("training-status-text").textContent = "Downloading Market Data (Yahoo Finance)...";
            }
            
            if (!data.is_training && data.logs.length > 0) {
                if (!document.getElementById("dismiss-monitor")) {
                    const dismissBtn = document.createElement("button");
                    dismissBtn.id = "dismiss-monitor";
                    dismissBtn.innerHTML = "<i class='fa-solid fa-xmark'></i> Close";
                    dismissBtn.style.cssText = "background: rgba(255,255,255,0.1); border: none; color: white; padding: 4px 8px; border-radius: 4px; cursor: pointer; font-size: 11px; margin-left: 8px;";
                    dismissBtn.onclick = () => { widget.style.display = "none"; };
                    document.getElementById("training-ticker-badge").parentElement.appendChild(dismissBtn);
                }
                document.getElementById("training-status-text").innerHTML = `<span style="color: var(--neon-purple);"><i class="fa-solid fa-check"></i> Training Complete!</span>`;
            }
        }
    } catch(err) {
        console.error("Polling error", err);
    }
}

setInterval(pollTrainingStatus, 2000);
"""

if "pollTrainingStatus" not in js:
    js += "\n" + polling_logic
    with open(path, 'w', encoding='utf-8') as f:
        f.write(js)
    print("JS polling logic securely appended!")
else:
    print("Polling logic already exists!")
