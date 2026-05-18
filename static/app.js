// SMC × DRL TRADING DASHBOARD SCRIPT

// App State Cache
let activeModelId = "";
let tradePairs = [];
let chartData = [];
let selectedPairId = null;
let chartInstance = null;
let candlestickSeries = null;

// DOM Elements
const modelSelector = document.getElementById("model-selector");
const tickerDisplay = document.getElementById("ticker-display");
const metricReturn = document.getElementById("metric-return");
const metricSharpe = document.getElementById("metric-sharpe");
const metricWinrate = document.getElementById("metric-winrate");
const metricTrades = document.getElementById("metric-trades");
const positionsList = document.getElementById("positions-list");

// Parameter DOMs
const paramBuyPrice = document.getElementById("param-buy-price");
const paramSellPrice = document.getElementById("param-sell-price");
const paramSL = document.getElementById("param-sl");
const paramTP = document.getElementById("param-tp");
const paramRRBasis = document.getElementById("param-rr-basis");
const rationaleBuy = document.getElementById("rationale-buy");
const rationaleSell = document.getElementById("rationale-sell");

// Audit DOMs
const saveReviewBtn = document.getElementById("save-review-btn");
const auditNote = document.getElementById("audit-note");

// Chat DOMs
const chatViewport = document.getElementById("chat-viewport");
const chatInput = document.getElementById("chat-input");
const chatSendBtn = document.getElementById("chat-send-btn");

// Toast Notification
function showToast(message, isError = false) {
    const toast = document.getElementById("toast");
    toast.innerText = message;
    toast.className = isError ? "toast show error" : "toast show";
    setTimeout(() => {
        toast.className = "toast";
    }, 4000);
}

// 1. Initialize Price Chart using TradingView's Lightweight Charts
function initChart() {
    const chartElement = document.getElementById("chart-viewport");
    chartElement.innerHTML = ""; // Clear placeholder
    
    chartInstance = LightweightCharts.createChart(chartElement, {
        layout: {
            background: { type: 'solid', color: 'transparent' },
            textColor: '#94a3b8',
        },
        grid: {
            vertLines: { color: 'rgba(255, 255, 255, 0.02)' },
            horzLines: { color: 'rgba(255, 255, 255, 0.02)' },
        },
        crosshair: {
            mode: LightweightCharts.CrosshairMode.Normal,
        },
        rightPriceScale: {
            borderColor: 'rgba(255, 255, 255, 0.08)',
        },
        timeScale: {
            borderColor: 'rgba(255, 255, 255, 0.08)',
            timeVisible: true,
            secondsVisible: false,
        },
    });

    try {
        if (typeof chartInstance.addCandlestickSeries === 'function') {
            candlestickSeries = chartInstance.addCandlestickSeries({
                upColor: '#10b981',
                downColor: '#ef4444',
                borderDownColor: '#ef4444',
                borderUpColor: '#10b981',
                wickDownColor: '#ef4444',
                wickUpColor: '#10b981',
            });
        } else {
            candlestickSeries = chartInstance.addSeries(LightweightCharts.CandlestickSeries, {
                upColor: '#10b981',
                downColor: '#ef4444',
                borderDownColor: '#ef4444',
                borderUpColor: '#10b981',
                wickDownColor: '#ef4444',
                wickUpColor: '#10b981',
            });
        }
    } catch (err) {
        console.error("Failed to initialize candlestick series:", err);
    }

    // Resize Handler
    const resizeObserver = new ResizeObserver(entries => {
        if (entries.length === 0 || !chartInstance) return;
        const { width, height } = entries[0].contentRect;
        chartInstance.resize(width, height);
    });
    resizeObserver.observe(chartElement);
}

// 2. Load Model Registry
async function loadModels() {
    try {
        const resp = await fetch("/api/models");
        const models = await resp.json();
        
        modelSelector.innerHTML = "";
        if (models.length === 0) {
            modelSelector.innerHTML = `<option value="">No saved models found</option>`;
            return;
        }

        models.forEach((m, idx) => {
            const opt = document.createElement("option");
            opt.value = m.model_id;
            opt.innerText = `${m.model_id.substring(0, 16)}... | Sharpe ${m.sharpe.toFixed(2)} | Return ${(m.total_return * 100).toFixed(1)}%`;
            if (idx === 0) opt.selected = true;
            modelSelector.appendChild(opt);
        });

        // Trigger loading the first (best) model
        if (models.length > 0) {
            activeModelId = models[0].model_id;
            await loadDashboardData();
        }
    } catch (e) {
        console.error("Error listing model registry:", e);
        showToast("Error loading model list", true);
    }
}

