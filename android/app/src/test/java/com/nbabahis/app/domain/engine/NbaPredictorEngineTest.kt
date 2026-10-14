package com.nbabahis.app.domain.engine

import com.nbabahis.app.data.model.NbaPlayer
import com.nbabahis.app.data.model.PlayerGameLog
import com.nbabahis.app.data.model.TeamStats
import org.junit.Assert.*
import org.junit.Test
import java.time.LocalDate

class NbaPredictorEngineTest {

    private fun createSampleHistory(basePts: Double, baseReb: Double, baseAst: Double): List<PlayerGameLog> {
        val list = mutableListOf<PlayerGameLog>()
        for (i in 1..8) {
            list.add(
                PlayerGameLog(
                    gameId = "00$i",
                    gameDate = LocalDate.now().minusDays((i * 2).toLong()).toString(),
                    matchup = if (i % 2 == 0) "LAL vs. GSW" else "LAL @ GSW",
                    min = 34.0,
                    pts = basePts + (i % 3),
                    reb = baseReb + (i % 2),
                    ast = baseAst + (i % 2)
                )
            )
        }
        return list
    }

    @Test
    fun testDenverAltitudeFatigue() {
        val player = NbaPlayer(playerId = 2544, name = "LeBron James", teamAbbr = "LAL", position = "F")
        val history = createSampleHistory(26.0, 7.0, 8.0)
        val teamRoster = listOf(player)
        val teamStats = TeamStats(teamAbbr = "LAL", defRating = 114.0, pace = 100.0)
        val opponentStats = TeamStats(teamAbbr = "DEN", defRating = 112.0, pace = 96.0)

        val result = NbaPredictorEngine.predictPlayer(
            player = player,
            history = history,
            teamRoster = teamRoster,
            teamStats = teamStats,
            opponentStats = opponentStats,
            isHome = false,
            targetDate = LocalDate.now()
        )

        assertNotNull("Tahmin sonucu null olmamalıdır", result)
        assertTrue("Yüksek irtifa (Denver) deplasmanında yorgunluk cezası uygulanmalıdır", result!!.travelFatigueFactor < 1.0)
    }

    @Test
    fun testBackToBackPenalty() {
        val player = NbaPlayer(playerId = 201939, name = "Stephen Curry", teamAbbr = "GSW", position = "G")
        val historyB2B = mutableListOf<PlayerGameLog>()
        // Son maç dün oynandı (B2B)
        historyB2B.add(PlayerGameLog(gameId = "1", gameDate = LocalDate.now().minusDays(1).toString(), min = 35.0, pts = 28.0, reb = 5.0, ast = 5.0))
        for (i in 2..7) {
            historyB2B.add(PlayerGameLog(gameId = "$i", gameDate = LocalDate.now().minusDays((i * 2).toLong()).toString(), min = 34.0, pts = 27.0, reb = 5.0, ast = 5.0))
        }

        val result = NbaPredictorEngine.predictPlayer(
            player = player,
            history = historyB2B,
            teamRoster = listOf(player),
            teamStats = TeamStats(teamAbbr = "GSW"),
            opponentStats = TeamStats(teamAbbr = "LAL"),
            isHome = true,
            targetDate = LocalDate.now()
        )

        assertNotNull(result)
        assertEquals("B2B durumunda dinlenme günü 1 gün olmalıdır", 1, result!!.restDays)
    }

    @Test
    fun testStatProjections() {
        val player = NbaPlayer(playerId = 203999, name = "Nikola Jokic", teamAbbr = "DEN", position = "C")
        val history = createSampleHistory(27.0, 12.0, 9.0)

        val result = NbaPredictorEngine.predictPlayer(
            player = player,
            history = history,
            teamRoster = listOf(player),
            teamStats = TeamStats(teamAbbr = "DEN"),
            opponentStats = TeamStats(teamAbbr = "BOS"),
            isHome = true,
            targetDate = LocalDate.now()
        )

        assertNotNull(result)
        val ptsPred = result!!.predictions.firstOrNull { it.statKey == "PTS" }
        val rebPred = result.predictions.firstOrNull { it.statKey == "REB" }
        val astPred = result.predictions.firstOrNull { it.statKey == "AST" }

        assertNotNull("Sayı tahmini mevcut olmalıdır", ptsPred)
        assertNotNull("Ribaund tahmini mevcut olmalıdır", rebPred)
        assertNotNull("Asist tahmini mevcut olmalıdır", astPred)

        assertTrue(ptsPred!!.predictedValue > 0.0)
        assertTrue(rebPred!!.predictedValue > 0.0)
        assertTrue(astPred!!.predictedValue > 0.0)
    }

