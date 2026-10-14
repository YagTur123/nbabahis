package com.nbabahis.app.ui.screens

import androidx.compose.animation.*
import androidx.compose.animation.core.Spring
import androidx.compose.animation.core.spring
import androidx.compose.foundation.BorderStroke
import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.filled.ArrowBack
import androidx.compose.material.icons.filled.CheckCircle
import androidx.compose.material.icons.filled.Info
import androidx.compose.material.icons.filled.RadioButtonUnchecked
import androidx.compose.material.icons.filled.Security
import androidx.compose.material.icons.filled.Share
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Brush
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.nbabahis.app.data.model.NbaPlayer
import com.nbabahis.app.domain.model.PredictionResult
import com.nbabahis.app.domain.model.StatPrediction
import com.nbabahis.app.ui.theme.*

data class SafeBetOption(
    val id: String,
    val player: NbaPlayer,
    val opponentAbbr: String,
    val isHome: Boolean,
    val prediction: StatPrediction
)

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun SafeSlateScreen(
    results: List<PredictionResult>,
    onBackClicked: () -> Unit,
    modifier: Modifier = Modifier
) {
    // Extract all predictions that satisfy safe floor criteria (>= 88% probability)
    val safeOptions = remember(results) {
        val list = mutableListOf<SafeBetOption>()
        results.forEach { res ->
            res.predictions.forEach { pred ->
                if (pred.safeFloorLine != null && pred.safeFloorProb >= 0.88) {
                    list.add(
                        SafeBetOption(
                            id = "${res.player.id}_${pred.statKey}",
                            player = res.player,
                            opponentAbbr = res.opponentAbbr,
                            isHome = res.isHome,
                            prediction = pred
                        )
                    )
                }
            }
        }
        list.sortedByDescending { it.prediction.safeFloorProb }
    }

    var selectedIds by remember { mutableStateOf<Set<String>>(emptySet()) }
    val selectedOptions = remember(safeOptions, selectedIds) {
        safeOptions.filter { it.id in selectedIds }
    }

    val avgSafeRate = if (safeOptions.isNotEmpty()) {
        safeOptions.map { it.prediction.safeFloorProb }.average()
    } else 0.0

    // Combined parlay decimal odds estimate based on probabilities
    val combinedProbability = remember(selectedOptions) {
        if (selectedOptions.isEmpty()) 1.0
        else selectedOptions.fold(1.0) { acc, item -> acc * item.prediction.safeFloorProb }
    }

    val estimatedOdds = remember(combinedProbability) {
        if (combinedProbability > 0) (1.0 / combinedProbability).coerceAtLeast(1.05) else 1.05
    }

    Scaffold(
        topBar = {
            TopAppBar(
                title = {
                    Row(verticalAlignment = Alignment.CenterVertically) {
                        Icon(
                            imageVector = Icons.Default.Security,
                            contentDescription = null,
                            tint = AccentGold,
                            modifier = Modifier.size(22.dp)
                        )
                        Spacer(modifier = Modifier.width(8.dp))
                        Text(
                            text = "%90+ Kasa Kuponu",
                            style = MaterialTheme.typography.titleLarge,
                            color = TextPrimary
                        )
                    }
                },
                navigationIcon = {
                    IconButton(onClick = onBackClicked) {
                        Icon(
                            imageVector = Icons.AutoMirrored.Filled.ArrowBack,
                            contentDescription = "Geri",
                            tint = TextPrimary
                        )
                    }
                },
                colors = TopAppBarDefaults.topAppBarColors(containerColor = BgDark)
            )
        },
        bottomBar = {
            AnimatedVisibility(
                visible = selectedOptions.isNotEmpty(),
                enter = slideInVertically(initialOffsetY = { it }) + fadeIn(),
                exit = slideOutVertically(targetOffsetY = { it }) + fadeOut()
            ) {
                Surface(
                    shape = RoundedCornerShape(topStart = 24.dp, topEnd = 24.dp),
                    color = CardDark,
                    border = BorderStroke(1.dp, AccentGold.copy(alpha = 0.5f)),
                    shadowElevation = 16.dp,
                    modifier = Modifier.fillMaxWidth()
                ) {
                    Column(
                        modifier = Modifier
                            .fillMaxWidth()
                            .padding(16.dp)
                    ) {
                        Row(
                            modifier = Modifier.fillMaxWidth(),
                            horizontalArrangement = Arrangement.SpaceBetween,
                            verticalAlignment = Alignment.CenterVertically
                        ) {
                            Column {
                                Text(
                                    text = "Seçilen Kasa Seçimleri: ${selectedOptions.size}",
                                    style = MaterialTheme.typography.titleSmall,
                                    color = TextPrimary
                                )
                                Text(
                                    text = "Kombine Başarı İhtimali: %${(combinedProbability * 100).toInt()}",
                                    style = MaterialTheme.typography.labelSmall,
                                    color = AccentGreen
                                )
                            }
                            Column(horizontalAlignment = Alignment.End) {
                                Text(
                                    text = "Tahmini Oran",
                                    style = MaterialTheme.typography.labelSmall,
                                    color = TextSecondary
                                )
                                Text(
                                    text = "%.2f".format(estimatedOdds),
                                    fontSize = 20.sp,
                                    fontWeight = FontWeight.Bold,
                                    fontFamily = FontFamily.Monospace,
                                    color = AccentGold
                                )
                            }
                        }

                        Spacer(modifier = Modifier.height(10.dp))

                        Row(
                            modifier = Modifier.fillMaxWidth(),
                            horizontalArrangement = Arrangement.spacedBy(8.dp)
                        ) {
                            OutlinedButton(
                                onClick = { selectedIds = emptySet() },
                                colors = ButtonDefaults.outlinedButtonColors(contentColor = TextSecondary),
                                border = BorderStroke(0.8.dp, CardBorder),
                                modifier = Modifier.weight(1f)
                            ) {
                                Text("Temizle", fontSize = 12.sp)
                            }

                            Button(
                                onClick = {
                                    // Prepares selection
                                },
                                colors = ButtonDefaults.buttonColors(containerColor = AccentGold),
                                modifier = Modifier.weight(2f)
                            ) {
                                Text(
                                    text = "Kuponu Kaydet / Oyna",
                                    color = CardDark,
                                    fontWeight = FontWeight.Bold,
                                    fontSize = 13.sp
                                )
                            }
                        }
                    }
                }
            }
        },
        containerColor = BgDark,
        modifier = modifier
    ) { innerPadding ->
        LazyColumn(
            modifier = Modifier
                .fillMaxSize()
                .padding(innerPadding),
            contentPadding = PaddingValues(horizontal = 16.dp, vertical = 12.dp),
            verticalArrangement = Arrangement.spacedBy(14.dp)
        ) {
            // Header Hero Banner
            item {
                Card(
                    shape = RoundedCornerShape(20.dp),
                    colors = CardDefaults.cardColors(containerColor = Color.Transparent),
                    border = BorderStroke(1.2.dp, AccentGold.copy(alpha = 0.6f)),
                    modifier = Modifier.fillMaxWidth()
                ) {
                    Box(
                        modifier = Modifier
                            .fillMaxWidth()
                            .background(
                                Brush.linearGradient(
                                    colors = listOf(
                                        Color(0xFF2A2006),
                                        Color(0xFF151A23),
                                        Color(0xFF0D181D)
                                    )
                                )
                            )
                            .padding(18.dp)
                    ) {
                        Column {
                            Row(
                                modifier = Modifier.fillMaxWidth(),
                                horizontalArrangement = Arrangement.SpaceBetween,
                                verticalAlignment = Alignment.CenterVertically
                            ) {
                                Row(verticalAlignment = Alignment.CenterVertically) {
                                    Surface(
                                        shape = CircleShape,
                                        color = AccentGold.copy(alpha = 0.2f),
                                        modifier = Modifier.size(36.dp)
                                    ) {
                                        Box(contentAlignment = Alignment.Center) {
                                            Text("🛡️", fontSize = 18.sp)
                                        }
                                    }
                                    Spacer(modifier = Modifier.width(10.dp))
                                    Column {
                                        Text(
                                            text = "%90+ Kasa Koridoru",
                                            style = MaterialTheme.typography.titleMedium,
                                            fontWeight = FontWeight.Bold,
                                            color = TextPrimary
                                        )
                                        Text(
                                            text = "Ampirik Doğrulanmış Güvenli Baremler",
                                            style = MaterialTheme.typography.labelSmall,
                                            color = AccentGold
                                        )
                                    }
                                }
                            }

                            Spacer(modifier = Modifier.height(14.dp))

                            Row(
                                modifier = Modifier.fillMaxWidth(),
                                horizontalArrangement = Arrangement.SpaceAround
                            ) {
                                HeaderStatBadge(
                                    title = "Aktif Fırsat",
                                    value = "${safeOptions.size}",
                                    color = AccentCyan
                                )
                                HeaderStatBadge(
                                    title = "Ort. Başarı",
                                    value = "%%%d".format((avgSafeRate * 100).toInt()),
                                    color = AccentGreen
                                )
                                HeaderStatBadge(
                                    title = "Risk Profili",
                                    value = "Ultra Düşük",
                                    color = AccentGold
                                )
                            }
                        }
                    }
                }
            }

            if (safeOptions.isEmpty()) {
                item {
                    Card(
                        modifier = Modifier
                            .fillMaxWidth()
                            .padding(vertical = 24.dp),
                        shape = RoundedCornerShape(16.dp),
                        colors = CardDefaults.cardColors(containerColor = SurfaceDark),
                        border = BorderStroke(1.dp, CardBorder)
                    ) {
                        Column(
                            modifier = Modifier
                                .fillMaxWidth()
                                .padding(24.dp),
                            horizontalAlignment = Alignment.CenterHorizontally
                        ) {
                            Icon(
                                imageVector = Icons.Default.Info,
                                contentDescription = null,
                                tint = TextSecondary,
                                modifier = Modifier.size(40.dp)
                            )
                            Spacer(modifier = Modifier.height(12.dp))
                            Text(
                                text = "Şu anda taranmış güvenli barem bulunamadı.",
                                style = MaterialTheme.typography.titleMedium,
                                color = TextPrimary,
                                textAlign = TextAlign.Center
                            )
                            Spacer(modifier = Modifier.height(4.dp))
                            Text(
                                text = "Maçlar ekranından 'Geceyi Tara' butonuna basarak tüm oyuncuları tarayabilirsiniz.",
                                style = MaterialTheme.typography.bodySmall,
                                color = TextMuted,
                                textAlign = TextAlign.Center
                            )
                        }
                    }
                }
            } else {
                items(safeOptions, key = { it.id }) { option ->
                    val isSelected = option.id in selectedIds
                    SafeBetCard(
                        option = option,
                        isSelected = isSelected,
                        onToggle = {
                            selectedIds = if (isSelected) {
                                selectedIds - option.id
                            } else {
                                selectedIds + option.id
                            }
                        }
                    )
                }
            }

            // Extra padding at bottom for floating slip
            item {
                Spacer(modifier = Modifier.height(80.dp))
            }
        }
    }
}

