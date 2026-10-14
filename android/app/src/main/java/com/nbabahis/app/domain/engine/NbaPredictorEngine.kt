package com.nbabahis.app.domain.engine

import com.nbabahis.app.data.model.NbaPlayer
import com.nbabahis.app.data.model.PlayerGameLog
import com.nbabahis.app.data.model.TeamStats
import com.nbabahis.app.domain.model.*
import java.time.LocalDate
import java.time.temporal.ChronoUnit
import kotlin.math.abs
import kotlin.math.roundToInt
import kotlin.math.sqrt

object NbaPredictorEngine {

    private const val MIN_GAMES_REQUIRED = 5
    private const val MIN_MINUTES_THRESHOLD = 12.0

    private val FLOORS = mapOf(
        "PTS" to 4.0,
        "REB" to 1.5,
        "AST" to 1.0,
        "3PM" to 0.5,
        "STL" to 0.3,
        "BLK" to 0.2,
        "PRA" to 7.0,
        "P+R" to 6.0,
        "P+A" to 5.5
    )

    fun predictPlayer(
        player: NbaPlayer,
        history: List<PlayerGameLog>,
        teamRoster: List<NbaPlayer>,
        opponentRoster: List<NbaPlayer> = emptyList(),
        teamStats: TeamStats?,
        opponentStats: TeamStats?,
        isHome: Boolean,
        targetDate: LocalDate = LocalDate.now()
    ): PredictionResult? {
        if (history.size < MIN_GAMES_REQUIRED) return null

        if (player.injuryStatus?.contains("OUT", ignoreCase = true) == true) {
            return null
        }

        val avgMinutes = history.map { it.min }.average()
        if (avgMinutes < MIN_MINUTES_THRESHOLD) return null

        val lastGame = history.first()
        val lastDate = try {
            LocalDate.parse(lastGame.gameDate.take(10))
        } catch (_: Exception) {
            targetDate.minusDays(2)
        }
        val restDays = ChronoUnit.DAYS.between(lastDate, targetDate).toInt().coerceAtLeast(0)

        // 1. Dinamik Sirkadiyen Ritim, Saat Dilimi & Deplasman Turu Motoru
        val consecutiveAwayGames = if (!isHome) {
            val count = history.take(5).indexOfFirst { it.matchup.contains("vs.") }
            if (count == -1) 5 else (count + 1)
        } else {
            0
        }

        val lastCity = if (lastGame.matchup.contains("@")) {
            lastGame.matchup.split(" ").lastOrNull()?.trim() ?: player.teamAbbr
        } else {
            player.teamAbbr
        }
        val targetCity = if (isHome) player.teamAbbr else (opponentStats?.teamAbbr ?: "OPP")

        val travelContext = TravelContext(
            originCity = lastCity,
            destinationCity = targetCity,
            roadTripGameNumber = consecutiveAwayGames,
            daysBetweenGames = restDays,
            targetDate = targetDate
        )
        val circadianFatigue = CircadianTravelEngine.calculateFatigueModifier(travelContext)
        val fatigueReport = CircadianTravelEngine.getFatigueReport(travelContext)

        // 2. Dinamik Oyunun Önemi & Bağlam Motoru (Playoff yarışı, Ezeli rekabet, TV)
        val isConferenceOrRival = isConferenceRival(player.teamAbbr, opponentStats?.teamAbbr)
        val stakesContext = GameStakesContext(
            isRivalryOrConferenceGame = isConferenceOrRival,
            isNationalTv = true, // Yıldız maçları
            teamWinPct = if ((teamStats?.avgMargin ?: 0.0) > 0) 0.60 else 0.45,
            opponentWinPct = if ((opponentStats?.avgMargin ?: 0.0) > 0) 0.58 else 0.42,
            gamesRemainingInSeason = 18,
            isReturningFromInjury = player.injuryStatus?.contains("GTD", ignoreCase = true) == true
        )
        val stakesImpact = GameStakesEngine.evaluateGameStakes(player, teamStats, opponentStats, stakesContext)

        // 3. Dinamik Taktiksel Eşleşme & Savunma Şeması (Drop vs Switch vs Blitz & Tempo)
        val tactical = MatchupTacticalEngine.calculateTacticalModifiers(player, teamStats, opponentStats, isHome)

        // 4. Birebir Savunmacı Eşleşmesi (Primary Defender Impact)
        val defenderImpact = PrimaryDefenderEngine.calculateMatchupImpact(
            offensivePlayer = player,
            opponentRoster = opponentRoster,
            opponentAbbr = opponentStats?.teamAbbr ?: "OPP"
        )

        // 5. Dinamik Blowout Riski
        val ownMargin = teamStats?.avgMargin ?: 0.0
        val oppMargin = opponentStats?.avgMargin ?: 0.0
        val marginDiff = abs(ownMargin - oppMargin)
        val blowoutRisk = marginDiff > 11.5
        val blowoutModifier = if (blowoutRisk) {
            if (avgMinutes >= 32.0) 0.88 else if (avgMinutes >= 28.0) 0.93 else 1.04
        } else {
            1.0
        }

        // 6. Sakatlık Kullanım Kayması (Takım arkadaşı yokluğunda şut payı)
        val usageBoost = UsageShiftCalculator.calculateUsageMultiplier(player, teamRoster)

        val statTypes = listOf(
            Triple("PTS", "Sayı", { g: PlayerGameLog -> g.pts }),
            Triple("REB", "Ribaund", { g: PlayerGameLog -> g.reb }),
            Triple("AST", "Asist", { g: PlayerGameLog -> g.ast }),
            Triple("3PM", "3 Sayılık Basket", { g: PlayerGameLog -> g.fg3m }),
            Triple("PRA", "Sayı+Rib+Ast", { g: PlayerGameLog -> g.pra }),
            Triple("P+R", "Sayı+Ribaund", { g: PlayerGameLog -> g.pr }),
            Triple("P+A", "Sayı+Asist", { g: PlayerGameLog -> g.pa }),
            Triple("STL", "Top Çalma", { g: PlayerGameLog -> g.stl }),
            Triple("BLK", "Blok", { g: PlayerGameLog -> g.blk })
        )

        val predictions = statTypes.map { (key, label, extractor) ->
            projectDynamicStat(
                statKey = key,
                displayName = label,
                extractor = extractor,
                history = history,
                player = player,
                isHome = isHome,
                restDays = restDays,
                circadianFatigue = circadianFatigue,
                stakesImpact = stakesImpact,
                tactical = tactical,
                defenderImpact = defenderImpact,
                blowoutModifier = blowoutModifier,
                usageBoost = usageBoost,
                oppStats = opponentStats
            )
        }

        return PredictionResult(
            player = player,
            opponentAbbr = opponentStats?.teamAbbr ?: "OPP",
            isHome = isHome,
            restDays = restDays,
            travelFatigueFactor = circadianFatigue,
            blowoutRisk = blowoutRisk,
            blowoutModifier = blowoutModifier,
            stakesReport = stakesImpact.explanation,
            tacticalReport = tactical.tacticalBreakdown,
            fatigueReport = "Yolculuk Katsayısı: ${(circadianFatigue * 100).toInt()}% · Deplasman Maç #${consecutiveAwayGames}",
            defenderReport = defenderImpact.matchupSummary,
            predictions = predictions
        )
    }

