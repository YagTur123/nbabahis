package com.nbabahis.app.ui.screens.components

import androidx.compose.animation.AnimatedVisibility
import androidx.compose.animation.expandVertically
import androidx.compose.animation.fadeIn
import androidx.compose.animation.fadeOut
import androidx.compose.animation.shrinkVertically
import androidx.compose.foundation.BorderStroke
import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.KeyboardArrowDown
import androidx.compose.material.icons.filled.KeyboardArrowUp
import androidx.compose.material.icons.filled.Security
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Brush
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

    var expandedBriefing by remember { mutableStateOf(false) }

    Card(
        modifier = modifier.fillMaxWidth(),
        shape = RoundedCornerShape(18.dp),
        colors = CardDefaults.cardColors(containerColor = CardDark),
        border = BorderStroke(1.dp, CardBorder)
    ) {
        Column(modifier = Modifier.padding(16.dp)) {
            // Header: Team Avatar + Player Info + Rest Badges
            Row(
                modifier = Modifier.fillMaxWidth(),
                horizontalArrangement = Arrangement.SpaceBetween,
                verticalAlignment = Alignment.CenterVertically
            ) {
                Row(
                    verticalAlignment = Alignment.CenterVertically,
                    modifier = Modifier.weight(1f)
                ) {
                    // Team Badge Circle
                    Surface(
                        shape = CircleShape,
                        color = SurfaceDark,
                        border = BorderStroke(1.2.dp, AccentCyan.copy(alpha = 0.6f)),
                        modifier = Modifier.size(44.dp)
                    ) {
                        Box(contentAlignment = Alignment.Center) {
                            Text(
                                text = result.player.teamAbbr,
                                fontWeight = FontWeight.Bold,
                                fontSize = 13.sp,
                                color = AccentCyan
                            )
                        }
                    }

                    Spacer(modifier = Modifier.width(12.dp))

                    Column {
                        Text(
                            text = result.player.name,
                            style = MaterialTheme.typography.titleLarge,
                            fontWeight = FontWeight.Bold,
                            color = TextPrimary
                        )
                        Row(
                            horizontalArrangement = Arrangement.spacedBy(6.dp),
                            verticalAlignment = Alignment.CenterVertically
                        ) {
                            Text(
                                text = "${result.player.position} #${result.player.jerseyNum}",
                                style = MaterialTheme.typography.bodyMedium,
                                color = TextSecondary
                            )
                            Text(text = "•", color = TextMuted)
                            val matchLoc = if (result.isHome) "vs ${result.opponentAbbr} (Ev)" else "@ ${result.opponentAbbr} (Dep)"
                            Text(
                                text = matchLoc,
                                style = MaterialTheme.typography.labelSmall,
                                fontWeight = FontWeight.SemiBold,
                                color = if (result.isHome) AccentGreen else AccentCyan
                            )
                        }
                    }
                }

                // Badges: Rest / Blowout
                Column(horizontalAlignment = Alignment.End) {
                    if (result.restDays <= 1) {
                        Surface(
                            shape = RoundedCornerShape(6.dp),
                            color = WarningYellow.copy(alpha = 0.15f),
                            border = BorderStroke(0.8.dp, WarningYellow)
                        ) {
                            Text(
                                text = "B2B / Yorgun",
                                color = WarningYellow,
                                fontWeight = FontWeight.Bold,
                                fontSize = 10.sp,
                                modifier = Modifier.padding(horizontal = 6.dp, vertical = 2.dp)
                            )
                        }
                    } else {
                        Surface(
                            shape = RoundedCornerShape(6.dp),
                            color = AccentGreen.copy(alpha = 0.12f),
                            border = BorderStroke(0.8.dp, AccentGreen.copy(alpha = 0.5f))
                        ) {
                            Text(
                                text = "${result.restDays} Gün Dinlenme",
                                style = MaterialTheme.typography.labelSmall,
                                color = AccentGreen,
                                fontSize = 10.sp,
                                modifier = Modifier.padding(horizontal = 6.dp, vertical = 2.dp)
                            )
                        }
                    }

                    if (result.blowoutRisk) {
                        Spacer(modifier = Modifier.height(4.dp))
                        Surface(
                            shape = RoundedCornerShape(6.dp),
                            color = HotRed.copy(alpha = 0.15f),
                            border = BorderStroke(0.8.dp, HotRed)
                        ) {
                            Text(
                                text = "⚠️ Blowout Riski",
                                color = HotRed,
                                fontWeight = FontWeight.SemiBold,
                                fontSize = 10.sp,
                                modifier = Modifier.padding(horizontal = 6.dp, vertical = 2.dp)
                            )
                        }
                    }
                }
            }

            // Dynamic Tactical Briefing Accordion
            val hasBriefing = result.tacticalReport.isNotEmpty() || result.stakesReport.isNotEmpty() || result.defenderReport.isNotEmpty() || result.fatigueReport.isNotEmpty()
            if (hasBriefing) {
                Spacer(modifier = Modifier.height(10.dp))
                Surface(
                    shape = RoundedCornerShape(10.dp),
                    color = SurfaceDark,
                    border = BorderStroke(0.6.dp, CardBorder),
                    modifier = Modifier
                        .fillMaxWidth()
                        .clickable { expandedBriefing = !expandedBriefing }
                ) {
                    Column(modifier = Modifier.padding(10.dp)) {
                        Row(
                            modifier = Modifier.fillMaxWidth(),
                            horizontalArrangement = Arrangement.SpaceBetween,
                            verticalAlignment = Alignment.CenterVertically
                        ) {
                            Row(verticalAlignment = Alignment.CenterVertically) {
                                Text(text = "🧠 Taktiksel Maç Analizi", style = MaterialTheme.typography.labelMedium, color = AccentCyan)
                            }
                            Icon(
                                imageVector = if (expandedBriefing) Icons.Default.KeyboardArrowUp else Icons.Default.KeyboardArrowDown,
                                contentDescription = null,
                                tint = TextSecondary,
                                modifier = Modifier.size(18.dp)
                            )
                        }

                        if (result.stakesReport.isNotEmpty()) {
                            Spacer(modifier = Modifier.height(4.dp))
                            Text(
                                text = "🎯 ${result.stakesReport}",
                                fontSize = 11.sp,
                                color = AccentGold,
                                lineHeight = 15.sp
                            )
                        }

                        AnimatedVisibility(
                            visible = expandedBriefing,
                            enter = expandVertically() + fadeIn(),
                            exit = shrinkVertically() + fadeOut()
                        ) {
                            Column {
                                if (result.tacticalReport.isNotEmpty()) {
                                    Spacer(modifier = Modifier.height(6.dp))
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
                }
            }

            Spacer(modifier = Modifier.height(14.dp))

            // Prediction Rows
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
        shape = RoundedCornerShape(12.dp),
        color = SurfaceDark,
        border = BorderStroke(1.dp, CardBorder)
    ) {
        Column(modifier = Modifier.fillMaxWidth()) {
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
                            fontWeight = FontWeight.Bold,
                            color = TextPrimary
                        )
                        Spacer(modifier = Modifier.width(6.dp))
                        if (pred.trend.type != TrendType.NEUTRAL) {
                            Surface(
                                shape = RoundedCornerShape(4.dp),
                                color = if (pred.trend.type == TrendType.HOT || pred.trend.type == TrendType.WARM) HotRed.copy(alpha = 0.15f) else ColdBlue.copy(alpha = 0.15f)
                            ) {
                                Text(
                                    text = "${pred.trend.type.emoji} ${pred.trend.type.label}",
                                    fontSize = 10.sp,
                                    fontWeight = FontWeight.SemiBold,
                                    color = if (pred.trend.type == TrendType.HOT || pred.trend.type == TrendType.WARM) HotRed else ColdBlue,
                                    modifier = Modifier.padding(horizontal = 4.dp, vertical = 2.dp)
                                )
                            }
                        }
                    }

                    Text(
                        text = "Sezon: ${pred.seasonAvg}  •  Son 5: ${pred.l5Avg}",
                        style = MaterialTheme.typography.labelSmall,
                        color = TextMuted
                    )
                }

                // Confidence Gauge Bar
                Column(
                    horizontalAlignment = Alignment.CenterHorizontally,
                    modifier = Modifier.weight(0.9f)
                ) {
                    Text(
                        text = "%%%d Güven".format(pred.confidence),
                        fontSize = 11.sp,
                        color = AccentGreen,
                        fontWeight = FontWeight.SemiBold
                    )
                    Spacer(modifier = Modifier.height(3.dp))
                    LinearProgressIndicator(
                        progress = { (pred.confidence / 100f).coerceIn(0f, 1f) },
                        modifier = Modifier
                            .width(64.dp)
                            .height(5.dp)
                            .clip(RoundedCornerShape(3.dp)),
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
                        fontWeight = FontWeight.Medium,
                        color = diffColor
                    )
                }
            }

            // High probability threshold badges + %90+ Güvenli Alternatif Kasa Baremi
            val hasSafeFloor = pred.safeFloorLine != null && pred.safeFloorProb >= 0.88
            val topThresholds = pred.thresholds.filter { it.isHighValue || (it.overProb in 0.52..0.85) }.take(3)

            if (hasSafeFloor || topThresholds.isNotEmpty()) {
                HorizontalDivider(color = CardBorder, thickness = 0.5.dp)
                Row(
                    modifier = Modifier
                        .fillMaxWidth()
                        .padding(horizontal = 12.dp, vertical = 8.dp),
                    horizontalArrangement = Arrangement.spacedBy(8.dp),
                    verticalAlignment = Alignment.CenterVertically
                ) {
                    if (hasSafeFloor) {
                        val safePct = (pred.safeFloorProb * 100).toInt()
                        Surface(
                            shape = RoundedCornerShape(6.dp),
                            color = AccentGold.copy(alpha = 0.18f),
                            border = BorderStroke(1.dp, AccentGold)
                        ) {
                            Row(
                                verticalAlignment = Alignment.CenterVertically,
                                modifier = Modifier.padding(horizontal = 8.dp, vertical = 3.dp)
                            ) {
                                Text(
                                    text = "🛡️ %90+ Kasa: ${pred.safeFloorLine}+ (%$safePct)",
                                    fontSize = 11.sp,
                                    fontWeight = FontWeight.Bold,
                                    fontFamily = FontFamily.Monospace,
                                    color = AccentGold
                                )
                            }
                        }
                    }

                    topThresholds.forEach { t ->
                        val pct = (t.overProb * 100).toInt()
                        Surface(
                            shape = RoundedCornerShape(6.dp),
                            color = CardDark,
                            border = BorderStroke(0.6.dp, if (t.isHighValue) AccentGreen else CardBorder)
                        ) {
                            Text(
                                text = "${t.threshold}+ Üst: %$pct",
                                fontSize = 10.sp,
                                fontFamily = FontFamily.Monospace,
                                color = if (t.isHighValue) AccentGreen else TextSecondary,
                                modifier = Modifier.padding(horizontal = 6.dp, vertical = 3.dp)
                            )
                        }
                    }
                }
            }
        }
    }
}
