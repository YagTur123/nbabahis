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
}
