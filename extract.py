import os
import re

source = r'c:\Users\yagiz\betpredicotr\nba_predictor_v12.py'
dest_dir = r'c:\Users\yagiz\betpredicotr\app\web\templates'
dest = os.path.join(dest_dir, 'index.html')

os.makedirs(dest_dir, exist_ok=True)

with open(source, 'r', encoding='utf-8') as f:
    content = f.read()

# Find HTML boundaries
match = re.search(r'<!DOCTYPE html>.*?</html>', content, re.IGNORECASE | re.DOTALL)
if match:
    html_str = match.group(0)
    
    # Remove Style and Script
    html_str = re.sub(r'<style>.*?</style>', '<link rel="stylesheet" href="/static/style.css">', html_str, flags=re.DOTALL)
    html_str = re.sub(r'<script(?! src).*?>.*?</script>', '<script src="/static/app.js"></script>', html_str, flags=re.DOTALL)
    
    # Modify for Kelly & Win Rate
    html_str = html_str.replace('<span>RİSK</span>', '<span>KAZANMA ORANI</span>')
    html_str = html_str.replace('<span>GÜVEN</span>', '<span style="text-align:right">KELLY ÖNERİSİ</span>')
    
    # Add Bankroll input to control panel
    bankroll_html = '''<div class="cp-group">
        <label>Kasa (TL):</label>
        <input type="number" id="bankroll" placeholder="Örn: 1000" style="width:70px;background:var(--bg3);color:var(--text);border:1px solid var(--border);border-radius:4px;padding:4px;" value="1000">
      </div>'''
    
    if '<div class="cp-group">' in html_str:
        html_str = html_str.replace('<div class="cp-group">', bankroll_html + '\n      <div class="cp-group">', 1)
        
    with open(dest, 'w', encoding='utf-8') as f:
        f.write(html_str)
    print(f"SUCCESS: Wrote {len(html_str)} bytes")
else:
    print("FAILED: Could not find HTML block.")
