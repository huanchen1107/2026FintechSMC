import os

path = 'static/app.js'
with open(path, 'r', encoding='utf-8') as f:
    js = f.read()

# Remove the old modal open/close logic
js = js.replace('const pipelineBtn = document.getElementById("open-pipeline-sidebar-btn");', '')
js = js.replace('const pipelineModal = document.getElementById("pipeline-modal");', '')
js = js.replace('const closePipelineBtn = document.getElementById("close-pipeline-btn");', '')
js = js.replace('if (pipelineBtn) { pipelineBtn.addEventListener("click", () => { pipelineModal.classList.add("show"); }); }', '')
js = js.replace('if (closePipelineBtn) { closePipelineBtn.addEventListener("click", () => { pipelineModal.classList.remove("show"); }); }', '')

# Replace tab logic
old_tab_logic = """
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
"""

new_tab_logic = """
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
        positionsContainer.style.display = "";
        coachCol.style.display = "none";
        parametersCol.style.display = "none";
        if(chartInstance) setTimeout(() => { chartInstance.resize(chartContainer.clientWidth, chartContainer.clientHeight); chartInstance.timeScale().fitContent(); }, 100);
    } else if (target === "step3") {
        if(appHeader) appHeader.style.display = "flex";
        if(metricsRow) metricsRow.style.display = "grid";
        if(originalGrid) originalGrid.style.display = "block";
        colLeft.style.display = "block";
        colRight.style.display = "none";
        chartContainer.style.display = "none";
        coachCol.style.display = "flex";
        coachCol.style.height = "80vh"; 
    } else if (target === "step4") {
        if(appHeader) appHeader.style.display = "flex";
        if(metricsRow) metricsRow.style.display = "grid";
        if(originalGrid) originalGrid.style.display = "block";
        colLeft.style.display = "none";
        colRight.style.display = "block";
        positionsContainer.style.display = "none";
        parametersCol.style.display = "flex";
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
"""

if old_tab_logic in js:
    js = js.replace(old_tab_logic, new_tab_logic)
else:
    print("Warning: old tab logic not found for replacement.")

with open(path, 'w', encoding='utf-8') as f:
    f.write(js)
print("app.js updated successfully!")