// 3. Load Active Model Dashboard Data
async function loadDashboardData() {
    try {
        // A. Load Metrics
        const metricsResp = await fetch("/api/metrics");
        const metricsData = await metricsResp.json();
        if (metricsData.metrics && Object.keys(metricsData.metrics).length > 0) {
            const m = metricsData.metrics;
            metricReturn.innerText = `${(m.total_return * 100).toFixed(2)}%`;
            metricSharpe.innerText = m.sharpe.toFixed(3);
            metricWinrate.innerText = `${(m.win_rate * 100).toFixed(1)}%`;
            metricTrades.innerText = m.total_trades;
        }

        // B. Load Chart Candlesticks
        const chartResp = await fetch("/api/chart_data");
        const chartJson = await chartResp.json();
        chartData = chartJson.ohlcv || [];
        if (candlestickSeries && chartData.length > 0) {
            candlestickSeries.setData(chartData);
            chartInstance.timeScale().fitContent();
        }

        // C. Load Trade Positions
        const pairsResp = await fetch("/api/trade_pairs");
        const pairsJson = await pairsResp.json();
        tradePairs = pairsJson.pairs || [];
        
        renderPositionsList();
        renderAllChartMarkers();
    } catch (e) {
        console.error("Error loading dashboard metrics/data:", e);
        showToast("Error reloading model metrics", true);
    }
}

// 4. Render Sidebar Position Cards
function renderPositionsList() {
    positionsList.innerHTML = "";
    if (tradePairs.length === 0) {
        positionsList.innerHTML = `<div class="list-placeholder">No completed trade positions for this agent run.</div>`;
        return;
    }

    tradePairs.forEach(p => {
        const isProfit = p.profit_pct >= 0;
        const pctText = `${(p.profit_pct * 100).toFixed(2)}%`;
        const pnlText = `${isProfit ? '+' : ''}${p.pnl.toLocaleString('en-US', {maximumFractionDigits: 2})} TWD`;
        
        const buyDate = new Date(p.buy_time).toLocaleDateString();
        const sellDate = new Date(p.sell_time).toLocaleDateString();

        const card = document.createElement("div");
        card.className = "position-card";
        card.id = `pos-card-${p.pair_id}`;
        card.onclick = () => selectTradePosition(p.pair_id);

        card.innerHTML = `
            <div class="pos-left">
                <span class="pos-id">POSITION #${p.pair_id}</span>
                <span class="pos-ticker">${p.ticker}</span>
                <span class="pos-dates">${buyDate} → ${sellDate}</span>
            </div>
            <div class="pos-right">
                <span class="pos-pnl ${isProfit ? 'profit' : 'loss'}">${pnlText}</span>
                <span class="pos-badge ${isProfit ? 'profit' : 'loss'}">${pctText}</span>
            </div>
        `;
        positionsList.appendChild(card);
    });
}

// 5. Place Buy/Sell Entry Markers for All Completed Positions on the Chart
function renderAllChartMarkers() {
    if (!candlestickSeries || tradePairs.length === 0) return;

    const markers = [];
    tradePairs.forEach(p => {
        // Convert buy/sell timestamps to seconds epoch
        const buySec = Math.floor(new Date(p.buy_time).getTime() / 1000);
        const sellSec = Math.floor(new Date(p.sell_time).getTime() / 1000);

        markers.push({
            time: buySec,
            position: 'belowBar',
            color: '#10b981',
            shape: 'arrowUp',
            text: `BUY #${p.pair_id}`
        });

        markers.push({
            time: sellSec,
            position: 'aboveBar',
            color: '#ef4444',
            shape: 'arrowDown',
            text: `SELL #${p.pair_id}`
        });
    });

    // Sort markers chronologically by epoch seconds
    markers.sort((a, b) => a.time - b.time);
    candlestickSeries.setMarkers(markers);
}

