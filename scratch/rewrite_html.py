import os
from bs4 import BeautifulSoup

path = 'static/index.html'
with open(path, 'r', encoding='utf-8') as f:
    soup = BeautifulSoup(f, 'html.parser')

body = soup.find('body')
if body:
    body['data-theme'] = 'light'
theme_toggle_i = soup.select_one('#theme-toggle i')
if theme_toggle_i:
    theme_toggle_i['class'] = 'fa-solid fa-sun'

strategy_select = soup.find(id='pipe-strategy')
if strategy_select:
    strategy_select.clear()
    option1 = soup.new_tag('option', value='dqn_on_buy_rr_box_sell', selected='')
    option1.string = 'DQN-on-Buy with RR-box-Sell'
    option2 = soup.new_tag('option', value='dqn_position')
    option2.string = 'DQN Position'
    strategy_select.append(option1)
    strategy_select.append(option2)

modal_body = soup.select_one('.modal-body')
if modal_body:
    advanced_html = """
    <!-- ADVANCED SETTINGS TOGGLE -->
    <div class="form-group full-width" style="margin-top: 8px;">
        <label class="toggle-container" style="display: flex; align-items: center; cursor: pointer; color: var(--neon-purple); font-size: 12px; font-weight: 500;">
            <input type="checkbox" id="advanced-toggle" style="margin-right: 8px; cursor: pointer;">
            <span>Show Advanced DQN Hyperparameters</span>
        </label>
    </div>
    <div id="advanced-settings-panel" style="display: none; padding-top: 12px; border-top: 1px solid rgba(255,255,255,0.1); margin-top: 12px;">
        <div class="form-row">
            <div class="form-group"><label>Learning Rate (LR)</label><input type="number" step="0.00001" id="pipe-lr" value="0.0001"></div>
            <div class="form-group"><label>Batch Size</label><input type="number" id="pipe-batch-size" value="64"></div>
        </div>
        <div class="form-row">
            <div class="form-group"><label>Gamma (Discount)</label><input type="number" step="0.01" id="pipe-gamma" value="0.95"></div>
            <div class="form-group"><label>State Lookback</label><input type="number" id="pipe-lookback" value="100"></div>
        </div>
    </div>
    """
    modal_body.append(BeautifulSoup(advanced_html, 'html.parser'))

app_container = soup.select_one('.app-container')
if app_container:
    app_container['style'] = "display: grid; grid-template-columns: 240px 1fr; gap: 24px; padding: 24px; max-width: 1800px; margin: 0 auto; min-height: 100vh;"
    
    sidebar_html = """
    <aside class="sidebar-nav glass-card" style="display: flex; flex-direction: column; padding: 24px; height: calc(100vh - 48px); position: sticky; top: 24px; z-index: 10;">
        <div class="sidebar-logo" style="margin-bottom: 32px; display: flex; align-items: center; gap: 12px;">
            <i class="fa-solid fa-brain fa-2x" style="color: var(--neon-purple);"></i>
            <h2 style="font-size: 20px; font-weight: 700; margin: 0; background: linear-gradient(90deg, var(--neon-purple), var(--neon-blue)); -webkit-background-clip: text; -webkit-text-fill-color: transparent;">SMC × DRL</h2>
        </div>
        <div style="display: flex; flex-direction: column; gap: 12px;">
            <button class="action-btn" id="open-pipeline-sidebar-btn" style="padding: 12px; margin-bottom: 16px;"><i class="fa-solid fa-layer-group"></i> Step 0-1: Train Model</button>
            <h3 style="font-size: 11px; color: var(--text-muted); text-transform: uppercase; letter-spacing: 1px; margin-bottom: 4px; border-bottom: 1px solid rgba(255,255,255,0.05); padding-bottom: 8px;">Pages</h3>
            <button class="tab-btn active" data-tab="step2" style="background: rgba(139, 92, 246, 0.15); border: 1px solid rgba(139, 92, 246, 0.5); color: var(--neon-purple); padding: 12px 16px; border-radius: 8px; cursor: pointer; font-weight: 600; text-align: left; transition: all 0.2s;"><i class="fa-solid fa-chart-pie" style="width: 24px;"></i> Step 2: Evaluation</button>
            <button class="tab-btn" data-tab="step3" style="background: transparent; border: 1px solid transparent; color: var(--text-muted); padding: 12px 16px; border-radius: 8px; cursor: pointer; font-weight: 600; text-align: left; transition: all 0.2s;"><i class="fa-solid fa-robot" style="width: 24px;"></i> Step 3: AI Coach</button>
            <button class="tab-btn" data-tab="step4" style="background: transparent; border: 1px solid transparent; color: var(--text-muted); padding: 12px 16px; border-radius: 8px; cursor: pointer; font-weight: 600; text-align: left; transition: all 0.2s;"><i class="fa-solid fa-clipboard-check" style="width: 24px;"></i> Step 4: Audit Review</button>
        </div>
    </aside>
    """
    sidebar_node = BeautifulSoup(sidebar_html, 'html.parser')
    
    main_workspace = soup.new_tag('div', **{'class': 'main-workspace', 'style': 'display: flex; flex-direction: column; min-width: 0;'})
    for child in list(app_container.children):
        if child.name is None and not child.string.strip(): continue
        main_workspace.append(child)
        
    app_container.clear()
    app_container.append(sidebar_node)
    app_container.append(main_workspace)
    
old_btn = soup.find(id='open-pipeline-btn')
if old_btn:
    old_btn.decompose()

with open(path, 'w', encoding='utf-8') as f:
    f.write(str(soup))
print("HTML rewrite successful!")
