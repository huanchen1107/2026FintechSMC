import os
from bs4 import BeautifulSoup

path = 'static/index.html'
with open(path, 'r', encoding='utf-8') as f:
    soup = BeautifulSoup(f, 'html.parser')

body = soup.find('body')
if body and not soup.find(id='training-monitor-widget'):
    widget_html = """
    <!-- FLOATING TRAINING MONITOR WIDGET -->
    <div id="training-monitor-widget" class="glass-card" style="display: none; position: fixed; bottom: 24px; right: 24px; width: 400px; padding: 16px; z-index: 1000; box-shadow: 0 8px 32px rgba(0,0,0,0.5);">
        <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px;">
            <h3 style="margin: 0; font-size: 14px; color: var(--neon-blue);"><i class="fa-solid fa-satellite-dish fa-spin" style="margin-right: 6px;"></i>Live Training Monitor</h3>
            <span id="training-ticker-badge" style="background: rgba(139, 92, 246, 0.2); color: var(--neon-purple); padding: 4px 8px; border-radius: 4px; font-size: 11px; font-weight: bold;">TICKER</span>
        </div>
        <p id="training-status-text" style="font-size: 12px; color: var(--text-muted); margin-bottom: 12px;">Waiting for PyTorch epoch 1...</p>
        <div id="training-chart-container" style="width: 100%; height: 150px; background: rgba(0,0,0,0.2); border-radius: 8px; overflow: hidden; border: 1px solid rgba(255,255,255,0.05);"></div>
    </div>
    """
    body.append(BeautifulSoup(widget_html, 'html.parser'))

with open(path, 'w', encoding='utf-8') as f:
    f.write(str(soup))
print("Widget added to index.html!")
