package com.nbabahis.app.ui.screens.components

import androidx.compose.foundation.BorderStroke
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.*
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.nbabahis.app.data.model.NbaGame
import com.nbabahis.app.ui.theme.*

@Composable
fun GameCard(
    game: NbaGame,
    isSelected: Boolean,
    onClick: () -> Unit,
    modifier: Modifier = Modifier
) {
    val borderColor = if (isSelected) AccentCyan else CardBorder
    val containerColor = if (isSelected) SurfaceDark else CardDark

    Card(
        modifier = modifier
            .fillMaxWidth()
            .clickable(onClick = onClick),
        shape = RoundedCornerShape(16.dp),
        colors = CardDefaults.cardColors(containerColor = containerColor),
        border = BorderStroke(if (isSelected) 1.8.dp else 1.dp, borderColor)
    ) {
        Column(
            modifier = Modifier
                .fillMaxWidth()
                .padding(14.dp)
        ) {
            // Status bar
            Row(
                modifier = Modifier.fillMaxWidth(),
                horizontalArrangement = Arrangement.SpaceBetween,
                verticalAlignment = Alignment.CenterVertically
            ) {
                Surface(
                    shape = RoundedCornerShape(6.dp),
                    color = if (isSelected) AccentCyan.copy(alpha = 0.2f) else CardBorder.copy(alpha = 0.5f)
                ) {
                    Text(
                        text = if (isSelected) "SEÇİLDİ" else "MAÇ",
                        fontSize = 9.sp,
                        fontWeight = FontWeight.Bold,
                        color = if (isSelected) AccentCyan else TextMuted,
                        modifier = Modifier.padding(horizontal = 6.dp, vertical = 2.dp)
                    )
                }

                Text(
                    text = game.gameStatus,
                    style = MaterialTheme.typography.labelSmall,
                    fontWeight = FontWeight.SemiBold,
                    color = if (game.gameStatus.contains("Live", ignoreCase = true) || game.gameStatus.contains("Q", ignoreCase = true)) HotRed else AccentGold
                )
            }

            Spacer(modifier = Modifier.height(10.dp))

            // Teams Row
            Row(
                modifier = Modifier.fillMaxWidth(),
                verticalAlignment = Alignment.CenterVertically,
                horizontalArrangement = Arrangement.SpaceBetween
            ) {
                // Away Team
                Column(
                    horizontalAlignment = Alignment.CenterHorizontally,
                    modifier = Modifier.weight(1f)
                ) {
                    Surface(
                        shape = CircleShape,
                        color = SurfaceDark,
                        border = BorderStroke(1.dp, CardBorder),
                        modifier = Modifier.size(38.dp)
                    ) {
                        Box(contentAlignment = Alignment.Center) {
                            Text(
                                text = game.awayTeamAbbr,
                                fontWeight = FontWeight.Bold,
                                fontSize = 12.sp,
                                color = TextPrimary
                            )
                        }
                    }
                    Spacer(modifier = Modifier.height(4.dp))
                    Text(
                        text = "Deplasman",
                        style = MaterialTheme.typography.labelSmall,
                        fontSize = 9.sp,
                        color = TextMuted
                    )
                }

                // VS
                Column(
                    horizontalAlignment = Alignment.CenterHorizontally,
                    modifier = Modifier.padding(horizontal = 4.dp)
                ) {
                    Text(
                        text = "@",
                        fontWeight = FontWeight.Bold,
                        fontSize = 14.sp,
                        color = AccentCyan
                    )
                    if (game.gameTime.isNotEmpty()) {
                        Text(
                            text = game.gameTime,
                            fontSize = 10.sp,
                            fontFamily = FontFamily.Monospace,
                            color = TextSecondary
                        )
                    }
                }

                // Home Team
                Column(
                    horizontalAlignment = Alignment.CenterHorizontally,
                    modifier = Modifier.weight(1f)
                ) {
                    Surface(
                        shape = CircleShape,
                        color = SurfaceDark,
                        border = BorderStroke(1.dp, if (isSelected) AccentCyan.copy(alpha = 0.7f) else CardBorder),
                        modifier = Modifier.size(38.dp)
                    ) {
                        Box(contentAlignment = Alignment.Center) {
                            Text(
                                text = game.homeTeamAbbr,
                                fontWeight = FontWeight.Bold,
                                fontSize = 12.sp,
                                color = TextPrimary
                            )
                        }
                    }
                    Spacer(modifier = Modifier.height(4.dp))
                    Text(
                        text = "Ev Sahibi",
                        style = MaterialTheme.typography.labelSmall,
                        fontSize = 9.sp,
                        color = TextMuted
                    )
                }
            }
        }
    }
}
