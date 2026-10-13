package com.nbabahis.app.ui.screens.components

import androidx.compose.foundation.BorderStroke
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.*
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.nbabahis.app.domain.model.PredictionResult
import com.nbabahis.app.domain.model.StatPrediction
import com.nbabahis.app.domain.model.TrendType
import com.nbabahis.app.ui.theme.*

@Composable
fun PredictionCard(
    result: PredictionResult,
    filter: String,
    modifier: Modifier = Modifier
) {
    val filteredPredictions = result.predictions.filter {
        when (filter) {
            "ALL" -> true
            "PTS" -> it.statKey == "PTS"
            "REB" -> it.statKey == "REB"
            "AST" -> it.statKey == "AST"
            "3PM" -> it.statKey == "3PM"
            "PRA" -> it.statKey in listOf("PRA", "P+R", "P+A")
            "DEF" -> it.statKey in listOf("STL", "BLK")
            else -> true
        }
    }

    Card(
        modifier = modifier.fillMaxWidth(),
        shape = RoundedCornerShape(16.dp),
        colors = CardDefaults.cardColors(containerColor = CardDark),
        border = BorderStroke(1.dp, CardBorder)
    ) {
        Column(modifier = Modifier.padding(16.dp)) {
            // Header: Player Name + Meta
            Row(
                modifier = Modifier.fillMaxWidth(),
                horizontalArrangement = Arrangement.SpaceBetween,
                verticalAlignment = Alignment.CenterVertically
            ) {
                Column {
                    Text(
                        text = result.player.name,
                        style = MaterialTheme.typography.titleLarge,
                        color = TextPrimary
                    )
                    Row(
                        horizontalArrangement = Arrangement.spacedBy(6.dp),
                        verticalAlignment = Alignment.CenterVertically
                    ) {
                        Text(
                            text = "${result.player.teamAbbr} · ${result.player.position} #${result.player.jerseyNum}",
                            style = MaterialTheme.typography.bodyMedium,
                            color = TextSecondary
                        )
                        val matchLoc = if (result.isHome) "Evinde vs ${result.opponentAbbr}" else "Deplasmanda @ ${result.opponentAbbr}"
                        Text(
                            text = "($matchLoc)",
                            style = MaterialTheme.typography.labelSmall,
                            color = AccentCyan
                        )
                    }
                }

                // Rest & Fatigue badges
                Column(horizontalAlignment = Alignment.End) {
                    if (result.restDays <= 1) {
                        Surface(
                            shape = RoundedCornerShape(6.dp),
                            color = WarningYellow.copy(alpha = 0.2f),
                            border = BorderStroke(1.dp, WarningYellow)
                        ) {
                            Text(
                                text = "B2B / Yorgun",
                                color = WarningYellow,
                                fontSize = 11.sp,
                                modifier = Modifier.padding(horizontal = 6.dp, vertical = 2.dp)
                            )
                        }
                    } else {
                        Text(
                            text = "${result.restDays} Gün Dinlendi",
                            style = MaterialTheme.typography.labelSmall,
                            color = AccentGreen
                        )
                    }

                    if (result.blowoutRisk) {
                        Text(
                            text = "⚠️ Blowout Riski",
                            color = HotRed,
                            fontSize = 11.sp
                        )
                    }
                }
            }

            // Dynamic Context & Tactical Briefing
            if (result.tacticalReport.isNotEmpty() || result.stakesReport.isNotEmpty()) {
                Spacer(modifier = Modifier.height(10.dp))
                Surface(
                    shape = RoundedCornerShape(8.dp),
                    color = SurfaceDark,
                    border = BorderStroke(0.5.dp, CardBorder),
                    modifier = Modifier.fillMaxWidth()
                ) {
                    Column(modifier = Modifier.padding(10.dp)) {
                        if (result.stakesReport.isNotEmpty()) {
                            Text(
                                text = "🎯 ${result.stakesReport}",
                                fontSize = 11.sp,
                                color = AccentGold,
                                lineHeight = 15.sp
                            )
                        }
                        if (result.tacticalReport.isNotEmpty()) {
                            Spacer(modifier = Modifier.height(4.dp))
                            Text(
                                text = "🛡️ ${result.tacticalReport}",
                                fontSize = 11.sp,
                                color = AccentCyan,
                                lineHeight = 15.sp
                            )
                        }
                        if (result.defenderReport.isNotEmpty()) {
                            Spacer(modifier = Modifier.height(4.dp))
                            Text(
                                text = "🔒 ${result.defenderReport}",
                                fontSize = 11.sp,
                                color = AccentGreen,
                                lineHeight = 15.sp
                            )
                        }
                        if (result.fatigueReport.isNotEmpty()) {
                            Spacer(modifier = Modifier.height(4.dp))
                            Text(
                                text = "✈️ ${result.fatigueReport}",
                                fontSize = 10.sp,
                                color = TextMuted
                            )
                        }
                    }
                }
            }

            Spacer(modifier = Modifier.height(14.dp))

            // Predictions Grid / List
            Column(verticalArrangement = Arrangement.spacedBy(10.dp)) {
                filteredPredictions.forEach { pred ->
                    StatRow(pred = pred)
                }
            }
        }
    }
}