// 6. Select a Trading Pair position
function selectTradePosition(pairId) {
    selectedPairId = pairId;
    
    // Toggle active CSS class
    document.querySelectorAll(".position-card").forEach(el => el.classList.remove("active"));
    const activeCard = document.getElementById(`pos-card-${pairId}`);
    if (activeCard) activeCard.classList.add("active");

    const pair = tradePairs.find(p => p.pair_id === pairId);
    if (!pair) return;

    // A. Populate Parameters Card
    paramBuyPrice.innerText = `${pair.buy_price.toLocaleString()} TWD`;
    paramSellPrice.innerText = `${pair.sell_price.toLocaleString()} TWD`;
    paramSL.innerText = pair.rr_stop_loss_price ? `${pair.rr_stop_loss_price.toLocaleString()} TWD` : "N/A";
    paramTP.innerText = pair.rr_take_profit_price ? `${pair.rr_take_profit_price.toLocaleString()} TWD` : "N/A";
    paramRRBasis.innerText = pair.rr_basis || "N/A";
    rationaleBuy.innerText = pair.buy_reason || "No buy logic recorded.";
    rationaleSell.innerText = pair.sell_reason || "No sell logic recorded.";

    // B. Focus/Scroll the Chart Viewport onto this Position
    focusChartOnPosition(pair.buy_time, pair.sell_time);

    // C. Enable & Load AI Coach chat
    chatInput.disabled = false;
    chatSendBtn.disabled = false;
    chatInput.placeholder = "Ask AI: e.g. Why did the agent buy at this liquidity sweep?...";
    
    loadJournalChatThread(pairId);
}

// 7. Auto Scroll and Focus Chart Viewport to center around active position
function focusChartOnPosition(buyTimeStr, sellTimeStr) {
    if (!chartInstance) return;
    
    const buySec = Math.floor(new Date(buyTimeStr).getTime() / 1000);
    const sellSec = Math.floor(new Date(sellTimeStr).getTime() / 1000);

    // Calculate paddings (approx 20 units of candles before & after)
    const padding = 3600 * 24; // 1 day
    
    chartInstance.timeScale().setVisibleRange({
        from: buySec - padding * 3,
        to: sellSec + padding * 5
    });
}

// 8. Load Interactive Chat Logs
async function loadJournalChatThread(pairId) {
    chatViewport.innerHTML = `<div class="list-placeholder"><i class="fa-solid fa-spinner fa-spin"></i> Loading AI discussion...</div>`;
    try {
        const resp = await fetch(`/api/journal/${pairId}`);
        const thread = await resp.json();
        
        chatViewport.innerHTML = "";
        if (thread.length === 0) {
            chatViewport.innerHTML = `
                <div class="chat-welcome">
                    <i class="fa-solid fa-comments"></i>
                    <p>Begin auditing! Ask your AI Quant Coach about the parameters of Position #${pairId}.</p>
                </div>
            `;
            return;
        }

        thread.forEach(msg => {
            appendChatBubble(msg.author, msg.content, msg.timestamp);
        });
        chatViewport.scrollTop = chatViewport.scrollHeight;
    } catch (e) {
        console.error("Error loading chat logs:", e);
        chatViewport.innerHTML = `<div class="list-placeholder error">Failed to load discussion logs.</div>`;
    }
}

// 9. Append a Chat Bubble to Viewport
function appendChatBubble(author, content, timestamp) {
    const isUser = author === "User";
    const bubble = document.createElement("div");
    bubble.className = `chat-msg ${isUser ? 'user' : 'coach'}`;
    
    bubble.innerHTML = `
        <div class="msg-header">
            <span class="msg-author ${isUser ? 'user' : 'coach'}">${isUser ? '🧑‍💻 User' : '🤖 AI Quant Coach'}</span>
            <span class="msg-time">${timestamp}</span>
        </div>
        <div class="msg-content">${content.replace(/\n/g, "<br>")}</div>
    `;
    chatViewport.appendChild(bubble);
}