    private fun projectDynamicStat(
        statKey: String,
        displayName: String,
        extractor: (PlayerGameLog) -> Double,
        history: List<PlayerGameLog>,
        player: NbaPlayer,
        isHome: Boolean,
        restDays: Int,
        circadianFatigue: Double,
        stakesImpact: StakesImpact,
        tactical: TacticalModifiers,
        defenderImpact: DefenderMatchupImpact,
        blowoutModifier: Double,
        usageBoost: Double,
        oppStats: TeamStats?
    ): StatPrediction {
        val values = history.map(extractor)
        val seasonAvg = values.average()
        val l5Values = values.take(5)
        val l3Values = values.take(3)
        val l5Avg = if (l5Values.isNotEmpty()) l5Values.average() else seasonAvg
        val l3Avg = if (l3Values.isNotEmpty()) l3Values.average() else seasonAvg

        // 1. Ağırlıklı Hareketli Ortalama (Son form daha baskın)
        var projection = (l3Avg * 0.45) + (l5Avg * 0.35) + (seasonAvg * 0.20)

        // 2. Dinamik Ev / Deplasman Şut Oranları
        val homeSplits = history.filter { it.matchup.contains("vs.") }.map(extractor)
        val awaySplits = history.filter { it.matchup.contains("@") }.map(extractor)
        if (isHome && homeSplits.isNotEmpty() && seasonAvg > 0) {
            val homeRatio = (homeSplits.average() / seasonAvg).coerceIn(0.92, 1.12)
            projection *= homeRatio
        } else if (!isHome && awaySplits.isNotEmpty() && seasonAvg > 0) {
            val awayRatio = (awaySplits.average() / seasonAvg).coerceIn(0.88, 1.08)
            projection *= awayRatio
        }

        // 3. Sirkadiyen Ritim, Jetlag ve Şehir Yorgunluğu
        projection *= circadianFatigue

        // 4. Oyunun Önemi & Dakika Dağılımı Çarpanı
        projection *= stakesImpact.projectedMinutesModifier

        // İstatistiğe göre taktiksel ve bağlamsal yoğunluk
        when (statKey) {
            "PTS" -> {
                projection *= stakesImpact.scoringIntensityModifier
                projection *= tactical.ptsModifier
                projection *= defenderImpact.ptsModifier
            }
            "3PM" -> {
                projection *= stakesImpact.scoringIntensityModifier
                projection *= tactical.threesModifier
                projection *= defenderImpact.fg3mModifier
            }
            "AST" -> {
                projection *= tactical.astModifier
            }
            "REB" -> {
                projection *= tactical.rebModifier
            }
            "PRA" -> {
                projection *= ((tactical.ptsModifier + tactical.rebModifier + tactical.astModifier) / 3.0)
                projection *= ((defenderImpact.ptsModifier * 2 + 1.0) / 3.0)
            }
            "P+R" -> {
                projection *= ((tactical.ptsModifier + tactical.rebModifier) / 2.0)
                projection *= ((defenderImpact.ptsModifier + 1.0) / 2.0)
            }
            "P+A" -> {
                projection *= ((tactical.ptsModifier + tactical.astModifier) / 2.0)
                projection *= ((defenderImpact.ptsModifier + 1.0) / 2.0)
            }
            "STL" -> {
                projection *= tactical.tovModifier
                projection *= (defenderImpact.primaryDefender.stealRate / 1.0).coerceIn(0.9, 1.15)
            }
            "BLK" -> {
                projection *= (defenderImpact.primaryDefender.blockRate / 0.8).coerceIn(0.85, 1.20)
            }
        }

        // 5. Dinamik Maç Temposu (Possessions Çarpanı)
        projection *= tactical.paceMultiplier

        // 6. Blowout ve Kullanım Kayması
        projection *= blowoutModifier
        projection *= usageBoost

        // 7. Pozisyon Bazlı Rakip Savunma Etkisi (DvP)
        val isGuard = player.position.contains("G", ignoreCase = true)
        val isCenter = player.position.contains("C", ignoreCase = true)
        if (statKey == "REB" && isCenter && oppStats != null) {
            val rebRatio = (oppStats.oppReb / 43.5).coerceIn(0.88, 1.15)
            projection *= rebRatio
        }

        val floorVal = FLOORS[statKey] ?: 0.5
        projection = projection.coerceAtLeast(floorVal)

        // Trend analizi
        val pctDiff = if (seasonAvg > 0) ((l5Avg - seasonAvg) / seasonAvg) * 100.0 else 0.0
        val trendType = when {
            pctDiff >= 20.0 -> TrendType.HOT
            pctDiff >= 10.0 -> TrendType.WARM
            pctDiff <= -20.0 -> TrendType.COLD
            pctDiff <= -10.0 -> TrendType.COOLING
            else -> TrendType.NEUTRAL
        }

        // Standart Sapma ve Güven Skoru
        val variance = values.map { (it - seasonAvg) * (it - seasonAvg) }.average()
        val stdDev = sqrt(variance)
        val cv = if (seasonAvg > 0) stdDev / seasonAvg else 1.0
        val confidenceScore = ((1.0 - (cv * 0.45).coerceIn(0.0, 0.6)) * 100).roundToInt().coerceIn(45, 96)

        // Poisson & Normal Gauss CDF Alt/Üst Olasılıkları
        val thresholds = ProbabilityEngine.getProbableThresholds(
            statKey = statKey,
            projection = (projection * 10.0).roundToInt() / 10.0,
            stdDev = if (stdDev > 0) stdDev else 2.0
        )

        return StatPrediction(
            statKey = statKey,
            displayName = displayName,
            predictedValue = (projection * 10.0).roundToInt() / 10.0,
            seasonAvg = (seasonAvg * 10.0).roundToInt() / 10.0,
            l5Avg = (l5Avg * 10.0).roundToInt() / 10.0,
            l3Avg = (l3Avg * 10.0).roundToInt() / 10.0,
            diffFromSeason = ((projection - seasonAvg) * 10.0).roundToInt() / 10.0,
            trend = Trend(trendType, (pctDiff * 10.0).roundToInt() / 10.0),
            confidence = confidenceScore,
            thresholds = thresholds
        )
    }

    private fun isConferenceRival(team1: String?, team2: String?): Boolean {
        if (team1 == null || team2 == null) return false
        val west = setOf("LAL", "GSW", "LAC", "PHX", "SAC", "DEN", "MIN", "OKC", "POR", "UTA", "DAL", "HOU", "MEM", "NOP", "SAS")
        val east = setOf("BOS", "BKN", "NYK", "PHI", "TOR", "CHI", "CLE", "DET", "IND", "MIL", "ATL", "CHA", "MIA", "ORL", "WAS")
        return (team1 in west && team2 in west) || (team1 in east && team2 in east)
    }
}