    @Test
    fun testDynamicTacticalAndStakesImpact() {
        val player = NbaPlayer(playerId = 1629029, name = "Luka Doncic", teamAbbr = "DAL", position = "PG")
        val history = createSampleHistory(33.0, 9.0, 10.0)

        val result = NbaPredictorEngine.predictPlayer(
            player = player,
            history = history,
            teamRoster = listOf(player),
            teamStats = TeamStats(teamAbbr = "DAL", pace = 101.0, avgMargin = 3.5),
            opponentStats = TeamStats(teamAbbr = "MIA", pace = 96.0, avgMargin = 1.8), // Miami uses BLITZ/TRAP
            isHome = true,
            targetDate = LocalDate.now()
        )

        assertNotNull(result)
        assertTrue("Taktiksel rapor boş olmamalıdır", result!!.tacticalReport.isNotEmpty())
        assertTrue("Oyun önemi raporu boş olmamalıdır", result.stakesReport.isNotEmpty())
        assertTrue("Yolculuk raporu boş olmamalıdır", result.fatigueReport.isNotEmpty())
    }

    @Test
    fun testPrimaryDefenderImpact() {
        val player = NbaPlayer(playerId = 201939, name = "Stephen Curry", teamAbbr = "GSW", position = "G")
        val history = createSampleHistory(28.0, 5.0, 5.0)

        // Rakip Celtics kadrosunda elit savunmacı Derrick White var
        val opponentRoster = listOf(
            NbaPlayer(playerId = 1628401, name = "Derrick White", teamAbbr = "BOS", position = "G"),
            NbaPlayer(playerId = 1628369, name = "Jayson Tatum", teamAbbr = "BOS", position = "F")
        )

        val result = NbaPredictorEngine.predictPlayer(
            player = player,
            history = history,
            teamRoster = listOf(player),
            opponentRoster = opponentRoster,
            teamStats = TeamStats(teamAbbr = "GSW"),
            opponentStats = TeamStats(teamAbbr = "BOS", defRating = 110.0),
            isHome = false,
            targetDate = LocalDate.now()
        )

        assertNotNull(result)
        assertTrue("Savunmacı raporu Derrick White'ı içermelidir", result!!.defenderReport.contains("Derrick White"))
    }

    @Test
    fun testBacktestTrackerEvaluation() {
        val player = NbaPlayer(playerId = 203999, name = "Nikola Jokic", teamAbbr = "DEN", position = "C")
        val history = createSampleHistory(26.0, 12.0, 9.0)

        val pred = NbaPredictorEngine.predictPlayer(
            player = player,
            history = history,
            teamRoster = listOf(player),
            teamStats = TeamStats(teamAbbr = "DEN"),
            opponentStats = TeamStats(teamAbbr = "LAL"),
            isHome = true,
            targetDate = LocalDate.now()
        )

        assertNotNull(pred)

        // Gerçekleşen maç skoru: Jokic 27 sayı, 11 ribaund, 10 asist yaptı
        val actual = PlayerGameLog(
            gameId = "test_actual",
            gameDate = LocalDate.now().toString(),
            matchup = "DEN vs. LAL",
            min = 36.0,
            pts = 27.0,
            reb = 11.0,
            ast = 10.0
        )

        val report = BacktestTrackerEngine.evaluateBacktest(
            pastPredictions = listOf(pred!!),
            actualBoxScores = mapOf(player.playerId to actual)
        )

        assertEquals(1, report.evaluatedCount)
        assertTrue("Doğrulama karnesi A veya B olmalıdır", report.accuracyGrade in listOf("A+", "A", "B+", "B"))
        assertTrue("PTS için MAE hesaplanmalıdır", report.metricsByStat.containsKey("PTS"))
        assertTrue("Kasa baremleri isabet oranı sıfırdan büyük veya eşit olmalıdır", report.eliteSafeHitRatePct >= 0.0)
    }

