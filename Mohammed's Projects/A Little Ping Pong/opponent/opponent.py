# The virtual opponent for game.py: where your return lands, how fast it flies,
# and the bot's paddle chasing it with a PD controller. No drawing, no game flow -
# so game.py and the tuning simulation (tune_opponent.py) use exactly the same logic.
#
# Positions are table u (0 = left edge, 1 = right edge on screen) at the far end.
import random


def swing_power(peak_acc_diff, peak_gyro, acc_full, gyro_full):
    """0..1 swing power: the stronger of acc diff and gyro, each scaled so 'full' = 1."""
    return max(0.0, min(1.0, max(peak_acc_diff / acc_full, peak_gyro / gyro_full)))


def plan_return(aim, power, aim_spread, aim_noise, slow, fast, smash_power, smash_speedup, rng=random):
    """Your return shot: (landing u at the bot's end, flight time, is_smash).

    aim: -1..1, your paddle center's left/right offset from the ring center in ring
         radii (like Pong: hit off-center to send it toward a corner).
    power: 0..1, weak = slow, strong = fast; above smash_power it's a SMASH (even faster).
    """
    land = 0.5 + aim * aim_spread + rng.uniform(-aim_noise, aim_noise)
    land = min(max(land, 0.03), 0.97)
    flight = slow + (fast - slow) * power
    smash = power > smash_power
    if smash:
        flight *= smash_speedup
    return land, flight, smash


class Opponent:
    """Bot paddle on the far end: x moves toward a target with a PD controller,
    acceleration = kp * (target - x) - kd * v, speed limited to max_speed.
    It only starts chasing after its reaction delay; before that it just coasts to a stop."""

    def __init__(self, kp, kd, max_speed, reaction, catch_radius, miss_chance):
        self.kp, self.kd, self.max_speed = kp, kd, max_speed
        self.reaction, self.catch_radius, self.miss_chance = reaction, catch_radius, miss_chance
        self.x, self.v = 0.5, 0.0
        self.target = 0.5
        self.chase_from = 0.0

    def chase(self, target, now):
        """Your shot is coming to land at `target`: start chasing after the reaction delay."""
        self.target, self.chase_from = target, now + self.reaction

    def recenter(self, now):
        """Drift back to the middle (between shots), starting right away."""
        self.target, self.chase_from = 0.5, now

    def update(self, now, dt):
        if now >= self.chase_from:
            a = self.kp * (self.target - self.x) - self.kd * self.v
        else:
            a = -self.kd * self.v
        self.v = max(-self.max_speed, min(self.max_speed, self.v + a * dt))
        self.x = max(0.0, min(1.0, self.x + self.v * dt))

    def returns(self, land, rng=random):
        """Did the paddle get there? Within the catch radius, and not unlucky."""
        return abs(self.x - land) <= self.catch_radius and rng.random() >= self.miss_chance
