import os
from bs4 import BeautifulSoup

path = 'static/index.html'
with open(path, 'r', encoding='utf-8') as f:
    soup = BeautifulSoup(f, 'html.parser')

# 1. Update Sidebar Navigation
sidebar_nav = soup.select_one('.sidebar-nav')
if sidebar_nav:
    # Find the old Step 0-1 button and replace it
    old_btn = soup.find(id='open-pipeline-sidebar-btn')
    if old_btn:
        old_btn.decompose()
        
    # Find the "Pages" header
    pages_header = soup.find('h3', string='Pages')
    if pages_header:
        # Create new tabs
        step0_btn = soup.new_tag('button', **{'class': 'tab-btn', 'data-tab': 'step0', 'style': 'background: transparent; border: 1px solid transparent; color: var(--text-muted); padding: 12px 16px; border-radius: 8px; cursor: pointer; font-weight: 600; text-align: left; transition: all 0.2s;'})
        step0_btn.append(BeautifulSoup('<i class="fa-solid fa-database" style="width: 24px;"></i> Step 0: Data Ingestion', 'html.parser'))
        
        step1_btn = soup.new_tag('button', **{'class': 'tab-btn', 'data-tab': 'step1', 'style': 'background: transparent; border: 1px solid transparent; color: var(--text-muted); padding: 12px 16px; border-radius: 8px; cursor: pointer; font-weight: 600; text-align: left; transition: all 0.2s;'})
        step1_btn.append(BeautifulSoup('<i class="fa-solid fa-microchip" style="width: 24px;"></i> Step 1: Agent Training', 'html.parser'))
        
        pages_header.insert_after(step1_btn)
        pages_header.insert_after(step0_btn)

# 2. Delete the Modal and move contents to Main Workspace
modal = soup.find(id='pipeline-modal')
if modal:
    modal.decompose()

# 3. Create the new Step 0 and Step 1 pages in the main workspace
main_workspace = soup.select_one('.main-workspace')
if main_workspace:
    step0_html = """
    <div id="page-step0" class="tab-page" style="display: none; padding-top: 24px; flex: 1;">
        <div class="glass-card" style="max-width: 700px; margin: 0 auto; padding: 40px; border-top: 4px solid var(--neon-blue);">
            <h2 style="font-size: 24px; margin-bottom: 8px;"><i class="fa-solid fa-database"></i> Step 0: Market Data Ingestion</h2>
            <p style="color: var(--text-muted); margin-bottom: 32px;">Select the target asset and define the historical backtest window limits for data extraction.</p>
            
            <div class="form-group">
                <label>Target Ticker (Yahoo Finance)</label>
                <input type="text" id="pipe-ticker" value="2330.TW" placeholder="e.g. AAPL, 2330.TW">
            </div>
            <div class="form-row">
                <div class="form-group">
                    <label>Start Date</label>
                    <input type="date" id="pipe-start" value="2023-01-01">
                </div>
                <div class="form-group">
                    <label>End Date</label>
                    <input type="date" id="pipe-end" value="2024-01-01">
                </div>
            </div>
            <div style="display: flex; justify-content: flex-end; margin-top: 32px;">
                <button class="action-btn" id="next-to-step1">Proceed to Step 1 <i class="fa-solid fa-arrow-right"></i></button>
            </div>
        </div>
    </div>
    """
    
    step1_html = """
    <div id="page-step1" class="tab-page" style="display: none; padding-top: 24px; flex: 1;">
        <div class="glass-card" style="max-width: 700px; margin: 0 auto; padding: 40px; border-top: 4px solid var(--neon-purple);">
            <h2 style="font-size: 24px; margin-bottom: 8px;"><i class="fa-solid fa-microchip"></i> Step 1: Agent Architecture</h2>
            <p style="color: var(--text-muted); margin-bottom: 32px;">Define the Deep Q-Learning model parameters for the selected asset.</p>
            
            <div class="form-group full-width">
                <label>Trading Strategy Pattern</label>
                <select id="pipe-strategy">
                    <option value="dqn_on_buy_rr_box_sell" selected>DQN-on-Buy with RR-box-Sell</option>
                    <option value="dqn_position">DQN Position</option>
                </select>
            </div>
            <div class="form-row">
                <div class="form-group">
                    <label>Max Epochs (Episodes)</label>
                    <input type="number" id="pipe-episodes" value="500" min="10" max="2000">
                </div>
                <div class="form-group">
                    <label>Early Stop Patience</label>
                    <input type="number" id="pipe-patience" value="25" min="5" max="100">
                </div>
            </div>

            <!-- ADVANCED SETTINGS TOGGLE -->
            <div class="form-group full-width" style="margin-top: 16px;">
                <label class="toggle-container" style="display: flex; align-items: center; cursor: pointer; color: var(--neon-purple); font-size: 13px; font-weight: 500;">
                    <input type="checkbox" id="advanced-toggle" style="margin-right: 8px; cursor: pointer;">
                    <span>Show Advanced DQN Hyperparameters</span>
                </label>
            </div>

            <div id="advanced-settings-panel" style="display: none; padding-top: 16px; border-top: 1px solid rgba(255,255,255,0.1); margin-top: 16px;">
                <div class="form-row">
                    <div class="form-group">
                        <label>Learning Rate (LR)</label>
                        <input type="number" step="0.00001" id="pipe-lr" value="0.0001">
                    </div>
                    <div class="form-group">
                        <label>Batch Size</label>
                        <input type="number" id="pipe-batch-size" value="64">
                    </div>
                </div>
                <div class="form-row">
                    <div class="form-group">
                        <label>Gamma (Discount)</label>
                        <input type="number" step="0.01" id="pipe-gamma" value="0.95">
                    </div>
                    <div class="form-group">
                        <label>State Lookback</label>
                        <input type="number" id="pipe-lookback" value="100">
                    </div>
                </div>
            </div>

            <div style="display: flex; justify-content: flex-end; margin-top: 40px;">
                <button id="run-pipeline-btn" class="action-btn" style="padding: 16px 32px; font-size: 16px; border-radius: 12px; background: linear-gradient(135deg, var(--neon-purple), var(--neon-blue));"><i class="fa-solid fa-bolt"></i> Initialize DRL Pipeline</button>
            </div>
        </div>
    </div>
    """
    
    # Insert new pages after the original-grid
    orig_grid = main_workspace.find(class_='original-grid')
    if orig_grid:
        orig_grid.insert_after(BeautifulSoup(step1_html, 'html.parser'))
        orig_grid.insert_after(BeautifulSoup(step0_html, 'html.parser'))

with open(path, 'w', encoding='utf-8') as f:
    f.write(str(soup))
print("HTML Step Pages successfully created!")
