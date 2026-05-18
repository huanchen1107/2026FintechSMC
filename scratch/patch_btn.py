import os
path = 'static/app.js'
with open(path, 'r', encoding='utf-8') as f:
    js = f.read()

btn_logic = """
const openPipelineSidebarBtn = document.getElementById("open-pipeline-sidebar-btn");
if(openPipelineSidebarBtn) {
    openPipelineSidebarBtn.addEventListener("click", () => {
        switchTab("step0");
    });
}
"""

if "switchTab(\"step0\");" not in js and "open-pipeline-sidebar-btn" not in js:
    js += "\n" + btn_logic
    with open(path, 'w', encoding='utf-8') as f:
        f.write(js)
    print("Patched button logic successfully!")
else:
    print("Already patched.")
