import json
import re
from datetime import datetime, timedelta
from typing import Dict, Optional

from DrissionPage import ChromiumPage, ChromiumOptions

from app.core.config import STAT_TO_ODDS_MARKET, log
from app.core.state import _odds_lock, _odds_cache, _odds_cache_time
from app.core.utils import _norm_name

STAKE_TO_MARKET = {
    'Player Points': 'player_points',
    'Player Rebounds': 'player_rebounds',
    'Player Assists': 'player_assists',
    'Player Points + Rebounds + Assists': 'player_points_rebounds_assists',
    'Player Points + Rebounds': 'player_points_rebounds',
    'Player Points + Assists': 'player_points_assists',
    'Player Rebounds + Assists': 'player_rebounds_assists',
    'Player Threes': 'player_threes',
    'Player Blocks': 'player_blocks',
    'Player Steals': 'player_steals',
    'Player Blocks + Steals': 'player_blocks_steals',
    'Player Turnovers': 'player_turnovers'
}

class StakeAPIClient:
    def __init__(self, headless: bool = False):
        self.headless = headless
        self.page = None
        
    def __enter__(self):
        self.start()
        return self
        
    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()

    def start(self):
        if not self.page:
            import os
            profile_dir = os.path.join(os.getcwd(), 'stake_browser_profile')
            
            co = ChromiumOptions()
            if self.headless:
                co.headless()
            co.set_argument('--start-maximized')
            co.set_argument('--log-level=3')
            # Kalici profil (oturum/cookie kaydetmek icin)
            co.set_user_data_path(profile_dir)
            
            self.page = ChromiumPage(addr_or_opts=co)
            log.info("Stake.com (NBA) DrissionPage ile açılıyor...")
            
            # Guvenlik veya Ana Sayfa
            try:
                self.page.get("https://stake.com/sports/basketball/usa/nba", timeout=30)
            except Exception as e:
                log.warning(f"Stake initial load timeout/error: {e}")
            
            log.info("Stake.com (NBA) ana sayfasının tam yüklenmesi bekleniyor...")
            import time
            
            wait_start = time.time()
            while "moment" in self.page.title.lower() or "cloudflare" in self.page.title.lower():
                if time.time() - wait_start > 60:
                    log.warning("Cloudflare 60 saniyede geçilemedi! Lütfen tarayıcıdaki onay kutusunu kontrol edin.")
                    break
                time.sleep(1)
                
            time.sleep(5) # Sayfadaki asıl basketbol verilerinin (SPA) dolması için küçük bir pay

    def close(self):
        if self.page:
            self.page.quit()
            
    def _execute_graphql(self, query: str, variables: dict) -> dict:
        if not self.page:
            self.start()
            
        script = f"""
        return new Promise(function(resolve, reject) {{
            var xhr = new XMLHttpRequest();
            xhr.open('POST', '/_api/graphql', true);
            xhr.setRequestHeader('Content-Type', 'application/json');
            xhr.setRequestHeader('Accept', 'application/json');
            xhr.onload = function() {{
                if (xhr.status >= 200 && xhr.status < 300) {{
                    try {{ resolve(JSON.parse(xhr.responseText)); }}
                    catch(e) {{ reject('JSON parse error: ' + e.toString()); }}
                }} else {{
                    reject('HTTP Error: ' + xhr.status + ' ' + xhr.responseText);
                }}
            }};
            xhr.onerror = function() {{ reject('XHR Network Error (Fetch Blocked)'); }};
            xhr.send(JSON.stringify({{
                query: {json.dumps(query)},
                variables: {json.dumps(variables)}
            }}));
        }});
        """
        try:
            result = self.page.run_js(script)
            return result
        except Exception as e:
            log.error(f"Stake DrissionPage API error: {e}")
            return {}

    def fetch_fixtures(self) -> list:
        query = """
        query SportsTournamentPage($sport: String!, $category: String!, $tournament: String!) {
          slugTournament(sport: $sport, category: $category, tournament: $tournament) {
            id
            name
            fixtureList(limit: 15) {
              id
              name
              slug
              status
            }
          }
        }
        """
        data = self._execute_graphql(query, {"sport": "basketball", "category": "usa", "tournament": "nba"})
        if not data:
            return []
            
        fixtures = []
        slug_tournament = data.get("data", {}).get("slugTournament")
        if slug_tournament:
            for fx in slug_tournament.get("fixtureList", []):
                # Only active/upcoming games
                if fx.get("status") in ["upcoming", "started", "active"]:
                    fixtures.append(fx.get("slug"))
        return fixtures
    def fetch_markets_for_fixture(self, fixture_slug: str) -> dict:
        query = """query FixtureIndex($fixture: String!, $groups: [String!]!) {
  slugFixture(fixture: $fixture) {
    ...SportFixtureView
    groups {
      id
      ...SportGroup
    }
    maps: groups(groups: ["maps"]) {
      id
      ...SportGroup
      templates(includeEmpty: false) {
        id
        extId
        markets {
          status
          specifiers
          extId
        }
      }
    }
    ...UfcFrontRowSeat
    group: groups(groups: $groups) {
      ...SportGroup
      templates(includeEmpty: false) {
        id
        ...SportGroupTemplate
        markets {
          ...SportMarket
          outcomes {
            ...SportMarketOutcome
            extId
          }
        }
      }
    }
  }
}

fragment SportFixtureView on SportFixture {
  ...SportFixtureLiveStreamExists
  id
  slug
  extId
  status
  name
  provider
  widgetUrl
  liveWidgetUrl
  customBetAvailable
  swishGame {
    id
    status
    swishSportId
  }
  eventStatus {
    ...SportFixtureEventStatus
    ...EsportFixtureEventStatus
    __typename
  }
  data {
    ...SportFixtureDataMatch
    ...SportFixtureDataOutright
    __typename
  }
  contentNotes {
    ...ContentNote
  }
  tournament {
    id
    name
    slug
    contentNotes {
      ...ContentNote
    }
    category {
      id
      name
      slug
      contentNotes {
        ...ContentNote
      }
      sport {
        id
        name
        slug
        contentNotes {
          ...ContentNote
        }
      }
    }
  }
}

fragment SportFixtureLiveStreamExists on SportFixture {
  id
  betradarStream {
    exists
  }
  imgArenaStream {
    exists
  }
  abiosStream {
    exists
    stream {
      startTime
      id
    }
  }
  geniussportsStream(deliveryType: hls) {
    exists
  }
  statsPerformStream(getData: false) {
    isAvailable
    geoBlocked
  }
  liveStream {
    data {
      isAvailable
    }
  }
}

fragment SportFixtureEventStatus on SportFixtureEventStatusData {
  __typename
  homeScore
  awayScore
  matchStatus
  clock {
    matchTime
    remainingTime
  }
  periodScores {
    homeScore
    awayScore
    matchStatus
  }
  currentTeamServing
  homeGameScore
  awayGameScore
  statistic {
    yellowCards {
      away
      home
    }
    redCards {
      away
      home
    }
    corners {
      home
      away
    }
  }
}

fragment EsportFixtureEventStatus on EsportFixtureEventStatus {
  matchStatus
  homeScore
  awayScore
  scoreboard {
    homeGold
    awayGold
    homeGoals
    awayGoals
    homeKills
    awayKills
    gameTime
    homeDestroyedTowers
    awayDestroyedTurrets
    currentRound
    currentCtTeam
    currentDefTeam
    time
    awayWonRounds
    homeWonRounds
    remainingGameTime
  }
  periodScores {
    type
    number
    awayGoals
    awayKills
    awayScore
    homeGoals
    homeKills
    homeScore
    awayWonRounds
    homeWonRounds
    matchStatus
  }
  __typename
}

fragment SportFixtureDataMatch on SportFixtureDataMatch {
  startTime
  competitors {
    ...SportFixtureCompetitor
  }
  teams {
    name
    qualifier
  }
  tvChannels {
    language
    name
    streamUrl
  }
  __typename
}

fragment SportFixtureCompetitor on SportFixtureCompetitor {
  name
  defaultName
  extId
  countryCode
  abbreviation
  iconPath
}

fragment SportFixtureDataOutright on SportFixtureDataOutright {
  name
  startTime
  endTime
  __typename
}

fragment ContentNote on ContentNote {
  id
  createdAt
  publishAt
  expireAt
  linkText
  linkUrl
  message
  publishAt
  locale
  ref {
    ... on Sport {
      id
      name
    }
    ... on SportCategory {
      id
      name
      sport {
        name
      }
    }
    ... on SportTournament {
      id
      name
      category {
        name
        sport {
          name
        }
      }
    }
    ... on SportFixture {
      id
      name
      provider
      tournament {
        name
        category {
          name
          sport {
            name
          }
        }
      }
    }
  }
}

fragment SportGroup on SportGroup {
  name
  translation
  rank
}

fragment UfcFrontRowSeat on SportFixture {
  frontRowSeatFight {
    fightId
  }
  tournament {
    frontRowSeatEvent {
      identifier
    }
  }
}

fragment SportGroupTemplate on SportGroupTemplate {
  extId
  rank
  name
}

fragment SportMarket on SportMarket {
  id
  name
  status
  extId
  specifiers
  customBetAvailable
  provider
}

fragment SportMarketOutcome on SportMarketOutcome {
  __typename
  id
  active
  odds
  name
  customBetAvailable
}"""
        
        target_groups = [["customPlayerProps"], ["player_props"], ["playerProps"]]
        
        for group in target_groups:
            # v13.0: Robust GraphQL Retry
            retries = 2
            while retries > 0:
                variables = {"fixture": fixture_slug, "groups": group}
                data = self._execute_graphql(query, variables)
                
                # v13.1 Safe Access Check
                if not data:
                    retries -= 1
                    import time; time.sleep(0.5)
                    continue
                    
                sf = data.get("data", {}).get("slugFixture")
                if sf and sf.get("group"):
                    return sf
                    
                retries -= 1
                import time; time.sleep(0.5)
                
        return {}

    def get_player_props(self) -> Dict:
        """ Fetch all prop bets across all NBA fixtures using DrissionPage """
        import re
             
        cache_key = "stake_all_props"
        with _odds_lock:
            if cache_key in _odds_cache:
                 if datetime.now() - _odds_cache_time.get(cache_key, datetime.min) < timedelta(minutes=15):
                     return _odds_cache[cache_key]
                     
        result = {}
        
        try:
            self.start()
            
            fixtures = self.fetch_fixtures()
            if not fixtures:
                log.warning("Stake.com'da güncel NBA maçı bulunamadı veya ağ bağlantısı başarısız oldu (DrissionPage).")
                return {}
                
            log.info(f"{len(fixtures)} maç bulundu. Oyuncu baremleri çekiliyor (Stake Yeni Şema)...")
            for slug in fixtures:
                fixt_data = self.fetch_markets_for_fixture(slug)
                if not fixt_data:
                    continue
                    
                groups = fixt_data.get("group", [])
                for grp in groups:
                    for tmpl in grp.get("templates", []):
                        for market in tmpl.get("markets", []):
                            market_name = market.get("name", "")
                            
                            internal_mkt = None
                            for k, v in STAKE_TO_MARKET.items():
                                if k.lower() in market_name.lower():
                                    internal_mkt = v
                                    break
                                    
                            if not internal_mkt:
                                continue
                                
                            for sel in market.get("outcomes", []):
                                sel_name = sel.get("name", "")
                                odds = float(sel.get("odds", 0))
                                
                                # Extract points from name (since 'points' field is removed from API)
                                pts = 0.0
                                match = re.search(r'\d+\.?\d*', sel_name)
                                if match:
                                    pts = float(match.group())
                                    
                                if not sel_name or not pts or not odds:
                                    continue
                                    
                                is_over = any(x in sel_name for x in ["Over", "O ", "over", "Üst", "üst"])
                                is_under = any(x in sel_name for x in ["Under", "U ", "under", "Alt", "alt"])
                                
                                if not (is_over or is_under):
                                    continue
                                    
                                # v12.5: Deep Scrubber for Player names
                                # We want to keep characters like " ' " (De'Aaron) and " - " (if part of name)
                                # but remove all bet-related noise.
                                player_raw = f"{market_name} {sel_name}"
                                scrub_patterns = [
                                    r'Player\s+(Points|Rebounds|Assists|Threes|Blocks|Steals|Turnovers)(\s*\+\s*\w+)*',
                                    r'\b(Over|Under|Üst|Alt|Total)\b',
                                    r'\(?[OU]\)?', r'[0-9]+\.?[0-9]*', r'\(\s*\)', r'\s+-\s+'
                                ]
                                for pat in scrub_patterns:
                                    player_raw = re.sub(pat, ' ', player_raw, flags=re.IGNORECASE)
                                    
                                player_raw = player_raw.strip()
                                # Final cleanup: remove trailing/leading dashes or dots
                                player_raw = re.sub(r'^[\s\-_.]+|[\s\-_.]+$', '', player_raw)
                                
                                pname = _norm_name(player_raw)
                                if not pname:
                                    continue
                                    
                                if pname not in result:
                                    result[pname] = {}
                                if internal_mkt not in result[pname]:
                                    result[pname][internal_mkt] = {}
                                    
                                if 'Stake' not in result[pname][internal_mkt]:
                                    result[pname][internal_mkt]['Stake'] = {
                                        'line': pts,
                                        'bookmaker': 'Stake',
                                        'over_odds': 0,
                                        'under_odds': 0
                                    }
                                
                                # Set odds depending on selection type
                                if pts == result[pname][internal_mkt]['Stake']['line']:
                                    if is_over:
                                        result[pname][internal_mkt]['Stake']['over_odds'] = odds
                                    else:
                                        result[pname][internal_mkt]['Stake']['under_odds'] = odds
        finally:
            self.close()

        with _odds_lock:
            _odds_cache[cache_key] = result
            _odds_cache_time[cache_key] = datetime.now()
            
        log.info(f"Stake verisi {len(result)} oyuncu için sisteme eklendi.")
        return result

def get_stake_client() -> StakeAPIClient:
    # DrissionPage ile çalışırken arka planda sessiz çalışabilir veya görsel kontrol edilebilmesi için False ile ayarlanabilir
    return StakeAPIClient(headless=False)
