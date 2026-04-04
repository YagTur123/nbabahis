import sys
import datetime
from app.core.config import log
from app.core.utils import seasons
import app.core.state as state
from app.data.nba_api import _load_lig, fetch_injury_report, nba_request
from app.services.predict_service import get_run_preds
from app.services.sgp_service import build_sgps
from nba_api.stats.endpoints import scoreboardv2
import colorama
from colorama import Fore, Style

colorama.init(autoreset=True)

def run_cli_scan():
    today = datetime.datetime.now().strftime('%Y-%m-%d')
    print(f"\n{Fore.CYAN}{Style.BRIGHT}==========================================")
    print(f"{Fore.CYAN}🏀 NBA PREDICTOR v12.0 - OTOMATİK TARAMA 🏀")
    print(f"{Fore.CYAN}=========================================={Style.RESET_ALL}")
    print(f"{Fore.YELLOW}Tarih:{Style.RESET_ALL} {today}\n")

    # 1. Lig verileri ve sakatlık raporunu çek
    curr_s, prev_s = seasons(today)
    state._curr_s, state._prev_s = curr_s, prev_s
    
    print(f"{Fore.MAGENTA}[1/4] Lig istatistikleri ve Savunma (DvP) verileri indiriliyor...{Style.RESET_ALL}")
    _load_lig(curr_s)
    
    print(f"{Fore.MAGENTA}[2/4] Hastane raporları ve Rotasyon bilgisi taranıyor...{Style.RESET_ALL}")
    fetch_injury_report(today)

    # 2. Bugünün maçlarını al
    print(f"{Fore.MAGENTA}[3/4] Bugünün eşleşmeleri çekiliyor...{Style.RESET_ALL}")
    try:
        dfs = nba_request(scoreboardv2.ScoreboardV2, game_date=today)
        if not dfs or dfs[0].empty:
            print(f"{Fore.RED}Bugün için planlanmış NBA maçı bulunamadı.{Style.RESET_ALL}")
            sys.exit(0)
            
        sb = dfs[0]
        pairs = []
        for _, row in sb.iterrows():
            hid, vid = int(row['HOME_TEAM_ID']), int(row['VISITOR_TEAM_ID'])
            pairs += [(hid, vid, True), (vid, hid, False)]
        print(f"{Fore.GREEN}Toplam {len(pairs)//2} maç bulundu. Analiz başlıyor...{Style.RESET_ALL}\n")
    except Exception as e:
        print(f"{Fore.RED}Maçlar çekilirken hata oluştu: {e}{Style.RESET_ALL}")
        sys.exit(1)

    # 3. Tüm tahminleri (XGBoost/LightGBM Optuna kalibreli) çalıştır
    print(f"{Fore.MAGENTA}[4/4] Yapay Zeka Modelleri çalışıyor (Tüm tahminler hesaplanıyor, bu işlem birkaç dakika sürebilir)...{Style.RESET_ALL}")
    all_preds = get_run_preds(pairs, today)
    
    if not all_preds:
        print(f"{Fore.RED}Hiçbir geçerli sonuç veya yüksek kazanma oranlı veri bulunamadı.{Style.RESET_ALL}")
        sys.exit(0)

    # 4. Korelasyon motoru (SGP Kombineleri)
    sgps = build_sgps(all_preds)
    
    # 5. Ekrana Bastırma (Kombineler)
    print(f"\n{Fore.GREEN}{Style.BRIGHT}🔥 GÜNÜN KOMBİNE FIRSATLARI (SGP) 🔥{Style.RESET_ALL}")
    print(f"{Fore.YELLOW}--------------------------------------------------{Style.RESET_ALL}")
    
    if sgps:
        for idx, sgp in enumerate(sgps, 1):
            print(f"\n{Fore.CYAN}KOMBİNE #{idx} - {sgp['type']}{Style.RESET_ALL}")
            print(f"{Fore.WHITE}Başlık:{Style.RESET_ALL} {sgp['title']}")
            print(f"{Fore.WHITE}Açıklama:{Style.RESET_ALL} {sgp['description']}")
            print(f"{Fore.GREEN}Kazanma İhtimali:{Style.RESET_ALL} %{sgp['combined_prob']}")
            print(f"{Fore.YELLOW}Bahisler:{Style.RESET_ALL}")
            for leg in sgp['legs']:
                odds_str = f"({leg.get('best_bookmaker', 'SIM')} {leg.get('market_odds', '-')})" if leg.get('has_market_odds') else "(SIM)"
                print(f"  - {Fore.WHITE}{leg['player']}{Style.RESET_ALL} {Fore.MAGENTA}{leg['stat']}{Style.RESET_ALL} OVER {Fore.YELLOW}{leg['line']}{Style.RESET_ALL} {odds_str} | Bireysel Kazanma: %{leg.get('win_prob', 0)}")
    else:
        print(f"{Fore.RED}Bugün için güçlü birbirini besleyen SGP kombinesi bulunamadı.{Style.RESET_ALL}")

    # En Güvenilir Bireysel Tahminler
    print(f"\n\n{Fore.GREEN}{Style.BRIGHT}🏆 EN GÜVENİLİR BİREYSEL TAHMİNLER (TOP 10) 🏆{Style.RESET_ALL}")
    print(f"{Fore.YELLOW}--------------------------------------------------{Style.RESET_ALL}")
    
    best_preds = sorted([p for p in all_preds if p.get('win_prob', 0) > 55], key=lambda x: (x.get('edge', 0) * x.get('win_prob', 0)), reverse=True)[:10]
    
    for px in best_preds:
        odds_str = f"[{px.get('best_bookmaker', 'SIM')} {px.get('market_odds', '-')}]" if px.get('has_market_odds') else "[SIM]"
        trend_str = f" {px.get('trend_label')}" if px.get('trend_label') else ""
        print(f"• {Fore.CYAN}{px['player']}{Style.RESET_ALL} ({px['team']}) - {Fore.MAGENTA}{px['stat']}{Style.RESET_ALL} {Fore.YELLOW}OVER {px['line']}{Style.RESET_ALL} {odds_str}")
        print(f"  Kazanma Olasılığı: {Fore.GREEN}%{px.get('win_prob', 0)}{Style.RESET_ALL} | Edge: {Fore.GREEN}+{px.get('edge', 0)}{Style.RESET_ALL}{trend_str}")
    
    print(f"\n{Fore.CYAN}{Style.BRIGHT}==========================================")
    print(f"{Fore.CYAN}Analiz Tamamlandı.{Style.RESET_ALL} Çıkmak için herhangi bir tuşa basabilirsin.")
    input()
    
if __name__ == '__main__':
    run_cli_scan()
