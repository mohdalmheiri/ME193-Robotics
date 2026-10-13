# Check the opponent tuning without hardware: simulates rallies with the same
# opponent.py logic and the constants from game.py.
# Run:  python tune_opponent.py
#
# Player model: hits each incoming ball with probability p_hit (a player who never
# misses wins every point eventually, so "near-perfect" = 90%). Aim = paddle dot
# anywhere in the ring (uniform over the disk); power mostly medium, sometimes a smash.
import math
import random

import game
from opponent import Opponent, plan_return

DT = 1 / 30
SHOTS = 20000
MATCHES = 2000


def bot_for(level):
    return Opponent(game.BOT_KP[level], game.BOT_KD[level], game.BOT_MAX_SPEED[level],
                    game.BOT_REACTION[level], game.BOT_CATCH[level], game.BOT_MISS_CHANCE[level])


def random_shot(rng):
    r, a = math.sqrt(rng.random()), rng.uniform(0, 2 * math.pi)
    return r * math.cos(a), rng.triangular(0.15, 1.0, 0.45)      # aim, power


def bot_returns(bot, aim, power, rng):
    """Your shot is in the air: does the bot get it back?"""
    land, flight, _ = plan_return(aim, power, game.AIM_SPREAD, game.AIM_NOISE, game.RETURN_SLOW,
                                  game.RETURN_FAST, game.SMASH_POWER, game.SMASH_SPEEDUP, rng)
    bot.chase(land, 0.0)
    t = 0.0
    while t < flight:
        bot.update(t, DT)
        t += DT
    return bot.returns(land, rng)


def recenter(bot, seconds):
    """While the ball flies to you, the bot drifts back to the middle."""
    bot.recenter(0.0)
    t = 0.0
    while t < seconds:
        bot.update(t, DT)
        t += DT


def shot_stats(level, rng):
    """Per-shot: how often the bot fails to return, by kind of shot."""
    kinds = {"all": [0, 0], "center & weak": [0, 0], "corner (|aim|>0.7)": [0, 0], "smash": [0, 0]}
    bot = bot_for(level)
    for _ in range(SHOTS):
        aim, power = random_shot(rng)
        recenter(bot, game.FLIGHT_TIME[level] * rng.uniform(0.6, 1.0))
        failed = not bot_returns(bot, aim, power, rng)
        tags = ["all"]
        if abs(aim) < 0.3 and power < 0.5:
            tags.append("center & weak")
        if abs(aim) > 0.7:
            tags.append("corner (|aim|>0.7)")
        if power > game.SMASH_POWER:
            tags.append("smash")
        for k in tags:
            kinds[k][0] += failed
            kinds[k][1] += 1
    return {k: f / max(n, 1) for k, (f, n) in kinds.items()}


def play_point(level, p_hit, rng):
    """True if you win the point. The bot serves."""
    bot = bot_for(level)
    flight = game.FLIGHT_TIME[level]
    while True:
        recenter(bot, flight)
        if rng.random() >= p_hit:
            return False                      # you missed
        if not bot_returns(bot, *random_shot(rng), rng):
            return True                       # bot missed
        flight = max(game.MIN_FLIGHT, flight * game.SPEEDUP[level])


def play_match(level, p_hit, rng):
    me = bot = 0
    while not ((me >= game.POINTS_TO_WIN or bot >= game.POINTS_TO_WIN) and abs(me - bot) >= game.WIN_BY):
        if play_point(level, p_hit, rng):
            me += 1
        else:
            bot += 1
    return me > bot


def main():
    rng = random.Random(0)
    for level in ("EASY", "MEDIUM", "HARD"):
        stats = shot_stats(level, rng)
        print(f"\n{level} ({game.BOT_NAME[level]}): bot fails to return  " +
              ",  ".join(f"{k} {v:.0%}" for k, v in stats.items()))
        for p_hit in (0.9, 0.6):
            points = sum(play_point(level, p_hit, rng) for _ in range(4000)) / 4000
            matches = sum(play_match(level, p_hit, rng) for _ in range(MATCHES // 4)) / (MATCHES // 4)
            print(f"   you hit {p_hit:.0%} of balls: you win {points:.0%} of points, {matches:.0%} of games")


if __name__ == "__main__":
    main()