@Composable
private fun StatRow(pred: StatPrediction) {
    Surface(
        shape = RoundedCornerShape(10.dp),
        color = SurfaceDark,
        border = BorderStroke(1.dp, CardBorder)
    ) {
        Row(
            modifier = Modifier
                .fillMaxWidth()
                .padding(12.dp),
            verticalAlignment = Alignment.CenterVertically,
            horizontalArrangement = Arrangement.SpaceBetween
        ) {
            // Stat Title & Trend
            Column(modifier = Modifier.weight(1.2f)) {
                Row(verticalAlignment = Alignment.CenterVertically) {
                    Text(
                        text = pred.displayName,
                        style = MaterialTheme.typography.titleMedium,
                        color = TextPrimary
                    )
                    Spacer(modifier = Modifier.width(6.dp))
                    if (pred.trend.type != TrendType.NEUTRAL) {
                        Text(
                            text = "${pred.trend.type.emoji} ${pred.trend.type.label}",
                            fontSize = 11.sp,
                            color = if (pred.trend.type == TrendType.HOT || pred.trend.type == TrendType.WARM) HotRed else ColdBlue
                        )
                    }
                }

                Text(
                    text = "Sezon: ${pred.seasonAvg} · Son 5: ${pred.l5Avg}",
                    style = MaterialTheme.typography.labelSmall,
                    color = TextMuted
                )
            }

            // Confidence Score
            Column(
                horizontalAlignment = Alignment.CenterHorizontally,
                modifier = Modifier.weight(0.9f)
            ) {
                Text(
                    text = "%${pred.confidence} Güven",
                    fontSize = 11.sp,
                    color = AccentGreen,
                    fontWeight = FontWeight.SemiBold
                )
                LinearProgressIndicator(
                    progress = { (pred.confidence / 100f).coerceIn(0f, 1f) },
                    modifier = Modifier
                        .width(60.dp)
                        .height(4.dp)
                        .clip(RoundedCornerShape(2.dp)),
                    color = AccentGreen,
                    trackColor = CardBorder,
                )
            }

            // Projected Value & Diff
            Column(
                horizontalAlignment = Alignment.End,
                modifier = Modifier.weight(0.9f)
            ) {
                Text(
                    text = "${pred.predictedValue}",
                    fontSize = 20.sp,
                    fontFamily = FontFamily.Monospace,
                    fontWeight = FontWeight.Bold,
                    color = AccentCyan
                )

                val diffColor = if (pred.diffFromSeason > 0) AccentGreen else if (pred.diffFromSeason < 0) HotRed else TextMuted
                val diffSign = if (pred.diffFromSeason > 0) "+" else ""
                Text(
                    text = "$diffSign${pred.diffFromSeason} ort.",
                    fontSize = 11.sp,
                    fontFamily = FontFamily.Monospace,
                    color = diffColor
                )
            }
        }

        // High probability threshold badges
        val topThresholds = pred.thresholds.filter { it.isHighValue || (it.overProb in 0.52..0.85) }.take(3)
        if (topThresholds.isNotEmpty()) {
            HorizontalDivider(color = CardBorder, thickness = 0.5.dp)
            Row(
                modifier = Modifier
                    .fillMaxWidth()
                    .padding(horizontal = 12.dp, vertical = 6.dp),
                horizontalArrangement = Arrangement.spacedBy(8.dp)
            ) {
                topThresholds.forEach { t ->
                    val pct = (t.overProb * 100).toInt()
                    Surface(
                        shape = RoundedCornerShape(4.dp),
                        color = CardDark,
                        border = BorderStroke(0.5.dp, if (t.isHighValue) AccentGreen else CardBorder)
                    ) {
                        Text(
                            text = "${t.threshold}+ Üst: %$pct",
                            fontSize = 10.sp,
                            fontFamily = FontFamily.Monospace,
                            color = if (t.isHighValue) AccentGreen else TextSecondary,
                            modifier = Modifier.padding(horizontal = 6.dp, vertical = 2.dp)
                        )
                    }
                }
            }
        }
    }
}
