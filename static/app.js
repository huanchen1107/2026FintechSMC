// SMC × DRL TRADING DASHBOARD SCRIPT

// App State Cache
let activeModelId = "";
let tradePairs = [];
let chartData = [];
let selectedPairId = null;
let chartInstance = null;
let candlestickSeries = null;
let currentChartInterval = "1h";
let rrPoints = [];
let rrOverlay = null;

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
const journalPairSelector = document.getElementById("journal-pair-selector");

// Toast Notification
function showToast(message, isError = false) {
    const toast = document.getElementById("toast");
    toast.innerText = message;
    toast.className = isError ? "toast show error" : "toast show";
    setTimeout(() => {
        toast.className = "toast";
    }, 4000);
}

function resetSelectedTradeContext() {
    selectedPairId = null;
    document.querySelectorAll(".position-card").forEach(el => el.classList.remove("active"));
    paramBuyPrice.innerText = "-- TWD";
    paramSellPrice.innerText = "-- TWD";
    paramSL.innerText = "-- TWD";
    paramTP.innerText = "-- TWD";
    paramRRBasis.innerText = "--";
    rationaleBuy.innerText = "No position selected.";
    rationaleSell.innerText = "No position selected.";
    if (auditNote) auditNote.value = "";
    if (journalPairSelector) {
        journalPairSelector.innerHTML = `<option value="">Select a model position...</option>`;
        journalPairSelector.disabled = true;
    }
    chatInput.disabled = true;
    chatSendBtn.disabled = true;
    chatInput.value = "";
    chatInput.placeholder = "Select a trade position first...";
    chatViewport.innerHTML = `
        <div class="chat-welcome">
            <i class="fa-solid fa-comments"></i>
            <p>Select a position from this saved model to load its pair-specific discussion.</p>
        </div>
    `;
}

// 1. Initialize Price Chart using TradingView's Lightweight Charts
function initChart() {
    const chartElement = document.getElementById("chart-viewport");
    chartElement.innerHTML = ""; // Clear placeholder
    chartElement.style.position = "relative";
    
    chartInstance = LightweightCharts.createChart(chartElement, {
        layout: {
            background: { type: 'solid', color: 'transparent' },
            textColor: '#475569',
        },
        grid: {
            vertLines: { color: 'rgba(0, 0, 0, 0.05)' },
            horzLines: { color: 'rgba(0, 0, 0, 0.05)' },
        },
        crosshair: {
            mode: LightweightCharts.CrosshairMode.Normal,
        },
        rightPriceScale: {
            borderColor: 'rgba(0, 0, 0, 0.1)',
        },
        timeScale: {
            borderColor: 'rgba(0, 0, 0, 0.1)',
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
        renderRRThresholdLines();
    });
    resizeObserver.observe(chartElement);

    if (chartInstance.timeScale && typeof chartInstance.timeScale().subscribeVisibleTimeRangeChange === "function") {
        chartInstance.timeScale().subscribeVisibleTimeRangeChange(() => renderRRThresholdLines());
    }
}

function getRRThreshold() {
    const input = document.getElementById("pipe-rr-threshold");
    const value = input ? parseFloat(input.value) : 2.0;
    return Number.isFinite(value) ? value : 2.0;
}

function calculatePairRR(pair) {
    const entry = Number(pair.buy_price);
    const stop = Number(pair.rr_stop_loss_price);
    const target = Number(pair.rr_take_profit_price);
    const risk = entry - stop;
    const reward = target - entry;
    if (!Number.isFinite(entry) || !Number.isFinite(stop) || !Number.isFinite(target) || risk <= 0 || reward <= 0) {
        return null;
    }
    return reward / risk;
}

function ensureRROverlay() {
    const chartElement = document.getElementById("chart-viewport");
    if (!chartElement) return null;
    if (!rrOverlay) {
        rrOverlay = document.createElement("div");
        rrOverlay.id = "rr-threshold-overlay";
        rrOverlay.style.cssText = "position:absolute; inset:0; pointer-events:none; z-index:5; overflow:hidden;";
        chartElement.appendChild(rrOverlay);
    }
    return rrOverlay;
}

function clearRRGuideLines() {
    if (rrOverlay) rrOverlay.innerHTML = "";
}

function renderRRThresholdLines() {
    const overlay = ensureRROverlay();
    if (!overlay || !chartInstance || !chartInstance.timeScale) return;
    overlay.innerHTML = "";

    const threshold = getRRThreshold();
    const timeScale = chartInstance.timeScale();
    const visibleRange = typeof timeScale.getVisibleRange === "function" ? timeScale.getVisibleRange() : null;
    const chartHeight = overlay.clientHeight || document.getElementById("chart-viewport").clientHeight;

    rrPoints
        .filter(point => Number(point.rr_valid) === 1 && Number(point.rr_ratio) >= threshold)
        .forEach(point => {
            if (visibleRange && (point.time < visibleRange.from || point.time > visibleRange.to)) return;
            const x = timeScale.timeToCoordinate(point.time);
            if (x === null || x === undefined || !Number.isFinite(x)) return;

            const line = document.createElement("div");
            line.title = `RR ${Number(point.rr_ratio).toFixed(2)} >= ${threshold.toFixed(1)}`;
            line.style.cssText = [
                "position:absolute",
                `left:${Math.round(x)}px`,
                "top:0",
                `height:${chartHeight}px`,
                "border-left:1px dotted rgba(0, 200, 83, 0.7)",
                "box-shadow:0 0 8px rgba(0, 200, 83, 0.25)",
            ].join(";");
            overlay.appendChild(line);
        });
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
        resetSelectedTradeContext();

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
        const chartResp = await fetch(`/api/chart_data?interval=${currentChartInterval}`);
        const chartJson = await chartResp.json();
        chartData = chartJson.ohlcv || [];
        rrPoints = chartJson.rr_points || [];
        if (candlestickSeries && chartData.length > 0) {
            candlestickSeries.setData(chartData);
            chartInstance.timeScale().fitContent();
            renderRRThresholdLines();
        }

        // C. Load Trade Positions
        const pairsResp = await fetch("/api/trade_pairs");
        const pairsJson = await pairsResp.json();
        tradePairs = pairsJson.pairs || [];
        activeModelId = pairsJson.model_id || activeModelId;
        
        renderPositionsList();
        renderAllChartMarkers();
        
        // Auto-select the first completed position card on load/evaluate to prevent empty placeholder states
        if (tradePairs.length > 0) {
            selectTradePosition(tradePairs[0].pair_id);
        }
    } catch (e) {
        console.error("Error loading dashboard metrics/data:", e);
        showToast("Error reloading model metrics", true);
    }
}