// 10. Send a Chat Message to Gemini AI Coach
async function sendChatMessage() {
    const text = chatInput.value.trim();
    if (!text || !selectedPairId) return;

    // Show User's bubble instantly
    const nowStr = new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
    appendChatBubble("User", text, nowStr);
    chatViewport.scrollTop = chatViewport.scrollHeight;
    
    chatInput.value = "";
    chatInput.disabled = true;
    chatSendBtn.disabled = true;
    
    // Add a glowing loading bubble for the coach
    const loadingBubble = document.createElement("div");
    loadingBubble.className = "chat-msg coach";
    loadingBubble.id = "chat-loading-bubble";
    loadingBubble.innerHTML = `<i class="fa-solid fa-circle-nodes fa-spin"></i> Coach is evaluating parameters...`;
    chatViewport.appendChild(loadingBubble);
    chatViewport.scrollTop = chatViewport.scrollHeight;

    try {
        const resp = await fetch(`/api/journal/${selectedPairId}`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ user_comment: text })
        });
        
        // Remove loading bubble
        const loader = document.getElementById("chat-loading-bubble");
        if (loader) loader.remove();

        const thread = await resp.json();
        // Clear and render all messages to keep clean
        chatViewport.innerHTML = "";
        thread.forEach(msg => {
            appendChatBubble(msg.author, msg.content, msg.timestamp);
        });
        chatViewport.scrollTop = chatViewport.scrollHeight;
    } catch (e) {
        console.error("Error submitting AI journal question:", e);
        const loader = document.getElementById("chat-loading-bubble");
        if (loader) loader.remove();
        showToast("Error getting AI Coach reply", true);
    } finally {
        chatInput.disabled = false;
        chatSendBtn.disabled = false;
        chatInput.focus();
    }
}

// 11. Save Manual Audit Review to CSV
async function saveAuditReview() {
    if (!selectedPairId) {
        showToast("Please select a position card to audit first!", true);
        return;
    }

    const stateVal = document.querySelector('input[name="audit-state"]:checked').value;
    const noteVal = auditNote.value.trim();

    saveReviewBtn.disabled = true;
    saveReviewBtn.innerHTML = `<i class="fa-solid fa-spinner fa-spin"></i> Saving...`;

    try {
        const resp = await fetch(`/api/save_review/${selectedPairId}`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
                pair_id: selectedPairId,
                review_state: stateVal,
                review_note: noteVal
            })
        });

        if (resp.ok) {
            showToast(`Position #${selectedPairId} review saved!`);
            auditNote.value = "";
        } else {
            showToast("Failed to save audit details", true);
        }
    } catch (e) {
        console.error("Failed saving manual review:", e);
        showToast("Failed sending review to database", true);
    } finally {
        saveReviewBtn.disabled = false;
        saveReviewBtn.innerHTML = `<i class="fa-solid fa-floppy-disk"></i> Save Review`;
    }
}

// Event Listeners
modelSelector.addEventListener("change", async (e) => {
    const selectedModel = e.target.value;
    if (!selectedModel) return;

    activeModelId = selectedModel;
    showToast(`Evaluating model: ${selectedModel.substring(0, 12)}...`);
    
    try {
        const resp = await fetch("/api/select_model", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ model_id: selectedModel })
        });
        if (resp.ok) {
            await loadDashboardData();
            showToast("Model switched successfully!");
        } else {
            showToast("Error switching model", true);
        }
    } catch (err) {
        console.error("Error switching model context:", err);
        showToast("Network error switching model", true);
    }
});

chatSendBtn.addEventListener("click", sendChatMessage);
chatInput.addEventListener("keydown", (e) => {
    if (e.key === "Enter" && !e.shiftKey) {
        e.preventDefault();
        sendChatMessage();
    }
});

saveReviewBtn.addEventListener("click", saveAuditReview);

// Theme Toggle Logic
const themeToggleBtn = document.getElementById("theme-toggle");
let currentTheme = "dark";

