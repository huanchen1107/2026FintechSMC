import os

path = 'static/app.js'
with open(path, 'r', encoding='utf-8') as f:
    js = f.read()

# 1. Update pipeline modal trigger ID
js = js.replace('const pipelineBtn = document.getElementById("open-pipeline-btn");', 
                'const pipelineBtn = document.getElementById("open-pipeline-sidebar-btn");\nconst advancedToggle = document.getElementById("advanced-toggle");\nconst advancedPanel = document.getElementById("advanced-settings-panel");\nif (advancedToggle && advancedPanel) { advancedToggle.addEventListener("change", (e) => { advancedPanel.style.display = e.target.checked ? "block" : "none"; }); }')

# 2. Add Tab Logic right before Fullscreen Chart Logic
tab_logic = """
// Tab Switching Logic
const tabBtns = document.querySelectorAll(".tab-btn");
const originalGrid = document.querySelector(".original-grid");
const colLeft = document.querySelector(".col-left");
const colRight = document.querySelector(".col-right");
const chartContainer = document.querySelector(".chart-container");
const coachCol = document.querySelector(".coach-col");
const positionsContainer = document.querySelector(".positions-container");
const parametersCol = document.querySelector(".parameters-col");

if (coachCol) coachCol.style.display = "none";
if (parametersCol) parametersCol.style.display = "none";

tabBtns.forEach(btn => {
    btn.addEventListener("click", () => {
        tabBtns.forEach(b => {
            b.classList.remove("active");
            b.style.background = "transparent";
            b.style.borderColor = "transparent";
            b.style.color = "var(--text-muted)";
        });
        
        btn.classList.add("active");
        btn.style.background = "rgba(139, 92, 246, 0.15)";
        btn.style.borderColor = "rgba(139, 92, 246, 0.5)";
        btn.style.color = "var(--neon-purple)";
        
        const target = btn.getAttribute("data-tab");
        
        if (target === "step2") {
            originalGrid.style.display = ""; 
            colLeft.style.display = "";
            colRight.style.display = "";
            chartContainer.style.display = "";
            positionsContainer.style.display = "";
            coachCol.style.display = "none";
            parametersCol.style.display = "none";
            if(chartInstance) setTimeout(() => { chartInstance.resize(chartContainer.clientWidth, chartContainer.clientHeight); chartInstance.timeScale().fitContent(); }, 100);
        } else if (target === "step3") {
            originalGrid.style.display = "block";
            colLeft.style.display = "block";
            colRight.style.display = "none";
            chartContainer.style.display = "none";
            coachCol.style.display = "flex";
            coachCol.style.height = "80vh"; 
        } else if (target === "step4") {
            originalGrid.style.display = "block";
            colLeft.style.display = "none";
            colRight.style.display = "block";
            positionsContainer.style.display = "none";
            parametersCol.style.display = "flex";
        }
    });
});

// Fullscreen Chart Logic"""

js = js.replace('// Fullscreen Chart Logic', tab_logic)

# 3. Modify fetch logic to be non-blocking and include advanced params
old_fetch = """        try {
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
        }"""

new_fetch = """
        runPipelineBtn.innerHTML = "<i class='fa-solid fa-spinner fa-spin'></i> Training in Background...";
        runPipelineBtn.disabled = true;

        try {
            const isAdvanced = advancedToggle ? advancedToggle.checked : false;
            const payload = {
                ticker: ticker,
                start_date: start,
                end_date: end,
                strategy_mode: strategy,
                episodes: episodes,
                early_stop_patience: patience
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
                showToast(`Training Success! Model ${data.model_id.substring(0, 15)} is ready.`, false);
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
            runPipelineBtn.innerHTML = "<i class='fa-solid fa-microchip'></i> Initialize Training";
            runPipelineBtn.disabled = false;
        }"""

js = js.replace(old_fetch, new_fetch)

with open(path, 'w', encoding='utf-8') as f:
    f.write(js)
print("JS rewrite successful!")