    @Test
    fun testHalftimeLiveProjection() {
        val player = NbaPlayer(playerId = 1629029, name = "Luka Doncic", teamAbbr = "DAL", position = "G")
        val history = createSampleHistory(32.0, 9.0, 10.0)

        val pregame = NbaPredictorEngine.predictPlayer(
            player = player,
            history = history,
            teamRoster = listOf(player),
            teamStats = TeamStats(teamAbbr = "DAL"),
            opponentStats = TeamStats(teamAbbr = "GSW"),
            isHome = true
        )
        assertNotNull(pregame)

        val h1Box = HalftimeBoxScore(
            h1Pts = 18.0,
            h1Reb = 5.0,
            h1Ast = 6.0,
            h1Threes = 2.0,
            h1Min = 19.0,
            fouls = 3, // Erken faul problemi
            marginAtHalf = 6.0
        )

        val liveResult = HalftimeLiveEngine.calculateLiveProjection(player, pregame!!, h1Box)
        assertNotNull(liveResult)
        assertNotNull("3 faul alan oyuncuda faul uyarısı bulunmalıdır", liveResult.foulRiskNote)
        assertTrue("Canlı PTS tahmini ilk yarı atılan 18 sayıdan büyük olmalıdır",
            (liveResult.liveStats.firstOrNull { it.statKey == "PTS" }?.totalProjected ?: 0.0) > 18.0)
    }

    @Test
    fun testStandardHalfPointThresholds() {
        val thresholds = ProbabilityEngine.getProbableThresholds("PTS", 24.3, 4.2)
        assertTrue("Baremler boş olmamalıdır", thresholds.isNotEmpty())
        for (t in thresholds) {
            val decimal = t.threshold - t.threshold.toInt()
            assertEquals("Tüm baremler .5 buçuklu standart olmalıdır", 0.5, decimal, 0.001)
        }
    }

    @Test
    fun testEliteSafeFloorThreshold() {
        val player = NbaPlayer(playerId = 1629029, name = "Luka Doncic", teamAbbr = "DAL", position = "G")
        val history = createSampleHistory(32.0, 9.0, 10.0)

        val result = NbaPredictorEngine.predictPlayer(
            player = player,
            history = history,
            teamRoster = listOf(player),
            teamStats = TeamStats(teamAbbr = "DAL"),
            opponentStats = TeamStats(teamAbbr = "GSW"),
            isHome = true
        )

        assertNotNull(result)
        val ptsPred = result!!.predictions.firstOrNull { it.statKey == "PTS" }
        assertNotNull(ptsPred)
        assertNotNull("Luka Doncic için %90+ güvenli kasa baremi bulunmalıdır", ptsPred!!.safeFloorLine)
        assertTrue("%90+ kasa baremi projeksiyondan küçük olmalıdır", ptsPred.safeFloorLine!! < ptsPred.predictedValue)
        assertTrue("%90+ kasa baremi olasılığı en az %88 olmalıdır", ptsPred.safeFloorProb >= 0.88)
    }

    @Test
    fun testProbabilityEngineEliteValue() {
        val thresholds = ProbabilityEngine.getProbableThresholds("PTS", 26.5, 4.5)
        val elite = ProbabilityEngine.getEliteSafeThreshold(thresholds)
        assertNotNull("Elit kasa baremi bulunabilmelidir", elite)
        assertTrue("Elit barem olasılığı >= 0.88 olmalıdır", elite!!.overProb >= 0.88)
        assertTrue("isEliteValue bayrağı true olmalıdır", elite.isEliteValue)
    }
}
