import os
from bs4 import BeautifulSoup

path = 'static/index.html'
with open(path, 'r', encoding='utf-8') as f:
    soup = BeautifulSoup(f, 'html.parser')

sidebar_nav = soup.select_one('.sidebar-nav')
if sidebar_nav:
    buttons_container = sidebar_nav.find('div', style=lambda value: value and 'flex-direction: column' in value)
    if buttons_container:
        buttons_container.clear()
        
        new_html = """
        <div class="sidebar-item" style="display: flex; flex-direction: column; gap: 4px;">
            <span style="font-size: 10px; color: var(--text-muted); text-transform: uppercase; letter-spacing: 1px; padding-left: 8px;">Data Ingestion</span>
            <button class="tab-btn" data-tab="step0" style="background: transparent; border: 1px solid transparent; color: var(--text-muted); padding: 12px 16px; border-radius: 8px; cursor: pointer; font-weight: 600; text-align: left; transition: all 0.2s;"><i class="fa-solid fa-database" style="width: 24px;"></i> Step 0</button>
        </div>
        
        <div class="sidebar-item" style="display: flex; flex-direction: column; gap: 4px;">
            <span style="font-size: 10px; color: var(--text-muted); text-transform: uppercase; letter-spacing: 1px; padding-left: 8px;">Agent Architecture</span>
            <button class="tab-btn" data-tab="step1" style="background: transparent; border: 1px solid transparent; color: var(--text-muted); padding: 12px 16px; border-radius: 8px; cursor: pointer; font-weight: 600; text-align: left; transition: all 0.2s;"><i class="fa-solid fa-microchip" style="width: 24px;"></i> Step 1</button>
        </div>

        <div class="sidebar-item" style="display: flex; flex-direction: column; gap: 4px;">
            <span style="font-size: 10px; color: var(--text-muted); text-transform: uppercase; letter-spacing: 1px; padding-left: 8px;">Evaluation</span>
            <button class="tab-btn active" data-tab="step2" style="background: rgba(139, 92, 246, 0.15); border: 1px solid rgba(139, 92, 246, 0.5); color: var(--neon-purple); padding: 12px 16px; border-radius: 8px; cursor: pointer; font-weight: 600; text-align: left; transition: all 0.2s;"><i class="fa-solid fa-chart-pie" style="width: 24px;"></i> Step 2</button>
        </div>
        
        <div class="sidebar-item" style="display: flex; flex-direction: column; gap: 4px;">
            <span style="font-size: 10px; color: var(--text-muted); text-transform: uppercase; letter-spacing: 1px; padding-left: 8px;">AI Quant Coach</span>
            <button class="tab-btn" data-tab="step3" style="background: transparent; border: 1px solid transparent; color: var(--text-muted); padding: 12px 16px; border-radius: 8px; cursor: pointer; font-weight: 600; text-align: left; transition: all 0.2s;"><i class="fa-solid fa-robot" style="width: 24px;"></i> Step 3</button>
        </div>
        
        <div class="sidebar-item" style="display: flex; flex-direction: column; gap: 4px;">
            <span style="font-size: 10px; color: var(--text-muted); text-transform: uppercase; letter-spacing: 1px; padding-left: 8px;">Audit Review</span>
            <button class="tab-btn" data-tab="step4" style="background: transparent; border: 1px solid transparent; color: var(--text-muted); padding: 12px 16px; border-radius: 8px; cursor: pointer; font-weight: 600; text-align: left; transition: all 0.2s;"><i class="fa-solid fa-clipboard-check" style="width: 24px;"></i> Step 4</button>
        </div>
        """
        
        buttons_container['style'] = "display: flex; flex-direction: column; gap: 16px;"
        buttons_container.append(BeautifulSoup(new_html, 'html.parser'))

with open(path, 'w', encoding='utf-8') as f:
    f.write(str(soup))
print("HTML successfully rewritten!")