@Composable
private fun HeaderStatBadge(
    title: String,
    value: String,
    color: Color
) {
    Column(horizontalAlignment = Alignment.CenterHorizontally) {
        Text(
            text = value,
            fontSize = 18.sp,
            fontWeight = FontWeight.Bold,
            fontFamily = FontFamily.Monospace,
            color = color
        )
        Text(
            text = title,
            style = MaterialTheme.typography.labelSmall,
            color = TextMuted
        )
    }
}

@Composable
private fun SafeBetCard(
    option: SafeBetOption,
    isSelected: Boolean,
    onToggle: () -> Unit
) {
    val borderColor = if (isSelected) AccentGold else CardBorder
    val containerColor = if (isSelected) Color(0xFF221C10) else CardDark

    Card(
        modifier = Modifier
            .fillMaxWidth()
            .clickable { onToggle() },
        shape = RoundedCornerShape(16.dp),
        colors = CardDefaults.cardColors(containerColor = containerColor),
        border = BorderStroke(if (isSelected) 1.5.dp else 1.dp, borderColor)
    ) {
        Column(modifier = Modifier.padding(14.dp)) {
            Row(
                modifier = Modifier.fillMaxWidth(),
                horizontalArrangement = Arrangement.SpaceBetween,
                verticalAlignment = Alignment.CenterVertically
            ) {
                Row(
                    verticalAlignment = Alignment.CenterVertically,
                    modifier = Modifier.weight(1f)
                ) {
                    IconButton(
                        onClick = onToggle,
                        modifier = Modifier.size(32.dp)
                    ) {
                        Icon(
                            imageVector = if (isSelected) Icons.Default.CheckCircle else Icons.Default.RadioButtonUnchecked,
                            contentDescription = "Seç",
                            tint = if (isSelected) AccentGold else TextMuted
                        )
                    }

                    Spacer(modifier = Modifier.width(6.dp))

                    Column {
                        Text(
                            text = option.player.name,
                            style = MaterialTheme.typography.titleMedium,
                            fontWeight = FontWeight.Bold,
                            color = TextPrimary
                        )
                        val matchLoc = if (option.isHome) "Evinde vs ${option.opponentAbbr}" else "Deplasmanda @ ${option.opponentAbbr}"
                        Text(
                            text = "${option.player.teamAbbr} · $matchLoc",
                            style = MaterialTheme.typography.labelSmall,
                            color = AccentCyan
                        )
                    }
                }

                // Probability Badge
                Surface(
                    shape = RoundedCornerShape(8.dp),
                    color = AccentGold.copy(alpha = 0.15f),
                    border = BorderStroke(1.dp, AccentGold)
                ) {
                    val pct = (option.prediction.safeFloorProb * 100).toInt()
                    Text(
                        text = "%%%d Başarı".format(pct),
                        fontSize = 11.sp,
                        fontWeight = FontWeight.Bold,
                        fontFamily = FontFamily.Monospace,
                        color = AccentGold,
                        modifier = Modifier.padding(horizontal = 8.dp, vertical = 4.dp)
                    )
                }
            }

            Spacer(modifier = Modifier.height(12.dp))

            // Stat & Line breakdown
            Surface(
                shape = RoundedCornerShape(10.dp),
                color = SurfaceDark,
                modifier = Modifier.fillMaxWidth()
            ) {
                Row(
                    modifier = Modifier
                        .fillMaxWidth()
                        .padding(horizontal = 12.dp, vertical = 10.dp),
                    horizontalArrangement = Arrangement.SpaceBetween,
                    verticalAlignment = Alignment.CenterVertically
                ) {
                    Column {
                        Text(
                            text = "KASA TAHMİNİ",
                            style = MaterialTheme.typography.labelSmall,
                            fontSize = 9.sp,
                            color = TextMuted
                        )
                        Text(
                            text = "${option.prediction.displayName}: ${option.prediction.safeFloorLine}+ Üst",
                            style = MaterialTheme.typography.titleSmall,
                            fontWeight = FontWeight.Bold,
                            color = AccentGreen
                        )
                    }

                    Column(horizontalAlignment = Alignment.End) {
                        Text(
                            text = "MODEL PROJEKSİYONU",
                            style = MaterialTheme.typography.labelSmall,
                            fontSize = 9.sp,
                            color = TextMuted
                        )
                        Text(
                            text = "${option.prediction.predictedValue} (Sezon: ${option.prediction.seasonAvg})",
                            style = MaterialTheme.typography.bodySmall,
                            fontFamily = FontFamily.Monospace,
                            color = TextSecondary
                        )
                    }
                }
            }
        }
    }
}
