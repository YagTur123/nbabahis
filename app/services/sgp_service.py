import itertools
from typing import List, Dict

def calculate_correlation(p1: Dict, p2: Dict) -> dict:
    """
    İki tahmin arasındaki istatistiksel ve basketbol mantığına dayalı korelasyonu hesaplar.
    Dönen sözlükte:
    - score: Korelasyon çarpanı (1.0 = nötr)
    - tag: Arayüzde gösterilecek etiket (Örn: "Pick & Roll")
    - conflict: True ise bu kupon yapılmamalı
    """
    t1, t2 = p1['team'], p2['team']
    s1, s2 = p1['stat'], p2['stat']
    out1, out2 = p1['expected_outcome'], p2['expected_outcome']
    score = 1.0
    tag = ""
    conflict = False

    same_team = (t1 == t2)
    same_player = (p1['player'] == p2['player'])
    same_stat = (s1 == s2)

    if same_player:
        if same_stat:
            return {'score': 0, 'tag': 'Geçersiz', 'conflict': True}
        # Aynı oyuncu (Sayı Üst + Asist Üst) => Uyumlu
        if out1 == 'OVER' and out2 == 'OVER':
            score = 1.10
            tag = "Formda Oyuncu"
        elif out1 == 'UNDER' and out2 == 'UNDER':
            score = 1.10
            tag = "Kötü Gün"
        else:
            score = 0.90 # Biri üst biri alt ise risklidir
            tag = "Zıt Eğilim"
            
    elif same_team:
        # Aynı takım takım arkadaşları
        
        # Guard Asist + Uzun Sayı (Pick & Roll İkilisi)
        if out1 == 'OVER' and out2 == 'OVER':
            if (s1 == 'AST' and s2 == 'PTS') or (s2 == 'AST' and s1 == 'PTS'):
                score = 1.30
                tag = "Pick & Roll (Asist+Sayı)"
                
        # Aynı takımda iki skorere Sayı Üst yazmak
        if s1 == 'PTS' and s2 == 'PTS' and out1 == 'OVER' and out2 == 'OVER':
            score = 0.85
            tag = "Kullanım (Top) Paylaşımı Riski"
            
        # Aynı takımda iki Ribaunt Üst
        if s1 in ('REB', 'TRB') and s2 in ('REB', 'TRB') and out1 == 'OVER' and out2 == 'OVER':
            # Ribauntlar paylaşılamaz, negatif korelasyon
            score = 0.70
            tag = "Ribaunt Çakışması"
            
    else:
        # Rakip takımlar
        
        # İki takım skorerinin Sayı Üst olması (Shootout)
        if s1 == 'PTS' and s2 == 'PTS' and out1 == 'OVER' and out2 == 'OVER':
            score = 1.25
            tag = "🔥 Yıldızlar Düellosu"
            
        # İki takım uzunlarının Ribaunt Üst olması
        if s1 in ('REB', 'TRB') and s2 in ('REB', 'TRB') and out1 == 'OVER' and out2 == 'OVER':
            score = 0.80
            tag = "Ribaunt Savaşı"
            conflict = True
            
    return {'score': score, 'tag': tag, 'conflict': conflict}

def build_sgps(preds: List[Dict], max_sgps=5) -> List[Dict]:
    """
    Korelasyon motorunu kullanarak mantıklı Aynı Maç Kombineleri oluşturur.
    """
    valid_preds = [
        p for p in preds
        if p.get('expected_outcome') in ('OVER', 'UNDER') and p.get('line') is not None and p.get('win_prob', 0) >= 60
    ]
    
    # En az 2'li kombineler için kombinasyonları çıkar
    from itertools import combinations
    pairs = list(combinations(valid_preds, 2))
    
    sgps = []
    
    for p1, p2 in pairs:
        corr = calculate_correlation(p1, p2)
        if corr['conflict']:
            continue
            
        # Ana güven skoru kombinelerin olasılığının çarpımıdır
        prob1 = p1['win_prob'] / 100.0
        prob2 = p2['win_prob'] / 100.0
        
        # EV yüksek ise bonus verilebilir
        ev1 = p1.get('ev', 0)
        ev2 = p2.get('ev', 0)
        
        combined_prob = prob1 * prob2
        rating = combined_prob * corr['score'] * 100
        combined_prob_pct = combined_prob * 100
        
        if rating > 30: # En az 30 üzerinden puan alanları ekle
            sgps.append({
                'legs': [p1, p2],
                'title': corr['tag'] if corr['tag'] else 'Standart Kombine',
                'description': f"Sistem Kararı: Bu tahminler birbirini istatistiksel olarak destekliyor (Korelasyon: {corr['score']}x)",
                'rating': round(rating, 2),
                'combined_prob': round(combined_prob_pct, 1),
                'combined_ev': round(ev1 + ev2, 3)
            })
            
    # En iyi rating'e sahip planları seç
    sgps = sorted(sgps, key=lambda x: x['rating'], reverse=True)[:max_sgps]
    return sgps
