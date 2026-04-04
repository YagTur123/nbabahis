import os
import sys

from app.data.stake_api import get_stake_client
from app.data.stake_api import STAKE_TO_MARKET

def main():
    print("="*60)
    print("Stake.com NBA Player Props CLI - DrissionPage Otomatı")
    print("="*60)
    print("DrissionPage başlatılıyor (Sıfır Cookie, %100 Otonom)...")
    
    with get_stake_client() as client:
        print("\nGüncel NBA maçları çekiliyor (Lütfen bekleyin)...")
        fixtures_slugs = client.fetch_fixtures()
        
        if not fixtures_slugs:
            print("\nMaç bulunamadı. Stake'te aktif maç yoktur veya bağlantı hatası oluştu.\n")
            return

        print("\n--- GÜNÜN MAÇLARI ---")
        for i, slug in enumerate(fixtures_slugs, 1):
            name = slug.split('/')[-1].replace('-vs-', ' vs ').replace('-', ' ').title()
            print(f"{i}. {name}")
            
        try:
            match_idx = int(input("\nBir maç seçin (Numara girin): ")) - 1
            if match_idx < 0 or match_idx >= len(fixtures_slugs):
                print("Geçersiz maç seçimi!")
                return
        except ValueError:
            print("Lütfen geçerli bir sayı girin!")
            return
            
        selected_slug = fixtures_slugs[match_idx]
        match_readable_name = selected_slug.split('/')[-1].replace('-vs-', ' vs ').replace('-', ' ').title()
        
        print(f"\nSeçilen Maç: {match_readable_name}")
        print("Oyuncu baremleri (Marketler) DrissionPage aracılığıyla çekiliyor...\n")
        
        fixt_data = client.fetch_markets_for_fixture(selected_slug)
        if not fixt_data:
            print("Bu maç için piyasa (market) verisi bulunamadı.")
            return

        import json
        with open("debug_fixt_data.json", "w", encoding="utf-8") as f:
            json.dump(fixt_data, f, ensure_ascii=False, indent=2)

        import re
        from app.core.utils import _norm_name

        players_data = {}
        
        # Rekürsif bir fonksiyonla tüm veriyi dolaşıp içinde 'markets' olanları bulalım
        def find_markets(data):
            found_markets = []
            if isinstance(data, dict):
                if 'markets' in data and isinstance(data['markets'], list):
                    found_markets.extend(data['markets'])
                for k, v in data.items():
                    found_markets.extend(find_markets(v))
            elif isinstance(data, list):
                for item in data:
                    found_markets.extend(find_markets(item))
            return found_markets
            
        all_markets = find_markets(fixt_data)

        for market in all_markets:
            market_name = market.get("name", "")
            
            internal_mkt = None
            for k, v in STAKE_TO_MARKET.items():
                if k.lower() in market_name.lower():
                    internal_mkt = k
                    break
                    
            if not internal_mkt:
                continue
                
            for sel in market.get("outcomes", []) + market.get("selections", []):
                sel_name = sel.get("name", "")
                odds = float(sel.get("odds", 0))
                
                pts = 0.0
                match = re.search(r'\d+\.?\d*', sel_name)
                if match:
                    pts = float(match.group())
                
                if not sel_name or not pts or not odds:
                    continue
                            
                is_over = "Over" in sel_name or "O " in sel_name or "over" in sel_name.lower()
                is_under = "Under" in sel_name or "U " in sel_name or "under" in sel_name.lower()
                
                if not (is_over or is_under):
                    continue
                    
                player_raw = f"{market_name} {sel_name}"
                keywords_to_remove = [
                            r'Player Points\s*\+\s*Rebounds\s*\+\s*Assists', r'Player Points\s*\+\s*Rebounds',
                            r'Player Points\s*\+\s*Assists', r'Player Rebounds\s*\+\s*Assists',
                            r'Player Points', r'Player Rebounds', r'Player Assists', r'Player Threes',
                            r'Player Blocks\s*\+\s*Steals', r'Player Blocks', r'Player Steals', r'Player Turnovers',
                            r'Over', r'Under', r'\(O\)', r'\(U\)', r'\bO\b', r'\bU\b', r'[0-9.]+', r'\(', r'\)', r'-'
                ]
                for kw in keywords_to_remove:
                    player_raw = re.sub(kw, ' ', player_raw, flags=re.IGNORECASE)
                player_raw = player_raw.strip()
                
                pname = _norm_name(player_raw)
                if not pname:
                    continue
                
                if pname not in players_data:
                    players_data[pname] = {}
                    
                if internal_mkt not in players_data[pname]:
                    players_data[pname][internal_mkt] = {"line": pts, "Over": 0.0, "Under": 0.0}
                    
                if pts == players_data[pname][internal_mkt]["line"]:
                    if is_over:
                        players_data[pname][internal_mkt]["Over"] = odds
                    else:
                        players_data[pname][internal_mkt]["Under"] = odds
                                
        if not players_data:
            print("Bu maça ait Player Props açıklanmamış veya Stake tarafından yansıtılmadı.")
            return
            
        print(f"--- {match_readable_name} MAÇINDAKİ OYUNCULAR ---")
        player_names = sorted(list(players_data.keys()))
        for i, p_name in enumerate(player_names, 1):
            print(f"{i}. {p_name}")
            
        try:
            player_idx = int(input("\nBir oyuncunun istatistiklerini görmek için numarasını girin: ")) - 1
            if player_idx < 0 or player_idx >= len(player_names):
                print("Geçersiz oyuncu seçimi!")
                return
        except ValueError:
            print("Lütfen geçerli bir sayı girin!")
            return
            
        selected_player = player_names[player_idx]
        
        print(f"\n{'='*75}")
        print(f"{selected_player.upper()} BAREMLERİ (STAKE.COM)")
        print(f"{'='*75}")
        print(f"| {'Market (Piyasa)':<35} | {'Line':<5} | {'Over (Üst)':<10} | {'Under (Alt)':<10} |")
        print(f"|{'-'*37}|{'-'*7}|{'-'*12}|{'-'*12}|")
        
        player_markets = players_data[selected_player]
        for mName, mData in player_markets.items():
            print(f"| {mName:<35} | {mData['line']:<5.1f} | {mData['Over']:<10.2f} | {mData['Under']:<10.2f} |")
        print(f"{'='*75}\n")

if __name__ == "__main__":
    main()