// 4. Render Sidebar Position Cards
function renderPositionsList() {
    positionsList.innerHTML = "";
    if (journalPairSelector) {
        journalPairSelector.innerHTML = `<option value="">Select a model position...</option>`;
        journalPairSelector.disabled = tradePairs.length === 0;
    }
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
        const pairLabel = `Position #${p.pair_id} | ${p.ticker} | ${buyDate} -> ${sellDate} | ${pctText}`;

        if (journalPairSelector) {
            const opt = document.createElement("option");
            opt.value = p.pair_id;
            opt.textContent = pairLabel;
            journalPairSelector.appendChild(opt);
        }

        const card = document.createElement("div");
        card.className = "position-card";
        card.id = `pos-card-${p.pair_id}`;
        card.onclick = () => selectTradePosition(p.pair_id);

        card.innerHTML = `
            <div class="pos-left">
                <span class="pos-id">POSITION #${p.pair_id}</span>
                <span class="pos-ticker">${p.ticker}</span>
                <span class="pos-dates">${buyDate} -> ${sellDate}</span>
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
    if (!candlestickSeries) return;
    if (tradePairs.length === 0) {
        if (typeof candlestickSeries.setMarkers === 'function') {
            candlestickSeries.setMarkers([]);
        } else if (typeof LightweightCharts.createSeriesMarkers === 'function') {
            LightweightCharts.createSeriesMarkers(candlestickSeries, []);
        }
        return;
    }

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
    if (typeof candlestickSeries.setMarkers === 'function') {
        candlestickSeries.setMarkers(markers);
    } else if (typeof LightweightCharts.createSeriesMarkers === 'function') {
        LightweightCharts.createSeriesMarkers(candlestickSeries, markers);
    } else {
        console.warn("setMarkers is not functional under this library version");
    }
}

// 6. Select a Trading Pair position
function selectTradePosition(pairId) {
    selectedPairId = pairId;
    
    // Toggle active CSS class
    document.querySelectorAll(".position-card").forEach(el => el.classList.remove("active"));
    const activeCard = document.getElementById(`pos-card-${pairId}`);
    if (activeCard) {
        activeCard.classList.add("active");
        activeCard.scrollIntoView({ block: "nearest", behavior: "smooth" });
    }
    if (journalPairSelector && String(journalPairSelector.value) !== String(pairId)) {
        journalPairSelector.value = String(pairId);
    }

    const pair = tradePairs.find(p => p.pair_id === pairId);
    if (!pair) return;
    const modelLabel = activeModelId ? activeModelId : "active model";

    // A. Populate Parameters Card
    paramBuyPrice.innerText = `${pair.buy_price.toLocaleString()} TWD`;
    paramSellPrice.innerText = `${pair.sell_price.toLocaleString()} TWD`;
    paramSL.innerText = pair.rr_stop_loss_price ? `${pair.rr_stop_loss_price.toLocaleString()} TWD` : "N/A";
    paramTP.innerText = pair.rr_take_profit_price ? `${pair.rr_take_profit_price.toLocaleString()} TWD` : "N/A";
    const selectedRR = calculatePairRR(pair);
    paramRRBasis.innerText = selectedRR !== null ? `RR ${selectedRR.toFixed(2)}x | ${pair.rr_basis || "N/A"}` : (pair.rr_basis || "N/A");
    rationaleBuy.innerText = pair.buy_reason || "No buy logic recorded.";
    rationaleSell.innerText = pair.sell_reason || "No sell logic recorded.";

    // B. Focus/Scroll the Chart Viewport onto this Position
    focusChartOnPosition(pair.buy_time, pair.sell_time);

    // C. Enable & Load AI Coach chat
    chatInput.disabled = false;
    chatSendBtn.disabled = false;
    chatInput.placeholder = `Ask about Position #${pairId} in ${modelLabel.substring(0, 24)}...`;
    
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
        const modelQuery = activeModelId ? `?model_id=${encodeURIComponent(activeModelId)}` : "";
        const resp = await fetch(`/api/journal/${pairId}${modelQuery}`);
        const thread = await resp.json();
        const pair = tradePairs.find(p => p.pair_id === pairId);
        
        chatViewport.innerHTML = "";
        if (thread.length === 0) {
            chatViewport.innerHTML = `
                <div class="chat-welcome">
                    <i class="fa-solid fa-comments"></i>
                    <p>Begin auditing Position #${pairId}${pair ? ` (${pair.ticker})` : ""} under model ${activeModelId || "active model"}.</p>
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
            body: JSON.stringify({ user_comment: text, model_id: activeModelId })
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
                model_id: activeModelId,
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

if (journalPairSelector) {
    journalPairSelector.addEventListener("change", (e) => {
        const pairId = Number(e.target.value);
        if (Number.isFinite(pairId) && pairId > 0) {
            selectTradePosition(pairId);
        }
    });
}

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
let currentTheme = "light";

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
const advancedToggle = document.getElementById("advanced-toggle");
const advancedPanel = document.getElementById("advanced-settings-panel");
if (advancedToggle && advancedPanel) { 
    advancedToggle.addEventListener("change", (e) => { 
        advancedPanel.style.display = e.target.checked ? "block" : "none"; 
    }); 
}

const runPipelineBtn = document.getElementById("run-pipeline-btn");
const rrThresholdInput = document.getElementById("pipe-rr-threshold");
if (rrThresholdInput) {
    rrThresholdInput.addEventListener("input", () => {
        renderRRThresholdLines();
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
        const rrThreshold = parseFloat(document.getElementById("pipe-rr-threshold").value);

        if (!ticker || !start || !end) {
            showToast("Please fill out all pipeline parameters.", true);
            return;
        }

        runPipelineBtn.innerHTML = "<i class='fa-solid fa-spinner fa-spin'></i> Training in Background...";
        runPipelineBtn.disabled = true;
        
        // Start background polling and flag session
        window.hasTrainedThisSession = true;
        const widget = document.getElementById("training-monitor-widget");
        if (widget) widget.style.display = "block";
        if (typeof trainingPollInterval !== 'undefined') {
            clearInterval(trainingPollInterval);
        }
        trainingPollInterval = setInterval(pollTrainingStatus, 2000);

        try {
            const isAdvanced = advancedToggle ? advancedToggle.checked : false;
            const payload = {
                ticker: ticker,
                start_date: start,
                end_date: end,
                strategy_mode: strategy,
                episodes: episodes,
                early_stop_patience: patience,
                training_rr_threshold: Number.isFinite(rrThreshold) ? rrThreshold : 2.0
            };
            
            if (isAdvanced) {
                payload.lr = parseFloat(document.getElementById("pipe-lr").value) || 0.0001;
                payload.batch_size = parseInt(document.getElementById("pipe-batch-size").value) || 64;
                payload.gamma = parseFloat(document.getElementById("pipe-gamma").value) || 0.95;
                payload.state_lookback = parseInt(document.getElementById("pipe-lookback").value) || 100;
            }

            const resp = await fetch("/api/run_pipeline", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify(payload)
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
        } finally {
            runPipelineBtn.innerHTML = "Initialize DRL Agent";
            runPipelineBtn.disabled = false;
            const globalLoader = document.getElementById("global-loader");
            if (globalLoader) globalLoader.style.display = "none";
        }
    });
}




// Page & Tab Switching Logic
const tabBtns = document.querySelectorAll(".tab-btn");
const originalGrid = document.querySelector(".original-grid");
const pageStep0 = document.getElementById("page-step0");
const pageStep1 = document.getElementById("page-step1");
const appHeader = document.querySelector(".app-header");
const metricsRow = document.querySelector(".metrics-row");

const colLeft = document.querySelector(".col-left");
const colRight = document.querySelector(".col-right");
const chartContainer = document.querySelector(".chart-container");
const coachCol = document.querySelector(".coach-col");
const positionsContainer = document.querySelector(".positions-container");
const parametersCol = document.querySelector(".parameters-col");

if (coachCol) coachCol.style.display = "none";
if (parametersCol) parametersCol.style.display = "none";

function switchTab(target) {
    tabBtns.forEach(b => {
        if(b.getAttribute("data-tab") === target) {
            b.classList.add("active");
            b.style.background = "rgba(139, 92, 246, 0.15)";
            b.style.borderColor = "rgba(139, 92, 246, 0.5)";
            b.style.color = "var(--neon-purple)";
        } else {
            b.classList.remove("active");
            b.style.background = "transparent";
            b.style.borderColor = "transparent";
            b.style.color = "var(--text-muted)";
        }
    });
    
    // Hide all main sections first
    if(originalGrid) originalGrid.style.display = "none";
    if(originalGrid) originalGrid.classList.remove("review-mode");
    if(pageStep0) pageStep0.style.display = "none";
    if(pageStep1) pageStep1.style.display = "none";
    if(appHeader) appHeader.style.display = "none";
    if(metricsRow) metricsRow.style.display = "none";
    
    if (target === "step0") {
        if(pageStep0) pageStep0.style.display = "flex";
    } else if (target === "step1") {
        if(pageStep1) pageStep1.style.display = "flex";
    } else if (target === "step2") {
        if(appHeader) appHeader.style.display = "flex";
        if(metricsRow) metricsRow.style.display = "grid";
        if(originalGrid) originalGrid.style.display = ""; 
        colLeft.style.display = "";
        colRight.style.display = "";
        chartContainer.style.display = "";
        chartContainer.style.height = "";
        positionsContainer.style.display = "";
        coachCol.style.display = "none";
        coachCol.style.height = "";
        parametersCol.style.display = "none";
        if(chartInstance) setTimeout(() => { chartInstance.resize(chartContainer.clientWidth, chartContainer.clientHeight); chartInstance.timeScale().fitContent(); }, 100);
    } else if (target === "step3") {
        if(appHeader) appHeader.style.display = "flex";
        if(metricsRow) metricsRow.style.display = "grid";
        if(originalGrid) originalGrid.style.display = "block";
        colLeft.style.display = "block";
        colRight.style.display = "none";
        chartContainer.style.display = "none";
        chartContainer.style.height = "";
        coachCol.style.display = "flex";
        coachCol.style.height = "80vh"; 
    } else if (target === "step4") {
        if(appHeader) appHeader.style.display = "flex";
        if(metricsRow) metricsRow.style.display = "grid";
        if(originalGrid) originalGrid.style.display = "";
        if(originalGrid) originalGrid.classList.add("review-mode");
        colLeft.style.display = "block";
        colRight.style.display = "block";
        chartContainer.style.display = "flex";
        chartContainer.style.height = "46vh";
        coachCol.style.display = "flex";
        coachCol.style.height = "38vh";
        positionsContainer.style.display = "";
        parametersCol.style.display = "flex";
        if (selectedPairId === null && tradePairs.length > 0) {
            selectTradePosition(tradePairs[0].pair_id);
        }
        if(chartInstance) {
            setTimeout(() => {
                chartInstance.resize(chartContainer.clientWidth, chartContainer.clientHeight);
                renderRRThresholdLines();
                if (selectedPairId !== null) {
                    const pair = tradePairs.find(p => p.pair_id === selectedPairId);
                    if (pair) focusChartOnPosition(pair.buy_time, pair.sell_time);
                }
            }, 100);
        }
    }
}

tabBtns.forEach(btn => {
    btn.addEventListener("click", () => {
        switchTab(btn.getAttribute("data-tab"));
    });
});

const nextStepBtn = document.getElementById("next-to-step1");
if(nextStepBtn) {
    nextStepBtn.addEventListener("click", () => {
        switchTab("step1");
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

// Timeframe Interval Switching Logic
const btnInterval1h = document.getElementById("btn-interval-1h");
const btnInterval4h = document.getElementById("btn-interval-4h");
const btnInterval1d = document.getElementById("btn-interval-1d");
const btnInterval1w = document.getElementById("btn-interval-1w");
const chartTitleText = document.getElementById("chart-title-text");

const intervalButtons = [
    { btn: btnInterval1h, interval: "1h", label: "1H" },
    { btn: btnInterval4h, interval: "4h", label: "4H" },
    { btn: btnInterval1d, interval: "1d", label: "1D" },
    { btn: btnInterval1w, interval: "1w", label: "1W" }
];

intervalButtons.forEach(item => {
    if (item.btn) {
        item.btn.addEventListener("click", async () => {
            if (currentChartInterval === item.interval) return;
            currentChartInterval = item.interval;
            
            // Apply cohesive premium glassmorphic styling states
            intervalButtons.forEach(inner => {
                if (inner.btn) {
                    if (inner.interval === currentChartInterval) {
                        inner.btn.classList.add("active");
                        inner.btn.style.background = "var(--neon-purple)";
                        inner.btn.style.color = "white";
                    } else {
                        inner.btn.classList.remove("active");
                        inner.btn.style.background = "transparent";
                        inner.btn.style.color = "var(--text-muted)";
                    }
                }
            });
            
            if (chartTitleText) {
                chartTitleText.innerHTML = `<i class="fa-solid fa-chart-candlestick"></i> Interday Candlestick Feed (${item.label})`;
            }
            
            // Reload chart data
            await refreshChartOnly();
        });
    }
});

async function refreshChartOnly() {
    try {
        const globalLoader = document.getElementById("global-loader");
        if (globalLoader) globalLoader.style.display = "flex";
        
        const chartResp = await fetch(`/api/chart_data?interval=${currentChartInterval}`);
        const chartJson = await chartResp.json();
        chartData = chartJson.ohlcv || [];
        rrPoints = chartJson.rr_points || [];
        if (candlestickSeries && chartData.length > 0) {
            candlestickSeries.setData(chartData);
            chartInstance.timeScale().fitContent();
            renderRRThresholdLines();
        }
        
        // Re-render chart markers (arrows) on the new candles!
        renderAllChartMarkers();
        
        if (globalLoader) globalLoader.style.display = "none";
    } catch (err) {
        console.error("Error refreshing interval chart:", err);
        showToast("Error loading candlestick timeframe", true);
    }
}

// Bootloader
window.addEventListener("load", () => {
    // Set dynamic default dates for Pipeline Modal (Max 730d limit for 1h interval)
    const endDateInput = document.getElementById("pipe-end");
    const startDateInput = document.getElementById("pipe-start");
    if (endDateInput && startDateInput) {
        const today = new Date();
        const offset = today.getTimezoneOffset() * 60000;
        const localToday = new Date(today.getTime() - offset);
        
        const localPast = new Date(localToday);
        localPast.setDate(localToday.getDate() - 729); 
        
        endDateInput.value = localToday.toISOString().split('T')[0];
        startDateInput.value = localPast.toISOString().split('T')[0];
    }

    initChart();
    loadModels();
});


const openPipelineSidebarBtn = document.getElementById("open-pipeline-sidebar-btn");
if(openPipelineSidebarBtn) {
    openPipelineSidebarBtn.addEventListener("click", () => {
        switchTab("step0");
    });
}


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
        
        // Quietly terminate polling and hide widget on load if not currently training
        if (!data.is_training && !window.hasTrainedThisSession) {
            widget.style.display = "none";
            if (typeof trainingPollInterval !== 'undefined') {
                clearInterval(trainingPollInterval);
            }
            return;
        }
        
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
                
                if (typeof liveChartInstance.addLineSeries === 'function') {
                    liveLossSeries = liveChartInstance.addLineSeries({ color: "#ef4444", lineWidth: 2 });
                } else {
                    liveLossSeries = liveChartInstance.addSeries(LightweightCharts.LineSeries, { color: "#ef4444", lineWidth: 2 });
                }
            }
            
            if (data.logs && data.logs.length > 0) {
                const latestLog = data.logs[data.logs.length - 1];
                const lossVal = (latestLog.avg_loss !== null && latestLog.avg_loss !== undefined) ? latestLog.avg_loss.toFixed(5) : "Building Buffer...";
                const totalN = data.total_episodes || 50;
                document.getElementById("training-status-text").innerHTML = `<b>Epoch ${latestLog.episode} / ${totalN}</b> | Loss: ${lossVal} | Train Ret: ${(latestLog.train_return*100).toFixed(2)}% | Val Ret: ${(latestLog.val_return*100).toFixed(2)}%`;
                
                const baseTime = 1700000000;
                const chartData = data.logs.map(log => ({
                    time: baseTime + log.episode * 3600, // 1 hour step per epoch fake time
                    value: log.avg_loss || 0
                }));
                
                if (liveLossSeries && typeof liveLossSeries.setData === 'function') {
                    liveLossSeries.setData(chartData);
                }
                if (liveChartInstance) {
                    liveChartInstance.timeScale().fitContent();
                }
            } else {
                if (data.ingestion_logs && data.ingestion_logs.length > 0) {
                    const latestIngest = data.ingestion_logs[data.ingestion_logs.length - 1];
                    document.getElementById("training-status-text").innerHTML = `<span style="font-size: 11px; color: var(--neon-cyan);"><i class="fa-solid fa-database"></i> ${latestIngest}</span>`;
                } else {
                    document.getElementById("training-status-text").textContent = "Checking local database & loading feed...";
                }
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
                
                document.getElementById("training-status-text").innerHTML = `
                    <div style="display: flex; flex-direction: column; gap: 8px; margin-top: 8px;">
                        <span style="color: #10b981; font-weight: 700; font-size: 13px;"><i class="fa-solid fa-circle-check"></i> Training Completed!</span>
                        <p style="font-size: 11px; color: var(--text-muted); margin: 0; line-height: 1.4;">The agent model has been fully saved. Click below to proceed to evaluations.</p>
                        <button class="action-btn" id="go-to-evaluation-btn" style="background: linear-gradient(135deg, var(--neon-purple), var(--neon-blue)); border: none; color: white; padding: 8px 12px; border-radius: 6px; cursor: pointer; font-weight: 600; font-size: 12px; display: flex; align-items: center; justify-content: center; gap: 6px; box-shadow: 0 4px 12px rgba(139, 92, 246, 0.3); transition: all 0.2s;">
                            Proceed to Step 2: Evaluation <i class="fa-solid fa-arrow-right"></i>
                        </button>
                    </div>
                `;
                
                const goBtn = document.getElementById("go-to-evaluation-btn");
                if (goBtn) {
                    goBtn.onclick = () => {
                        widget.style.display = "none";
                        switchTab("step2");
                    };
                }
                
                // Epoch complete! Terminate active background polling to keep browser clean
                if (typeof trainingPollInterval !== 'undefined') {
                    clearInterval(trainingPollInterval);
                }
            }
        }
    } catch(err) {
        console.error("Polling error", err);
    }
}

let trainingPollInterval = setInterval(pollTrainingStatus, 2000);