themeToggleBtn.addEventListener("click", () => {
    currentTheme = currentTheme === "dark" ? "light" : "dark";
    document.body.setAttribute("data-theme", currentTheme);
    
    // Update button icon
    themeToggleBtn.innerHTML = currentTheme === "dark" 
        ? '<i class="fa-solid fa-moon"></i>' 
        : '<i class="fa-solid fa-sun"></i>';
        
    // Update chart colors dynamically
    if (chartInstance) {
        chartInstance.applyOptions({
            layout: {
                textColor: currentTheme === "dark" ? '#94a3b8' : '#475569',
            },
            grid: {
                vertLines: { color: currentTheme === "dark" ? 'rgba(255, 255, 255, 0.02)' : 'rgba(0, 0, 0, 0.05)' },
                horzLines: { color: currentTheme === "dark" ? 'rgba(255, 255, 255, 0.02)' : 'rgba(0, 0, 0, 0.05)' },
            },
            rightPriceScale: {
                borderColor: currentTheme === "dark" ? 'rgba(255, 255, 255, 0.08)' : 'rgba(0, 0, 0, 0.1)',
            },
            timeScale: {
                borderColor: currentTheme === "dark" ? 'rgba(255, 255, 255, 0.08)' : 'rgba(0, 0, 0, 0.1)',
            }
        });
    }
});

// Pipeline Modal Logic
const pipelineBtn = document.getElementById("open-pipeline-btn");
const pipelineModal = document.getElementById("pipeline-modal");
const closePipelineBtn = document.getElementById("close-pipeline-btn");
const runPipelineBtn = document.getElementById("run-pipeline-btn");

if (pipelineBtn) {
    pipelineBtn.addEventListener("click", () => {
        pipelineModal.classList.add("show");
    });
}
if (closePipelineBtn) {
    closePipelineBtn.addEventListener("click", () => {
        pipelineModal.classList.remove("show");
    });
}
if (runPipelineBtn) {
    runPipelineBtn.addEventListener("click", async () => {
        const ticker = document.getElementById("pipe-ticker").value;
        const start = document.getElementById("pipe-start").value;
        const end = document.getElementById("pipe-end").value;
        const strategy = document.getElementById("pipe-strategy").value;
        const episodes = parseInt(document.getElementById("pipe-episodes").value);
        const patience = parseInt(document.getElementById("pipe-patience").value);

        if (!ticker || !start || !end) {
            showToast("Please fill out all pipeline parameters.", true);
            return;
        }

        pipelineModal.classList.remove("show");
        showToast("Training pipeline started. This may take several minutes...");

        try {
            const resp = await fetch("/api/run_pipeline", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({
                    ticker: ticker,
                    start_date: start,
                    end_date: end,
                    strategy_mode: strategy,
                    episodes: episodes,
                    early_stop_patience: patience
                })
            });

            const data = await resp.json();
            if (resp.ok) {
                showToast(`Pipeline complete! Model ${data.model_id.substring(0, 8)} registered.`);
                await loadModels();
                document.getElementById("model-selector").value = data.model_id;
                activeModelId = data.model_id;
                await loadDashboardData();
            } else {
                showToast(data.detail || "Error during pipeline execution", true);
            }
        } catch (err) {
            console.error("Pipeline request error", err);
            showToast("Network error starting pipeline.", true);
        }
    });
}

// Fullscreen Chart Logic
const fullscreenChartBtn = document.getElementById("fullscreen-chart-btn");
const chartContainerElement = document.querySelector(".chart-container");
let isChartFullscreen = false;

if (fullscreenChartBtn && chartContainerElement) {
    fullscreenChartBtn.addEventListener("click", () => {
        isChartFullscreen = !isChartFullscreen;
        if (isChartFullscreen) {
            chartContainerElement.classList.add("fullscreen-mode");
            fullscreenChartBtn.innerHTML = '<i class="fa-solid fa-compress"></i>';
        } else {
            chartContainerElement.classList.remove("fullscreen-mode");
            fullscreenChartBtn.innerHTML = '<i class="fa-solid fa-expand"></i>';
        }
        
        // Ensure chart scale fits the new dimensions after the CSS transition
        if (chartInstance) {
            setTimeout(() => {
                chartInstance.timeScale().fitContent();
            }, 350);
        }
    });
}

// Bootloader
window.addEventListener("load", () => {
    initChart();
    loadModels();
});
