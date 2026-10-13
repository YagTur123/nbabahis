package com.nbabahis.app.data.api

import com.google.gson.Gson
import com.google.gson.JsonObject
import com.nbabahis.app.data.model.NbaGame
import com.nbabahis.app.data.model.NbaPlayer
import com.nbabahis.app.data.model.PlayerGameLog
import com.nbabahis.app.data.model.TeamStats
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import okhttp3.OkHttpClient
import okhttp3.Request
import java.util.concurrent.TimeUnit

class NbaApiService(
    private val client: OkHttpClient = OkHttpClient.Builder()
        .addInterceptor(NbaHeadersInterceptor())
        .connectTimeout(15, TimeUnit.SECONDS)
        .readTimeout(15, TimeUnit.SECONDS)
        .build(),
    private val gson: Gson = Gson()
) {

    /**
     * Günün NBA maçlarını çeker. (stats.nba.com veya ESPN scoreboard)
     */
    suspend fun getScoreboard(dateStr: String): List<NbaGame> = withContext(Dispatchers.IO) {
        try {
            val url = "https://stats.nba.com/stats/scoreboardv3?GameDate=$dateStr&LeagueID=00"
            val request = Request.Builder().url(url).build()
            val response = client.newCall(request).execute()
            if (response.isSuccessful) {
                val body = response.body?.string() ?: return@withContext getSampleGames(dateStr)
                parseNbaScoreboard(body, dateStr)
            } else {
                getSampleGames(dateStr)
            }
        } catch (_: Exception) {
            getSampleGames(dateStr)
        }
    }

    private fun parseNbaScoreboard(jsonStr: String, dateStr: String): List<NbaGame> {
        return try {
            val root = gson.fromJson(jsonStr, JsonObject::class.java)
            val scoreboard = root.getAsJsonObject("scoreboard") ?: return getSampleGames(dateStr)
            val gamesArray = scoreboard.getAsJsonArray("games") ?: return getSampleGames(dateStr)

            val games = mutableListOf<NbaGame>()
            for (element in gamesArray) {
                val g = element.asJsonObject
                val gameId = g.get("gameId")?.asString ?: continue
                val homeTeamObj = g.getAsJsonObject("homeTeam")
                val awayTeamObj = g.getAsJsonObject("awayTeam")

                val homeId = homeTeamObj?.get("teamId")?.asInt ?: 0
                val awayId = awayTeamObj?.get("teamId")?.asInt ?: 0
                val homeAbbr = homeTeamObj?.get("teamTricode")?.asString ?: "HOME"
                val awayAbbr = awayTeamObj?.get("teamTricode")?.asString ?: "AWAY"
                val homeName = homeTeamObj?.get("teamName")?.asString ?: homeAbbr
                val awayName = awayTeamObj?.get("teamName")?.asString ?: awayAbbr
                val gameStatus = g.get("gameStatusText")?.asString ?: "Scheduled"

                games.add(
                    NbaGame(
                        gameId = gameId,
                        homeTeamId = homeId,
                        awayTeamId = awayId,
                        homeTeamAbbr = homeAbbr,
                        awayTeamAbbr = awayAbbr,
                        homeTeamName = homeName,
                        awayTeamName = awayName,
                        gameDate = dateStr,
                        gameStatus = gameStatus
                    )
                )
            }
            if (games.isNotEmpty()) games else getSampleGames(dateStr)
        } catch (_: Exception) {
            getSampleGames(dateStr)
        }
    }

    /**
     * Takım kadrosunu çeker.
     */
    suspend fun getTeamRoster(teamId: Int, season: String = "2024-25"): List<NbaPlayer> = withContext(Dispatchers.IO) {
        try {
            val url = "https://stats.nba.com/stats/commonteamroster?TeamID=$teamId&Season=$season"
            val request = Request.Builder().url(url).build()
            val response = client.newCall(request).execute()
            if (response.isSuccessful) {
                val body = response.body?.string() ?: return@withContext emptyList()
                parseRoster(body)
            } else {
                emptyList()
            }
        } catch (_: Exception) {
            emptyList()
        }
    }

    private fun parseRoster(jsonStr: String): List<NbaPlayer> {
        return try {
            val root = gson.fromJson(jsonStr, JsonObject::class.java)
            val resultSets = root.getAsJsonArray("resultSets") ?: return emptyList()
            val rosterSet = resultSets.firstOrNull { it.asJsonObject.get("name")?.asString == "CommonTeamRoster" }?.asJsonObject ?: return emptyList()
            val headers = rosterSet.getAsJsonArray("headers").map { it.asString }
            val rows = rosterSet.getAsJsonArray("rowSet") ?: return emptyList()

            val pIdIdx = headers.indexOf("PLAYER_ID")
            val pNameIdx = headers.indexOf("PLAYER")
            val posIdx = headers.indexOf("POSITION")
            val numIdx = headers.indexOf("NUM")

            val players = mutableListOf<NbaPlayer>()
            for (row in rows) {
                val arr = row.asJsonArray
                val pId = arr[pIdIdx].asInt
                val pName = arr[pNameIdx].asString
                val pos = if (posIdx != -1) arr[posIdx].asString else "G"
                val num = if (numIdx != -1) arr[numIdx].asString else ""

                players.add(
                    NbaPlayer(
                        playerId = pId,
                        name = pName,
                        teamAbbr = "",
                        position = pos,
                        jerseyNum = num
                    )
                )
            }
            players
        } catch (_: Exception) {
            emptyList()
        }
    }

    /**
     * Oyuncunun son maçlarını çeker.
     */
    suspend fun getPlayerGameLogs(playerId: Int, season: String = "2024-25"): List<PlayerGameLog> = withContext(Dispatchers.IO) {
        try {
            val url = "https://stats.nba.com/stats/playergamelog?PlayerID=$playerId&Season=$season&SeasonType=Regular+Season"
            val request = Request.Builder().url(url).build()
            val response = client.newCall(request).execute()
            if (response.isSuccessful) {
                val body = response.body?.string() ?: return@withContext emptyList()
                parseGameLogs(body)
            } else {
                emptyList()
            }
        } catch (_: Exception) {
            emptyList()
        }
    }

    private fun parseGameLogs(jsonStr: String): List<PlayerGameLog> {
        return try {
            val root = gson.fromJson(jsonStr, JsonObject::class.java)
            val resultSets = root.getAsJsonArray("resultSets") ?: return emptyList()
            val logSet = resultSets.firstOrNull()?.asJsonObject ?: return emptyList()
            val headers = logSet.getAsJsonArray("headers").map { it.asString }
            val rows = logSet.getAsJsonArray("rowSet") ?: return emptyList()

            val dIdx = headers.indexOf("GAME_DATE")
            val mIdx = headers.indexOf("MATCHUP")
            val minIdx = headers.indexOf("MIN")
            val ptsIdx = headers.indexOf("PTS")
            val rebIdx = headers.indexOf("REB")
            val astIdx = headers.indexOf("AST")
            val stlIdx = headers.indexOf("STL")
            val blkIdx = headers.indexOf("BLK")
            val fg3mIdx = headers.indexOf("FG3M")
            val tovIdx = headers.indexOf("TOV")

            val logs = mutableListOf<PlayerGameLog>()
            for (row in rows) {
                val arr = row.asJsonArray
                logs.add(
                    PlayerGameLog(
                        gameDate = arr[dIdx].asString,
                        matchup = arr[mIdx].asString,
                        min = arr[minIdx].asDouble,
                        pts = arr[ptsIdx].asDouble,
                        reb = arr[rebIdx].asDouble,
                        ast = arr[astIdx].asDouble,
                        stl = if (stlIdx != -1) arr[stlIdx].asDouble else 0.0,
                        blk = if (blkIdx != -1) arr[blkIdx].asDouble else 0.0,
                        fg3m = if (fg3mIdx != -1) arr[fg3mIdx].asDouble else 0.0,
                        tov = if (tovIdx != -1) arr[tovIdx].asDouble else 0.0
                    )
                )
            }
            logs
        } catch (_: Exception) {
            emptyList()
        }
    }

    /**
     * ESPN Sakatlık Raporu
     */
    suspend fun getInjuries(): Map<String, String> = withContext(Dispatchers.IO) {
        try {
            val url = "https://site.api.espn.com/apis/site/v2/sports/basketball/nba/injuries"
            val request = Request.Builder().url(url).build()
            val response = client.newCall(request).execute()
            if (response.isSuccessful) {
                val body = response.body?.string() ?: return@withContext emptyMap()
                val root = gson.fromJson(body, JsonObject::class.java)
                val injuriesArray = root.getAsJsonArray("injuries") ?: return@withContext emptyMap()
                val map = mutableMapOf<String, String>()
                for (teamEntry in injuriesArray) {
                    val subInjuries = teamEntry.asJsonObject.getAsJsonArray("injuries") ?: continue
                    for (inj in subInjuries) {
                        val athlete = inj.asJsonObject.getAsJsonObject("athlete")
                        val name = athlete?.get("displayName")?.asString ?: ""
                        val status = inj.asJsonObject.get("status")?.asString ?: ""
                        if (name.isNotEmpty()) {
                            map[name.lowercase().trim()] = status
                        }
                    }
                }
                map
            } else {
                emptyMap()
            }
        } catch (_: Exception) {
            emptyMap()
        }
    }

    /**
     * Varsayılan / Yedek NBA Maçları (İnternet yokken veya sezon aralarındayken anında çalışan örnek maçlar)
     */
    fun getSampleGames(dateStr: String): List<NbaGame> = listOf(
        NbaGame("0022400101", 1610612747, 1610612738, "LAL", "BOS", "Los Angeles Lakers", "Boston Celtics", dateStr, "02:30"),
        NbaGame("0022400102", 1610612744, 1610612743, "GSW", "DEN", "Golden State Warriors", "Denver Nuggets", dateStr, "05:00"),
        NbaGame("0022400103", 1610612752, 1610612755, "NYK", "PHI", "New York Knicks", "Philadelphia 76ers", dateStr, "02:00"),
        NbaGame("0022400104", 1610612749, 1610612756, "MIL", "PHX", "Milwaukee Bucks", "Phoenix Suns", dateStr, "03:00"),
        NbaGame("0022400105", 1610612742, 1610612760, "DAL", "OKC", "Dallas Mavericks", "Oklahoma City Thunder", dateStr, "04:30")
    )
}
