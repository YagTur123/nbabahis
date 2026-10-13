package com.nbabahis.app.domain.engine

import com.nbabahis.app.data.model.PlayerGameLog
import java.time.LocalDate
import java.time.temporal.ChronoUnit
import kotlin.math.*

object TravelFatigueCalculator {

    data class Arena(val lat: Double, val lon: Double, val altFt: Int)

    val NBA_ARENAS = mapOf(
        "ATL" to Arena(33.7573, -84.3963, 1050),
        "BOS" to Arena(42.3662, -71.0621, 15),
        "BKN" to Arena(40.6826, -73.9754, 20),
        "CHA" to Arena(35.2251, -80.8392, 761),
        "CHI" to Arena(41.8807, -87.6742, 597),
        "CLE" to Arena(41.4965, -81.6881, 653),
        "DAL" to Arena(32.7905, -96.8103, 430),
        "DEN" to Arena(39.7486, -105.0075, 5280), // High altitude
        "DET" to Arena(42.3411, -83.0550, 600),
        "GSW" to Arena(37.7680, -122.3877, 16),
        "HOU" to Arena(29.7508, -95.3621, 50),
        "IND" to Arena(39.7640, -86.1555, 715),
        "LAC" to Arena(34.0430, -118.2673, 230),
        "LAL" to Arena(34.0430, -118.2673, 230),
        "MEM" to Arena(35.1381, -90.0506, 331),
        "MIA" to Arena(25.7814, -80.1870, 10),
        "MIL" to Arena(43.0451, -87.9172, 593),
        "MIN" to Arena(44.9795, -93.2761, 830),
        "NOP" to Arena(29.9490, -90.0821, -2),
        "NYK" to Arena(40.7505, -73.9934, 33),
        "OKC" to Arena(35.4634, -97.5151, 1200),
        "ORL" to Arena(28.5392, -81.3839, 82),
        "PHI" to Arena(39.9012, -75.1720, 12),
        "PHX" to Arena(33.4457, -112.0712, 1086),
        "POR" to Arena(45.5316, -122.6668, 50),
        "SAC" to Arena(38.5802, -121.4997, 30),
        "SAS" to Arena(29.4270, -98.4375, 650),
        "TOR" to Arena(43.6435, -79.3791, 246),
        "UTA" to Arena(40.7683, -111.9011, 4226), // High altitude
        "WAS" to Arena(38.8981, -77.0209, 23)
    )

    private fun haversine(lat1: Double, lon1: Double, lat2: Double, lon2: Double): Double {
        val r = 3958.8 // miles
        val dLat = Math.toRadians(lat2 - lat1)
        val dLon = Math.toRadians(lon2 - lon1)
        val a = sin(dLat / 2).pow(2) +
                cos(Math.toRadians(lat1)) * cos(Math.toRadians(lat2)) *
                sin(dLon / 2).pow(2)
        val c = 2 * atan2(sqrt(a), sqrt(1 - a))
        return r * c
    }

    fun calculateFatigue(
        teamAbbr: String,
        isHome: Boolean,
        oppAbbr: String,
        history: List<PlayerGameLog>,
        targetDate: LocalDate
    ): Double {
        if (history.isEmpty()) return 1.0

        val lastGame = history.first() // assumes sorted newest first
        val lastGameDate = try {
            LocalDate.parse(lastGame.gameDate.take(10))
        } catch (_: Exception) {
            targetDate.minusDays(2)
        }

        val restDays = ChronoUnit.DAYS.between(lastGameDate, targetDate).toInt().coerceAtLeast(0)

        // Previous game location
        val wasHomeLast = lastGame.matchup.contains("vs.")
        val lastCity = if (wasHomeLast) teamAbbr else {
            val parts = lastGame.matchup.split(" ")
            parts.lastOrNull()?.trim() ?: teamAbbr
        }
        val currCity = if (isHome) teamAbbr else oppAbbr

        val arena1 = NBA_ARENAS[lastCity] ?: NBA_ARENAS[teamAbbr] ?: Arena(35.0, -90.0, 500)
        val arena2 = NBA_ARENAS[currCity] ?: NBA_ARENAS[oppAbbr] ?: Arena(35.0, -90.0, 500)

        val distance = haversine(arena1.lat, arena1.lon, arena2.lat, arena2.lon)

        var penalty = 1.0

        // 1. Back to Back
        if (restDays <= 1) {
            penalty -= 0.04
            if (distance > 600) penalty -= 0.02
            if (distance > 1500) penalty -= 0.03
        }

        // 2. Altitude check (Denver / Utah)
        if (arena2.altFt >= 4000 && arena1.altFt < 4000) {
            penalty -= 0.03
            if (restDays <= 1) penalty -= 0.02
        }

        return max(0.85, penalty)
    }
}
