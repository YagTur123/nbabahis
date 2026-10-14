package com.nbabahis.app.data.api

import com.google.gson.Gson
import com.google.gson.JsonArray
import com.google.gson.JsonObject
import com.nbabahis.app.data.model.NbaGame
import com.nbabahis.app.data.model.NbaPlayer
import com.nbabahis.app.data.model.PlayerGameLog
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

    companion object {
        val TEAM_ABBR_TO_ESPN_ID = mapOf(
            "ATL" to 1, "BOS" to 2, "BKN" to 17, "CHA" to 30, "CHI" to 4,
            "CLE" to 5, "DAL" to 6, "DEN" to 7, "DET" to 8, "GSW" to 9, "GS" to 9,
            "HOU" to 10, "IND" to 11, "LAC" to 12, "LAL" to 13, "MEM" to 29,
            "MIA" to 14, "MIL" to 15, "MIN" to 16, "NOP" to 3, "NO" to 3,
            "NYK" to 18, "NY" to 18, "OKC" to 25, "ORL" to 19, "PHI" to 20,
            "PHX" to 21, "POR" to 22, "SAC" to 23, "SAS" to 24, "SA" to 24,
            "TOR" to 28, "UTA" to 26, "UTAH" to 26, "WAS" to 27, "WSH" to 27
        )

        val ESPN_ID_TO_ABBR = mapOf(
            1 to "ATL", 2 to "BOS", 17 to "BKN", 30 to "CHA", 4 to "CHI",
            5 to "CLE", 6 to "DAL", 7 to "DEN", 8 to "DET", 9 to "GSW",
            10 to "HOU", 11 to "IND", 12 to "LAC", 13 to "LAL", 29 to "MEM",
            14 to "MIA", 15 to "MIL", 16 to "MIN", 3 to "NOP", 18 to "NYK",
            25 to "OKC", 19 to "ORL", 20 to "PHI", 21 to "PHX", 22 to "POR",
            23 to "SAC", 24 to "SAS", 28 to "TOR", 26 to "UTA", 27 to "WAS"
        )
    }

    /**
     * ESPN Açık REST API üzerinden günün veya en güncel gerçek NBA maçlarını çeker.
     */
    suspend fun getScoreboard(dateStr: String): List<NbaGame> = withContext(Dispatchers.IO) {
        try {
            val cleanDate = dateStr.replace("-", "")
            val url = "https://site.api.espn.com/apis/site/v2/sports/basketball/nba/scoreboard?dates=$cleanDate"
            val request = Request.Builder().url(url).build()
            val response = client.newCall(request).execute()

            if (response.isSuccessful) {
                val body = response.body?.string() ?: ""
                val games = parseEspnScoreboard(body, dateStr)
                if (games.isNotEmpty()) return@withContext games
            }

            // Seçilen tarihte maç yoksa en güncel canlı fikstürü çek
            val fallbackUrl = "https://site.api.espn.com/apis/site/v2/sports/basketball/nba/scoreboard"
            val fbReq = Request.Builder().url(fallbackUrl).build()
            val fbResp = client.newCall(fbReq).execute()
            if (fbResp.isSuccessful) {
                val fbBody = fbResp.body?.string() ?: ""
                val fbGames = parseEspnScoreboard(fbBody, dateStr)
                if (fbGames.isNotEmpty()) return@withContext fbGames
            }

            emptyList()
        } catch (_: Exception) {
            emptyList()
        }
    }

    private fun parseEspnScoreboard(jsonStr: String, dateStr: String): List<NbaGame> {
        return try {
            val root = gson.fromJson(jsonStr, JsonObject::class.java)
            val events = root.getAsJsonArray("events") ?: return emptyList()

            val games = mutableListOf<NbaGame>()
            for (elem in events) {
                val ev = elem.asJsonObject
                val gameId = ev.get("id")?.asString ?: continue
                val comps = ev.getAsJsonArray("competitions") ?: continue
                if (comps.size() == 0) continue
                val comp = comps[0].asJsonObject

                val competitors = comp.getAsJsonArray("competitors") ?: continue
                var homeId = 0
                var awayId = 0
                var homeAbbr = "HOME"
                var awayAbbr = "AWAY"
                var homeName = "Ev Sahibi"
                var awayName = "Misafir"

                for (cElem in competitors) {
                    val c = cElem.asJsonObject
                    val isHome = c.get("homeAway")?.asString == "home"
                    val teamObj = c.getAsJsonObject("team")
                    val tId = teamObj?.get("id")?.asInt ?: 0
                    val tAbbr = teamObj?.get("abbreviation")?.asString ?: ""
                    val tName = teamObj?.get("displayName")?.asString ?: tAbbr

                    if (isHome) {
                        homeId = tId
                        homeAbbr = tAbbr
                        homeName = tName
                    } else {
                        awayId = tId
                        awayAbbr = tAbbr
                        awayName = tName
                    }
                }

                val statusObj = ev.getAsJsonObject("status")
                val statusType = statusObj?.getAsJsonObject("type")
                val gameStatus = statusType?.get("shortDetail")?.asString
                    ?: statusType?.get("description")?.asString ?: "Scheduled"
                val eventDate = ev.get("date")?.asString?.take(10) ?: dateStr

                games.add(
                    NbaGame(
                        gameId = gameId,
                        homeTeamId = homeId,
                        awayTeamId = awayId,
                        homeTeamAbbr = homeAbbr,
                        awayTeamAbbr = awayAbbr,
                        homeTeamName = homeName,
                        awayTeamName = awayName,
                        gameDate = eventDate,
                        gameStatus = gameStatus,
                        gameTime = statusObj?.get("displayClock")?.asString ?: ""
                    )
                )
            }
            games
        } catch (_: Exception) {
            emptyList()
        }
    }

    /**
     * ESPN API üzerinden takımın gerçek canlı kadrosunu çeker.
     */
    suspend fun getTeamRoster(teamId: Int, teamAbbr: String): List<NbaPlayer> = withContext(Dispatchers.IO) {
        try {
            val espnId = TEAM_ABBR_TO_ESPN_ID[teamAbbr.uppercase()] ?: if (teamId in 1..30) teamId else 13
            val url = "https://site.api.espn.com/apis/site/v2/sports/basketball/nba/teams/$espnId/roster"
            val request = Request.Builder().url(url).build()
            val response = client.newCall(request).execute()

            if (response.isSuccessful) {
                val body = response.body?.string() ?: return@withContext emptyList()
                parseEspnRoster(body, teamAbbr)
            } else {
                emptyList()
            }
        } catch (_: Exception) {
            emptyList()
        }
    }

    private fun parseEspnRoster(jsonStr: String, teamAbbr: String): List<NbaPlayer> {
        return try {
            val root = gson.fromJson(jsonStr, JsonObject::class.java)
            val athletes = root.getAsJsonArray("athletes") ?: return emptyList()

            val players = mutableListOf<NbaPlayer>()
            for (elem in athletes) {
                val a = elem.asJsonObject
                val pId = a.get("id")?.asInt ?: continue
                val name = a.get("displayName")?.asString ?: a.get("fullName")?.asString ?: continue
                val jersey = a.get("jersey")?.asString ?: ""
                val posObj = a.getAsJsonObject("position")
                val pos = posObj?.get("abbreviation")?.asString ?: "G"

                players.add(
                    NbaPlayer(
                        playerId = pId,
                        name = name,
                        teamAbbr = teamAbbr,
                        position = pos,
                        jerseyNum = jersey
                    )
                )
            }
            players
        } catch (_: Exception) {
            emptyList()
        }
    }

    /**
     * ESPN API üzerinden oyuncunun gerçek sezon maç kayıtlarını çeker.
     */
    suspend fun getPlayerGameLogs(playerId: Int): List<PlayerGameLog> = withContext(Dispatchers.IO) {
        try {
            val url = "https://site.web.api.espn.com/apis/common/v3/sports/basketball/nba/athletes/$playerId/gamelog"
            val request = Request.Builder().url(url).build()
            val response = client.newCall(request).execute()

            if (response.isSuccessful) {
                val body = response.body?.string() ?: return@withContext emptyList()
                parseEspnGameLogs(body)
            } else {
                emptyList()
            }
        } catch (_: Exception) {
            emptyList()
        }
    }

    private fun parseEspnGameLogs(jsonStr: String): List<PlayerGameLog> {
        return try {
            val root = gson.fromJson(jsonStr, JsonObject::class.java)
            val labelsArray = root.getAsJsonArray("labels") ?: return emptyList()
            val labels = labelsArray.map { it.asString }

            val minIdx = labels.indexOf("MIN")
            val ptsIdx = labels.indexOf("PTS")
            val rebIdx = labels.indexOf("REB")
            val astIdx = labels.indexOf("AST")
            val blkIdx = labels.indexOf("BLK")
            val stlIdx = labels.indexOf("STL")
            val pfIdx = labels.indexOf("PF")
            val toIdx = labels.indexOf("TO")
            val fgIdx = labels.indexOf("FG")
            val fg3Idx = labels.indexOf("3PT")
            val ftIdx = labels.indexOf("FT")

            val eventsObj = root.getAsJsonObject("events") ?: JsonObject()
            val seasonTypes = root.getAsJsonArray("seasonTypes") ?: return emptyList()

            val logs = mutableListOf<PlayerGameLog>()

            for (stElem in seasonTypes) {
                val st = stElem.asJsonObject
                val categories = st.getAsJsonArray("categories") ?: continue

                for (catElem in categories) {
                    val cat = catElem.asJsonObject
                    val eventsList = cat.getAsJsonArray("events") ?: continue

                    for (evElem in eventsList) {
                        val ev = evElem.asJsonObject
                        val eventId = ev.get("eventId")?.asString ?: continue
                        val statsArr = ev.getAsJsonArray("stats") ?: continue

                        val meta = eventsObj.getAsJsonObject(eventId)
                        val gameDate = meta?.get("gameDate")?.asString?.take(10) ?: ""
                        val atVs = meta?.get("atVs")?.asString ?: "vs"
                        val oppAbbr = meta?.getAsJsonObject("opponent")?.get("abbreviation")?.asString ?: "OPP"
                        val matchup = "$atVs $oppAbbr"

                        val minVal = getStatDouble(statsArr, minIdx)
                        val ptsVal = getStatDouble(statsArr, ptsIdx)
                        val rebVal = getStatDouble(statsArr, rebIdx)
                        val astVal = getStatDouble(statsArr, astIdx)
                        val blkVal = getStatDouble(statsArr, blkIdx)
                        val stlVal = getStatDouble(statsArr, stlIdx)
                        val pfVal = getStatDouble(statsArr, pfIdx)
                        val toVal = getStatDouble(statsArr, toIdx)

                        val (fgmVal, fgaVal) = parseSplitStats(statsArr, fgIdx)
                        val (fg3mVal, fg3aVal) = parseSplitStats(statsArr, fg3Idx)
                        val (ftmVal, ftaVal) = parseSplitStats(statsArr, ftIdx)

                        logs.add(
                            PlayerGameLog(
                                gameId = eventId,
                                gameDate = gameDate,
                                matchup = matchup,
                                min = minVal,
                                pts = ptsVal,
                                reb = rebVal,
                                ast = astVal,
                                stl = stlVal,
                                blk = blkVal,
                                tov = toVal,
                                pf = pfVal,
                                fg3m = fg3mVal,
                                fg3a = fg3aVal,
                                fgm = fgmVal,
                                fga = fgaVal,
                                ftm = ftmVal,
                                fta = ftaVal
                            )
                        )
                    }
                }
            }
            logs
        } catch (_: Exception) {
            emptyList()
        }
    }

    private fun getStatDouble(arr: JsonArray, index: Int): Double {
        if (index == -1 || index >= arr.size()) return 0.0
        val s = arr[index].asString
        return s.toDoubleOrNull() ?: 0.0
    }

    private fun parseSplitStats(arr: JsonArray, index: Int): Pair<Double, Double> {
        if (index == -1 || index >= arr.size()) return 0.0 to 0.0
        val s = arr[index].asString
        val parts = s.split("-")
        return if (parts.size == 2) {
            val made = parts[0].trim().toDoubleOrNull() ?: 0.0
            val att = parts[1].trim().toDoubleOrNull() ?: 0.0
            made to att
        } else {
            0.0 to 0.0
        }
    }

    /**
     * ESPN Canlı Sakatlık Raporu
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
}
