package com.nbabahis.app.domain.engine

import java.time.LocalDate
import java.time.temporal.ChronoUnit

data class TravelContext(
    val originCity: String,
    val destinationCity: String,
    val roadTripGameNumber: Int, // 1st away game, 2nd, 3rd, 4th, 5th+
    val daysBetweenGames: Int,
    val targetDate: LocalDate
)

object CircadianTravelEngine {

    private val cityTimezoneOffset = mapOf(
        "Atlanta" to -5,      // EST
        "Boston" to -5,       // EST
        "Brooklyn" to -5,     // EST
        "Charlotte" to -5,    // EST
        "Chicago" to -6,      // CST
        "Cleveland" to -5,    // EST
        "Dallas" to -6,       // CST
        "Denver" to -7,       // MST
        "Detroit" to -5,      // EST
        "Houston" to -6,      // CST
        "Indianapolis" to -5, // EST
        "Los Angeles" to -8,  // PST
        "Memphis" to -6,      // CST
        "Miami" to -5,        // EST
        "Milwaukee" to -6,    // CST
        "Minneapolis" to -6,  // CST
        "New Orleans" to -6,  // CST
        "New York" to -5,     // EST
        "Oklahoma City" to -6,// CST
        "Orlando" to -5,      // EST
        "Philadelphia" to -5, // EST
        "Phoenix" to -7,      // MST
        "Portland" to -8,     // PST
        "Sacramento" to -8,   // PST
        "San Antonio" to -6,  // CST
        "San Francisco" to -8,// PST
        "Seattle" to -8,      // PST
        "Toronto" to -5,      // EST
        "Utah" to -7,         // MST (Salt Lake City)
        "Washington" to -5,   // EST
        // Tricodes
        "BOS" to -5, "BKN" to -5, "NYK" to -5, "PHI" to -5, "TOR" to -5,
        "CHI" to -6, "CLE" to -5, "DET" to -5, "IND" to -5, "MIL" to -6,
        "ATL" to -5, "CHA" to -5, "MIA" to -5, "ORL" to -5, "WAS" to -5,
        "DEN" to -7, "MIN" to -6, "OKC" to -6, "POR" to -8, "UTA" to -7,
        "GSW" to -8, "LAC" to -8, "LAL" to -8, "PHX" to -7, "SAC" to -8,
        "DAL" to -6, "HOU" to -6, "MEM" to -6, "NOP" to -6, "SAS" to -6
    )

    private val cityAltitude = mapOf(
        "Denver" to 5280.0,
        "DEN" to 5280.0,
        "Salt Lake City" to 4226.0,
        "Utah" to 4226.0,
        "UTA" to 4226.0
    )

    private val highAltitudeThreshold = 5000.0 // feet

    fun calculateFatigueModifier(context: TravelContext): Double {
        var modifier = 1.0

        // Jetlag penalty
        val jetlagPenalty = calculateJetlagPenalty(context)
        modifier -= jetlagPenalty

        // Road trip fatigue
        val roadTripFatigue = calculateRoadTripFatigue(context.roadTripGameNumber)
        modifier -= roadTripFatigue

        // Altitude shock
        val altitudePenalty = calculateAltitudePenalty(context)
        modifier -= altitudePenalty

        return modifier.coerceIn(0.75, 1.10)
    }

    fun getFatigueReport(context: TravelContext): String {
        val jetlagPenalty = calculateJetlagPenalty(context)
        val roadTripFatigue = calculateRoadTripFatigue(context.roadTripGameNumber)
        val altitudePenalty = calculateAltitudePenalty(context)

        val originTz = cityTimezoneOffset[context.originCity] ?: -5
        val destTz = cityTimezoneOffset[context.destinationCity] ?: -5
        val tzDelta = destTz - originTz

        val altitudeInfo = if (context.destinationCity in cityAltitude) {
            val altitude = cityAltitude[context.destinationCity] ?: 0.0
            "Altitude: ${context.destinationCity} (${altitude.toInt()} ft)"
        } else {
            "Altitude: Sea level"
        }

        val breakdown = buildList {
            add("Jetlag: ${if (tzDelta > 0) "Eastbound" else "Westbound"} (${if (tzDelta != 0) "${tzDelta.absoluteValue} hour(s)" else "No change"}) → Penalty: ${String.format("%.2f", jetlagPenalty)}")
            add("Road Trip Load: Game ${context.roadTripGameNumber} → Penalty: ${String.format("%.2f", roadTripFatigue)}")
            add(altitudeInfo)
            if (altitudePenalty > 0) {
                add("Altitude Shock Penalty: ${String.format("%.2f", altitudePenalty)}")
            }
        }.joinToString(separator = "\n")

        return buildString {
            append("FATIGUE REPORT\n")
            append("==============\n")
            append("Origin: ${context.originCity} → Destination: ${context.destinationCity}\n")
            append("Days between games: ${context.daysBetweenGames}\n")
            append("Target date: ${context.targetDate}\n")
            append("\n")
            append(breakdown)
            append("\n\n")
            append("Total Fatigue Modifier: ${String.format("%.2f", 1.0 - jetlagPenalty - roadTripFatigue - altitudePenalty)}")
        }
    }

    private fun calculateJetlagPenalty(context: TravelContext): Double {
        val originTz = cityTimezoneOffset[context.originCity] ?: -5
        val destTz = cityTimezoneOffset[context.destinationCity] ?: -5
        val tzDelta = destTz - originTz

        return when {
            tzDelta == 0 -> 0.0
            tzDelta > 0 -> (tzDelta * 0.02).coerceAtMost(0.06) // Eastbound: -2% per hour, max -6%
            else -> (tzDelta.absoluteValue * 0.01).coerceAtMost(0.03) // Westbound: -1% per hour, max -3%
        }
    }

    private fun calculateRoadTripFatigue(gameNumber: Int): Double {
        return when (gameNumber) {
            1 -> 0.00
            2 -> 0.02
            3 -> 0.045
            else -> 0.07
        }
    }

    private fun calculateAltitudePenalty(context: TravelContext): Double {
        val destAltitude = cityAltitude[context.destinationCity] ?: 0.0
        val originAltitude = cityAltitude[context.originCity] ?: 0.0

        // Only apply if destination is high altitude and origin is not
        if (destAltitude < highAltitudeThreshold || originAltitude >= highAltitudeThreshold) {
            return 0.0
        }

        // Days spent in destination (approximate: daysBetweenGames - 1, but assume arrival day + game day)
        val daysInDestination = context.daysBetweenGames.coerceAtLeast(0)

        return when {
            daysInDestination < 1 -> 0.05 // <24h = severe shock
            daysInDestination <= 2 -> 0.02 // 2-3 days = partial acclimatization
            else -> 0.0 // >3 days = fully acclimatized
        }
    }

    private val Int.absoluteValue: Int get() = if (this < 0) -this else this
}
