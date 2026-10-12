"""Tracks: V0's Monza (kept unchanged as MonzaV0 for the regression tests) and V9's approximate real circuits.

A Circuit is an approximation built from public, estimated information, not surveyed geometry:

- Lap length, race laps, corner types and many minimum corner speeds come from F1-Encyclopedia by LordZeusIsBack,
  https://github.com/LordZeusIsBack/F1-Encyclopedia (files 03, 05, 15-17, 20, 23; most speeds there are labelled
  [Estimate]). Lines marked "# E" use one of its speeds (the middle of its range). Unmarked corner speeds, angles and
  straight lengths are estimates by the V9 author, made from general knowledge of each layout.
- Facts missing from the encyclopedia, or wrong in it, come from Wikipedia (noted on each class).
- Each corner's radius follows from its minimum speed and the lateral g the encyclopedia gives for that speed class
  (radius_for), so radii never depend on this simulator's car model.
- Straights are then scaled by one factor per circuit so the lap matches the official length (straight_scale shows how
  far the estimated straights were off). Elevation is given as metres of rise, kept when a straight is scaled, and sums
  to zero over a lap.
"""
import math
from abc import abstractmethod
from bisect import bisect_right

from abstract_classes import Chicane, Corner, Esses, Hairpin, Spiral, Straight, Track, TrackSegment
from physics import G


class MonzaV0(Track):
    """The V0 layout (5900 m, rough radii). Kept so the V0-V5 regression tests keep guarding the simulator itself."""

    def build_track(self):
        self.segments = [
            Straight(1210, float('inf'), 0),
            Corner(45, 14, 0),
            Straight(20, float('inf'), 0),
            Corner(50, 17, 0.3),
            Straight(110, float('inf'), 0.5),
            Corner(630, 340, 1.1),
            Straight(450, float('inf'), 0.5),
            Corner(45, 20, 0.2),
            Straight(20, float('inf'), 0),
            Corner(45, 24, 0),
            Straight(280, float('inf'), 0.7),
            Corner(85, 52, 0.4),
            Straight(180, float('inf'), -0.2),
            Corner(80, 38, -0.6),
            Straight(410, float('inf'), -1.8),
            Corner(180, 620, -1.4),
            Straight(420, float('inf'), -1),
            Corner(65, 42, -0.2),
            Corner(75, 58, 0),
            Corner(80, 75, 0.2),
            Straight(980, float('inf'), 0.2),
            Corner(440, 95, 0)
        ]


# F1-Encyclopedia 03_Corners_Technical_Taxonomy.md section 2, "Speed Classification Table" [Estimate]:
# (middle of each class's minimum-speed range in km/h, middle of its lateral-g range)
LATERAL_G = ((62.5, 2.0), (87.5, 2.5), (115.0, 3.0), (145.0, 3.6), (180.0, 4.25), (225.0, 5.0), (275.0, 5.75))


def radius_for(speed: float) -> float:
    """m: the radius on which a car at `speed` km/h pulls the encyclopedia's lateral g for that speed (interpolated
    between class midpoints, held constant beyond the slowest and fastest class)."""
    speeds = [s for s, _ in LATERAL_G]
    i = min(max(bisect_right(speeds, speed), 1), len(speeds) - 1)
    (s0, g0), (s1, g1) = LATERAL_G[i - 1], LATERAL_G[i]
    g = g0 + (g1 - g0) * min(max((speed - s0) / (s1 - s0), 0.0), 1.0)
    v = speed / 3.6
    return v * v / (g * G)


def _gradient(rise: float, length: float) -> float:
    return 100 * rise / length


def straight(length: float, rise: float = 0.0) -> Straight:
    return Straight(length, math.inf, _gradient(rise, length))


def turn(speed: float, angle: float, rise: float = 0.0, banking: float = 0.0) -> Corner:
    """A constant-radius corner taken at `speed` km/h at its slowest, turning `angle` degrees."""
    radius = radius_for(speed)
    length = math.radians(angle) * radius
    return Corner(length, radius, _gradient(rise, length), banking)


def hairpin(speed: float, angle: float = 180.0, rise: float = 0.0) -> Hairpin:
    radius = radius_for(speed)
    return Hairpin(radius, _gradient(rise, math.radians(angle) * radius), angle)


def chicane(*speeds: float, angle: float = 50.0, rise: float = 0.0) -> Chicane:
    """One element per speed, each turning `angle` degrees; the rise is shared out evenly."""
    return Chicane(*(turn(speed, angle, rise / len(speeds)) for speed in speeds))


def esses(*speeds: float, angle: float = 35.0, rise: float = 0.0) -> Esses:
    return Esses(*(turn(speed, angle, rise / len(speeds)) for speed in speeds))


def spiral(entry: float, exit: float, angle: float, rise: float = 0.0) -> Spiral:
    """Radius going from the entry-speed radius to the exit-speed radius. With curvature linear in distance, the turn
    angle is length x mean curvature, which fixes the length."""
    r1, r2 = radius_for(entry), radius_for(exit)
    length = 2 * math.radians(angle) / (1 / r1 + 1 / r2)
    return Spiral(length, r1, r2, _gradient(rise, length))


class Circuit(Track):
    """A real circuit, approximated (see the module docstring). Class attributes are its metadata."""
    official_length: float  # m, lap length
    laps: int  # Grand Prix race distance in laps
    lap_record: float | None = None  # s, race lap record: a sanity check only (other cars, other years)
    rain_chance = 0.25  # chance of a shower during a race: model assumption, used by rl.env
    neutralisation_chance = 0.5  # chance of a VSC or safety car during a race: model assumption, used by rl.env
    pit_loss: float | None = None  # s, measured pit loss; None: rl.env uses a generic value
    tyre_wear = 1.0  # multiplier on every compound's wear per lap: model assumption, used by rl.env

    @abstractmethod
    def layout(self) -> list[TrackSegment]:
        """Segments from the start/finish line, with estimated straight lengths."""

    def build_track(self):
        layout = self.layout()
        straights = sum(segment.length for segment in layout if isinstance(segment, Straight))
        corners = sum(segment.length for segment in layout) - straights
        if not 0 < corners < self.official_length or straights <= 0:
            raise ValueError(f"{self.name}: corners ({corners:.0f} m) must fit inside the lap")
        self.straight_scale = (self.official_length - corners) / straights
        self.segments = [Straight(s.length * self.straight_scale, math.inf, s.gradient / self.straight_scale)
                         if isinstance(s, Straight) else s for s in layout]


STREET = 0.7  # neutralisation chance on street circuits (F1-Encyclopedia 20, 15.1: "safety car period very likely")
WET = 0.4  # rain chance at the encyclopedia's wet-weather-prone circuits (20, 15.13)
DESERT = 0.05  # rain chance at desert venues, model assumption
DEMANDING = 1.2  # tyre wear at the encyclopedia's seven most tyre-demanding circuits (20, section 9), model assumption
GENTLE = 0.8  # tyre wear where the encyclopedia reports very low degradation (Albert Park), model assumption


# ---- Europe (F1-Encyclopedia 15) --------------------------------------------------------------------------------

class Monza(Circuit):
    """Autodromo Nazionale Monza, Italian GP. Straights from the encyclopedia: main ~1155 m, back ~1050 m, Ascari to
    Parabolica ~800 m. The encyclopedia names Hamilton 2020 as the record holder; 1:21.046 was Barrichello's, 2004."""
    official_length, laps, lap_record = 5793.0, 53, 81.046
    pit_loss = 25.62  # measured: V6 calibration, median of the 2024 stops (validation/config/calibrated.json)

    def layout(self):
        return [
            straight(600),
            chicane(92, 140, angle=75),  # E Prima Variante, minimum 85-100, exit 130-150
            straight(160),
            turn(258, 100),  # E Curva Grande 245-270
            straight(620),
            chicane(120, 120, angle=65),  # E Seconda Variante 110-130
            straight(290),
            turn(155, 85),  # E Lesmo 1 145-165
            straight(170),
            turn(140, 75),  # E Lesmo 2 130-150
            straight(1000),
            chicane(190, 130, 180, angle=40),  # E Ascari, minimum 120-140
            straight(800),
            spiral(108, 225, 180),  # E Parabolica: minimum 95-120, opening to the 210-240 exit
            straight(555),
        ]


class Spa(Circuit):
    """Circuit de Spa-Francorchamps, Belgian GP. About 100 m of elevation change (encyclopedia 20, section 6)."""
    official_length, laps, lap_record = 7004.0, 44, 106.286
    rain_chance = WET

    def layout(self):
        return [
            straight(240, rise=5),
            hairpin(82, 160),  # E La Source 75-90
            straight(450, rise=-25),
            esses(282, 282, 282, angle=25, rise=30),  # E Eau Rouge / Raidillon 270-295
            straight(900, rise=15),  # Kemmel
            chicane(162, 175, angle=60),  # E Les Combes 150-175
            turn(158, 70),  # E Malmedy 150-165
            straight(250, rise=-15),
            hairpin(78, 150),  # E Rivage 70-85
            straight(300, rise=-20),
            turn(130, 80),
            straight(350, rise=-25),
            turn(242, 120),  # E Pouhon 230-255
            straight(300, rise=-10),
            chicane(190, 200, angle=40),  # Fagnes
            straight(200, rise=-10),
            turn(180, 80),  # E Paul Frere 170-190
            straight(650, rise=30),
            turn(285, 40),  # E Blanchimont 270-300
            straight(450, rise=20),
            chicane(90, 100, angle=70),  # E Bus Stop 80-100
            straight(120, rise=5),
        ]


class Silverstone(Circuit):
    """Silverstone, British GP. Hangar straight ~0.7 km (encyclopedia 20, section 4)."""
    official_length, laps, lap_record = 5891.0, 52, 87.097
    rain_chance, tyre_wear = WET, DEMANDING

    def layout(self):
        return [
            straight(330),
            esses(190, 240, angle=30),  # E Abbey / Farm 180-200
            straight(230),
            turn(102, 80),  # E Village 95-110
            straight(90),
            hairpin(78, 150),  # E The Loop 70-85
            straight(140),
            turn(140, 60),  # E Aintree 130-150
            straight(700),  # Wellington
            turn(122, 110),  # E Brooklands 115-130
            straight(80),
            turn(95, 170),  # E Luffield 85-105
            straight(120),
            turn(230, 30),  # Woodcote
            straight(500),
            turn(270, 90),  # E Copse 255-285
            straight(350),
            esses(260, 260, 260, 260, angle=35),  # E Maggotts / Becketts / Chapel 245-275
            straight(770),  # Hangar
            turn(175, 90),  # E Stowe 165-185
            straight(400),
            chicane(185, 200, angle=80),  # E Vale 175-195, Club 185-215
            straight(300),
        ]


class Monaco(Circuit):
    """Circuit de Monaco. Lap record from Wikipedia (the encyclopedia gives none). About 40 m of elevation change."""
    official_length, laps, lap_record = 3337.0, 78, 72.909
    neutralisation_chance = STREET

    def layout(self):
        return [
            straight(150),
            turn(90, 90),  # E Sainte Devote 85-95
            straight(450, rise=30),  # Beau Rivage
            turn(128, 70, rise=8),  # E Massenet 120-135
            straight(70),
            turn(95, 70),  # E Casino 90-100
            straight(150, rise=-10),
            turn(85, 110),  # E Mirabeau Haute 80-90
            straight(80, rise=-8),
            hairpin(50, 180),  # E Grand Hotel hairpin 45-55
            straight(70, rise=-8),
            turn(80, 90),  # Mirabeau Bas
            straight(80, rise=-12),
            turn(92, 90),  # E Portier 85-100
            straight(450),  # tunnel
            chicane(58, 70, angle=60),  # E Nouvelle Chicane 50-65
            straight(150),
            turn(140, 40),  # E Tabac 130-150
            straight(150),
            chicane(200, 95, angle=35),  # E Swimming Pool, minimum 90-100
            straight(80),
            chicane(110, 110, angle=40),
            straight(100),
            turn(55, 120),  # E Rascasse 50-60
            straight(60),
            turn(120, 90),  # E Anthony Noghes 110-130
            straight(250),
        ]


class Barcelona(Circuit):
    """Circuit de Barcelona-Catalunya, the encyclopedia's 4.675 km layout with the T14-T15 chicane."""
    official_length, laps, lap_record = 4675.0, 66, 78.149
    tyre_wear = DEMANDING

    def layout(self):
        return [
            straight(600),
            chicane(155, 162, angle=50),  # E T1 145-165, T2 155-170
            turn(230, 100),
            straight(250),
            turn(172, 90),  # E Repsol 165-180
            straight(250),
            turn(120, 100),  # Seat
            straight(150),
            turn(180, 60),  # E T6 170-190
            straight(250),
            turn(185, 90),  # E Campsa 175-195
            straight(600),
            hairpin(92, 140),  # E La Caixa 85-100
            straight(250),
            turn(160, 70),
            straight(200),
            turn(175, 120),  # E banked T13 165-185 (banking not documented, so left flat)
            straight(150),
            chicane(145, 145, angle=60),  # E chicane 135-155
            straight(80),
            turn(142, 60),  # E T16 130-155
            straight(400),
        ]


class Zandvoort(Circuit):
    """Circuit Zandvoort, Dutch GP. Banking from Wikipedia: Hugenholtz (T3) 19 degrees, Arie Luyendyk (T14) 18 degrees
    (the encyclopedia confirms both corners are banked but gives no angle)."""
    official_length, laps, lap_record = 4259.0, 72, 71.097

    def layout(self):
        return [
            straight(400),
            hairpin(90, 170),  # E Tarzan 80-100
            straight(80),
            turn(182, 60),  # E Gerlach 175-190
            straight(150),
            turn(165, 160, banking=19),  # E Hugenholtz 155-175
            straight(250),
            esses(210, 200, angle=40),  # E sector 2, 180-240
            straight(200),
            turn(230, 50),
            straight(250),
            chicane(220, 115, 130, angle=50),  # E T7-T9, minimum 100-130
            straight(300),
            turn(120, 90),
            esses(230, 210, angle=35),  # E T10-T13, 195-265
            straight(400),
            turn(172, 120, banking=18),  # E Arie Luyendyk 165-180
            straight(280),
        ]


class RedBullRing(Circuit):
    """Red Bull Ring, Austrian GP. About 65 m of elevation change. The encyclopedia's corner numbers do not match the
    layout beyond T1, T9 and T10, so the other corner speeds are estimates."""
    official_length, laps, lap_record = 4318.0, 71, 65.619

    def layout(self):
        return [
            straight(300, rise=8),
            turn(100, 90, rise=2),  # E T1 90-110
            straight(150, rise=10),
            turn(230, 20),
            straight(650, rise=25),
            hairpin(70, 150),  # Remus
            straight(750, rise=-35),
            turn(105, 110),  # Schlossgold
            straight(300, rise=-10),
            turn(225, 70),
            straight(150),
            turn(190, 120),
            straight(200),
            turn(165, 110),
            straight(150),
            turn(155, 90),
            straight(400),
            turn(185, 90),  # E T9 175-195
            straight(200),
            turn(185, 100),  # E T10 175-195
            straight(500),
        ]


class Hungaroring(Circuit):
    """Hungaroring, Hungarian GP."""
    official_length, laps, lap_record = 4381.0, 70, 76.627
    tyre_wear = DEMANDING

    def layout(self):
        return [
            straight(500),
            turn(140, 160),  # E T1 130-150
            straight(250, rise=-15),
            turn(162, 140),  # E T2 155-170
            straight(150),
            turn(175, 60),  # E T3-T4 155-200
            straight(400, rise=15),
            turn(180, 70),  # E T3-T4 155-200
            straight(300),
            turn(205, 120),  # E T5 195-215
            straight(250),
            chicane(125, 125, angle=60),  # E T6 115-135
            straight(150),
            turn(205, 80),  # E T8 195-215
            straight(100),
            turn(85, 100),  # E T9 75-95
            straight(250),
            turn(160, 60),  # E T10-T12 100-180
            straight(150),
            turn(140, 70),  # E T10-T12 100-180
            straight(250),
            turn(100, 80),  # E T10-T12 100-180
            straight(200),
            turn(110, 120),  # E T13 100-120
            straight(100),
            turn(110, 100),  # E T14 100-120
            straight(400),
        ]


class Imola(Circuit):
    """Autodromo Enzo e Dino Ferrari, Emilia Romagna GP. Lap record from Wikipedia: the encyclopedia's 1:24.170
    (Barrichello, 2004) does not match the current layout's record."""
    official_length, laps, lap_record = 4909.0, 63, 75.484

    def layout(self):
        return [
            straight(600),
            chicane(125, 140, 125, angle=45),  # E Tamburello 115-135
            straight(450),
            chicane(110, 120, angle=50),  # E Villeneuve 100-120
            straight(250),
            hairpin(72, 150),  # E Tosa 65-80
            straight(400, rise=20),
            turn(195, 60),  # E Piratella 185-205
            straight(250, rise=-25),
            esses(140, 160, angle=60),  # E Acque Minerali 130-150
            straight(350, rise=15),
            chicane(90, 100, angle=55),  # E Variante Alta 80-100
            straight(500, rise=-10),
            turn(100, 80),  # E Rivazza 1, 90-110
            turn(100, 90),  # E Rivazza 2, 90-110
            straight(500),
        ]


class Madrid(Circuit):
    """Madring, Spanish GP from 2026. The encyclopedia predates the race and gives ~5.47-5.5 km and no corner data, so
    length, 22 turns, La Monumental's 13.5-degree banking cap and the 2026 lap record are from Wikipedia. Laps: the
    fewest that exceed 305 km. The layout is the least certain of all circuits here."""
    official_length, laps, lap_record = 5414.0, 57, 95.587
    neutralisation_chance = STREET

    def layout(self):
        return [
            straight(700),
            turn(90, 90),
            straight(200),
            chicane(130, 140, angle=50),
            straight(300),
            turn(170, 60),
            straight(400),
            chicane(100, 110, angle=60),
            straight(250),
            turn(200, 50),
            straight(400),
            turn(95, 100),
            straight(150),
            esses(150, 160, angle=50),
            straight(300),
            turn(185, 200, banking=13.5),  # La Monumental
            straight(300),
            turn(110, 90),
            straight(250),
            chicane(120, 125, angle=55),
            straight(400),
            turn(150, 70),
            straight(200),
            esses(160, 170, angle=40),
            straight(250),
            turn(100, 90),
            straight(150),
            chicane(130, 140, angle=45),
            straight(150),
            turn(140, 70),
            straight(500),
        ]


class Istanbul(Circuit):
    """Istanbul Park, Turkish GP. Turn 8 is the encyclopedia's example of a compound, spiral, multi-apex corner. Laps:
    the fewest that exceed 305 km."""
    official_length, laps, lap_record = 5338.0, 58, 84.770

    def layout(self):
        return [
            straight(450),
            turn(120, 90, rise=-15),
            turn(140, 90, rise=-5),
            straight(250),
            turn(150, 70),
            straight(250),
            turn(130, 90),
            straight(200, rise=10),
            turn(170, 60),
            straight(250),
            turn(150, 90),
            straight(250),
            turn(175, 120),
            straight(250),
            spiral(260, 225, 270),  # E Turn 8, ~250 km/h, quad-apex, tightening
            straight(250),
            esses(160, 170, angle=50),
            straight(900),
            turn(90, 120),
            straight(250),
            turn(110, 90),
            straight(200, rise=10),
            chicane(95, 100, angle=60),
            straight(200),
            turn(140, 70),
            straight(400),
        ]


# ---- Americas (F1-Encyclopedia 16) ------------------------------------------------------------------------------

class COTA(Circuit):
    """Circuit of the Americas, United States GP. The encyclopedia: 30 m climb from the start line to the Turn 1
    hairpin, 41 m elevation change, main straight 1.2 km. Its corner numbers after T12 do not match the layout, so its
    back-hairpin speed is used for T15."""
    official_length, laps, lap_record = 5513.0, 56, 96.169
    tyre_wear = DEMANDING

    def layout(self):
        return [
            straight(300, rise=25),
            hairpin(75, 150, rise=3),  # E T1, apex ~75
            straight(150, rise=-10),
            turn(190, 50, rise=-5),
            esses(220, 210, 200, 200, angle=35, rise=-5),  # E T3-T6, 200-240 and T6 200
            turn(145, 60),  # E tighter esses 130-160
            turn(140, 70),
            turn(170, 50),
            straight(250),
            turn(180, 30),  # E T10-T11 170-190
            straight(100),
            hairpin(70, 160),
            straight(1000, rise=-8),
            turn(80, 90),  # E T12 apex ~80
            straight(150),
            esses(150, 165, angle=50),  # E T13-T15 150-180
            straight(80),
            hairpin(70, 160),  # E back hairpin ~70
            straight(150),
            spiral(170, 220, 220),
            straight(250),
            turn(240, 50),  # E T19 230-250
            straight(300),
            turn(80, 90),  # E T20 apex ~80
            straight(900),
        ]


class Miami(Circuit):
    """Miami International Autodrome, Miami GP."""
    official_length, laps, lap_record = 5412.0, 57, 89.708

    def layout(self):
        return [
            straight(450),
            turn(70, 100),  # E T1 apex ~70
            straight(100),
            turn(130, 70),  # E T2-T5 130-180
            straight(150),
            esses(170, 180, angle=40),  # E T2-T5 130-180
            straight(250),
            turn(215, 60),  # E T6-T10 200-230
            straight(200),
            turn(215, 80),  # E T6-T10 200-230
            straight(150),
            turn(215, 90),  # E T6-T10 200-230
            straight(400),
            turn(100, 90),
            straight(1250),
            chicane(120, 120, angle=60),
            straight(150),
            chicane(55, 60, angle=70),
            straight(150),
            turn(110, 80),
            straight(250),
            hairpin(75, 160),
            straight(600),
            turn(230, 40),
            straight(400),
        ]


class Mexico(Circuit):
    """Autodromo Hermanos Rodriguez, Mexican GP. Main straight ~0.8-1.0 km (encyclopedia 20, section 4)."""
    official_length, laps, lap_record = 4304.0, 71, 77.774

    def layout(self):
        return [
            straight(800),
            chicane(110, 200, 200, angle=45),  # E T2-T3 180-220
            straight(800),
            turn(170, 90),  # E T4 160-180
            straight(150),
            chicane(80, 90, angle=70),  # E T5-T6 apex ~80
            straight(350),
            esses(230, 240, 230, angle=30),
            straight(150),
            turn(150, 60),
            straight(150),
            turn(170, 90),
            straight(400),
            turn(110, 90),
            straight(200),
            esses(120, 120, angle=60),  # E stadium 100-140
            straight(150),
            turn(110, 80),
            straight(150),
            turn(265, 60),  # E Peraltada (modified) 250-280
            straight(400),
        ]


class Interlagos(Circuit):
    """Autodromo Jose Carlos Pace, Sao Paulo GP. About 40-50 m of elevation change (encyclopedia 20, section 6)."""
    official_length, laps, lap_record = 4309.0, 71, 70.540
    rain_chance = WET

    def layout(self):
        return [
            straight(250),
            esses(110, 140, angle=55, rise=-15),  # Senna S
            straight(150),
            turn(165, 90),  # E Curva do Sol 150-180
            straight(650, rise=-10),
            turn(115, 90, rise=-5),
            turn(160, 60),
            straight(250, rise=15),
            turn(180, 100),
            straight(150),
            turn(170, 120),  # Ferradura
            straight(150),
            turn(100, 90),
            straight(150),
            turn(80, 100),  # Pinheirinho
            straight(150),
            hairpin(70, 160),  # Bico de Pato
            straight(150),
            turn(160, 100, rise=-15),  # Mergulho
            straight(150),
            turn(110, 90),  # Juncao
            straight(1050, rise=30),
        ]


class LasVegas(Circuit):
    """Las Vegas Strip Circuit, Las Vegas GP."""
    official_length, laps, lap_record = 6201.0, 50, 95.490
    rain_chance, neutralisation_chance = DESERT, STREET

    def layout(self):
        return [
            straight(400),
            chicane(85, 110, 90, angle=60),
            straight(350),
            turn(200, 40),
            straight(400),
            hairpin(70, 160),  # E infield 70-100
            straight(700),
            chicane(100, 110, angle=60),
            turn(90, 90),
            straight(800),
            turn(100, 90),
            straight(400),
            turn(250, 30),
            straight(1900),  # the Strip
            chicane(65, 75, 70, angle=60),  # E end of the Strip, apex ~65
            straight(300),
            turn(120, 90),
            straight(500),
        ]


class Montreal(Circuit):
    """Circuit Gilles Villeneuve, Canadian GP."""
    official_length, laps, lap_record = 4361.0, 70, 73.078
    rain_chance = WET

    def layout(self):
        return [
            straight(300),
            turn(120, 60),
            hairpin(85, 150),  # E T1-T2 apex ~85
            straight(450),
            chicane(130, 140, angle=60),
            straight(350),
            turn(250, 30),
            straight(250),
            chicane(100, 120, angle=60),
            straight(400),
            chicane(105, 120, angle=50),
            straight(250),
            hairpin(65, 175),  # E hairpin apex ~65
            straight(1350),
            chicane(130, 100, angle=55),  # Wall of Champions chicane
            straight(450),
        ]


# ---- Asia, Pacific and Middle East (F1-Encyclopedia 17) ----------------------------------------------------------

class Bahrain(Circuit):
    """Bahrain International Circuit, Grand Prix layout."""
    official_length, laps, lap_record = 5412.0, 57, 91.447
    rain_chance, tyre_wear = DESERT, DEMANDING

    def layout(self):
        return [
            straight(550),
            hairpin(80, 140),  # E T1 apex ~80
            straight(80),
            turn(165, 60),  # E T2-T3 150-180
            straight(150),
            turn(250, 30),
            straight(550),
            turn(185, 90),  # E T4 170-200
            straight(300),
            esses(155, 155, 150, angle=40),  # E T5-T8 130-170
            straight(150),
            turn(150, 110),  # E T7-T8 130-170
            straight(200),
            hairpin(75, 150),  # E back hairpin apex ~75
            straight(200),
            turn(150, 60),  # E T10 ~150
            straight(500),
            turn(110, 90),  # E T11-T12, ~110
            straight(300),
            turn(250, 40),
            straight(400),
            turn(80, 90),  # E T13 apex ~80
            straight(600),
            turn(130, 90),  # E T14-T16 100-160
            turn(130, 60),  # E T14-T16 100-160
            straight(550),
        ]


class Jeddah(Circuit):
    """Jeddah Corniche Circuit, Saudi Arabian GP. Turn 13's ~12-degree banking is an estimate (not in the encyclopedia)."""
    official_length, laps, lap_record = 6174.0, 50, 90.734
    rain_chance, neutralisation_chance = DESERT, STREET

    def layout(self):
        return [
            straight(500),
            chicane(100, 115, angle=60),
            straight(200),
            turn(170, 70),
            esses(250, 285, 250, 285, 260, angle=25),  # E high-speed section 280-290
            straight(400),
            esses(240, 250, 240, angle=30),
            straight(300),
            turn(150, 150, banking=12),
            straight(600),
            esses(285, 285, angle=20),  # E 280-290
            straight(400),
            esses(285, 285, angle=20),  # E 280-290
            straight(400),
            chicane(160, 170, angle=40),
            straight(600),
            turn(230, 40),
            straight(400),
            hairpin(90, 150),
            straight(400),
        ]


class Suzuka(Circuit):
    """Suzuka, Japanese GP (figure-of-eight; the crossover does not matter in a one-dimensional model)."""
    official_length, laps, lap_record = 5807.0, 53, 90.983
    rain_chance = WET

    def layout(self):
        return [
            straight(450),
            turn(245, 70),  # E First Curve 240-250
            turn(140, 90),
            straight(100),
            esses(260, 260, 260, 260, angle=35),  # E S-curves 250-270
            straight(150),
            turn(200, 90),  # E Dunlop ~200
            straight(300),
            esses(230, 160, angle=60),  # E Degner 220-240
            straight(450),
            hairpin(75, 170),  # E hairpin apex ~75
            straight(500),
            turn(270, 40),
            straight(250),
            turn(200, 150),  # E Spoon 180-220
            straight(1100),
            turn(300, 60),  # E 130R 290-310
            straight(250),
            chicane(90, 100, angle=60),  # E Casio Triangle apex ~90
            straight(300),
        ]


class Shanghai(Circuit):
    """Shanghai International Circuit, Chinese GP. Turns 1-2 are a tightening spiral."""
    official_length, laps, lap_record = 5451.0, 56, 92.238

    def layout(self):
        return [
            straight(400),
            spiral(270, 90, 270),  # E T1-T2, 260-280 tightening to ~90
            turn(90, 90),
            straight(250),
            turn(120, 90),  # E T4 110-130
            straight(200),
            turn(165, 80),  # E T5-T6 150-180
            straight(450),
            esses(230, 230, angle=35),
            turn(90, 90),  # E T7-T9 80-100
            straight(150),
            turn(145, 90),  # E T10-T11 130-160
            straight(150),
            turn(145, 60),  # E T10-T11 130-160
            straight(300),
            spiral(110, 240, 270),
            straight(1170),
            hairpin(70, 170),  # E T14 apex ~70
            straight(200),
            turn(100, 90),
            turn(130, 80),
            straight(500),
        ]


class Singapore(Circuit):
    """Marina Bay Street Circuit, Singapore GP, 2023-2024 layout. The encyclopedia's record is for an older layout, so
    the record is from Wikipedia. The encyclopedia: highest safety-car frequency on the calendar."""
    official_length, laps, lap_record = 4940.0, 62, 94.486
    neutralisation_chance, tyre_wear = 0.9, DEMANDING

    def layout(self):
        return [
            straight(500),
            chicane(75, 110, 90, angle=60),  # E T1 apex ~75
            straight(250),
            turn(140, 90),  # E financial district 100-180
            straight(200),
            turn(200, 40),
            straight(650),
            turn(100, 90),  # E financial district 100-180
            straight(250),
            turn(105, 90),  # E financial district 100-180
            straight(150),
            turn(110, 90),  # E financial district 100-180
            straight(300),
            turn(180, 40),  # E financial district 100-180
            straight(150),
            chicane(110, 115, angle=50),  # E financial district 100-180
            straight(150),
            hairpin(60, 160),
            straight(550),
            turn(95, 90),
            straight(200),
            chicane(130, 140, angle=45),
            straight(400),
            chicane(57, 60, angle=80),  # E slow hairpin complex 50-65
            straight(150),
            turn(150, 60),
            straight(450),
        ]


class Lusail(Circuit):
    """Lusail International Circuit, Qatar GP. The encyclopedia gives no corner speeds or banking angles for its
    banked sweepers, so every corner here is an estimate and is left flat."""
    official_length, laps, lap_record = 5380.0, 57, 84.319
    rain_chance = DESERT

    def layout(self):
        return [
            straight(650),
            turn(115, 90),
            straight(150),
            esses(195, 210, angle=35),
            straight(150),
            turn(225, 50),
            straight(150),
            turn(165, 90),
            straight(150),
            hairpin(100, 140),
            straight(300),
            esses(220, 230, 220, angle=30),
            straight(250),
            turn(115, 110),
            straight(350),
            esses(240, 250, 240, angle=30),
            straight(250),
            turn(230, 60),
            straight(150),
            turn(175, 80),
            straight(420),
        ]


class YasMarina(Circuit):
    """Yas Marina Circuit, Abu Dhabi GP, post-2021 layout."""
    official_length, laps, lap_record = 5281.0, 58, 86.103
    rain_chance = DESERT

    def layout(self):
        return [
            straight(350),
            turn(120, 90),
            straight(100),
            esses(210, 220, 200, angle=35),
            straight(150),
            hairpin(75, 170),  # E hairpin apex ~75
            straight(1150),
            chicane(85, 95, angle=70),
            straight(1100),
            turn(100, 90),
            straight(250),
            esses(160, 170, angle=50),
            straight(300),
            turn(170, 120),
            straight(200),
            turn(110, 90),
            straight(150),
            turn(110, 90),
            straight(200),
            turn(170, 90),
            straight(350),
        ]


class Baku(Circuit):
    """Baku City Circuit, Azerbaijan GP. The encyclopedia: ~2.0-2.2 km waterfront straight, castle section."""
    official_length, laps, lap_record = 6003.0, 51, 103.009
    neutralisation_chance, tyre_wear = STREET, DEMANDING

    def layout(self):
        return [
            straight(250),
            turn(90, 90),  # E T1 apex ~90
            straight(350),
            turn(90, 90),
            straight(300),
            turn(95, 90),
            straight(250),
            hairpin(50, 140),  # E castle hairpin ~50
            straight(120),
            chicane(90, 100, angle=70),
            straight(150),
            turn(80, 90),
            straight(100),
            chicane(70, 75, angle=50),  # castle
            straight(200, rise=20),
            turn(140, 60),  # E T7-T14 100-180
            straight(250),
            turn(120, 90),  # E T7-T14 100-180
            straight(150),
            turn(130, 90),  # E T7-T14 100-180
            straight(250),
            turn(150, 80),  # E T7-T14 100-180
            straight(300, rise=-20),
            turn(120, 90),
            straight(250),
            turn(110, 90),
            straight(2150),
        ]


class AlbertPark(Circuit):
    """Albert Park, Australian GP, layout revised for 2022."""
    official_length, laps, lap_record = 5278.0, 58, 80.235
    tyre_wear = GENTLE

    def layout(self):
        return [
            straight(450),
            esses(110, 160, angle=45),  # E T1 apex ~110
            straight(350),
            turn(180, 90),  # E T3 170-190
            straight(150),
            turn(160, 60),
            straight(300),
            turn(250, 40),
            straight(150),
            turn(200, 70),
            straight(400),
            esses(260, 260, angle=25),
            straight(650),
            chicane(180, 190, angle=35),
            straight(400),
            turn(130, 90),
            straight(150),
            turn(140, 80),
            straight(250),
            turn(95, 90),
            turn(130, 60),
            straight(500),
        ]


class Sepang(Circuit):
    """Sepang International Circuit, Malaysian GP 1999-2017. The encyclopedia gives no length, laps or record, so they
    are from Wikipedia (laps: the fewest that exceed 305 km). The encyclopedia: sudden heavy tropical rain."""
    official_length, laps, lap_record = 5543.0, 56, 94.080
    rain_chance = WET

    def layout(self):
        return [
            straight(450),
            turn(90, 90),
            hairpin(70, 160),
            straight(200),
            turn(200, 100),
            straight(450),
            turn(95, 90),
            straight(200),
            esses(250, 260, angle=30),
            straight(200),
            turn(170, 90),
            turn(140, 90),
            straight(300),
            hairpin(75, 160),
            straight(350),
            turn(180, 60),
            straight(150),
            turn(110, 100),
            straight(250),
            esses(250, 215, angle=40),
            straight(200),
            turn(95, 100),
            straight(900),
            hairpin(70, 180),
            straight(500),
        ]


class Buddh(Circuit):
    """Buddh International Circuit, Indian GP 2011-2013. The encyclopedia gives no length, laps or record, so they are
    from Wikipedia (laps: the fewest that exceed 305 km)."""
    official_length, laps, lap_record = 5125.0, 60, 87.249

    def layout(self):
        return [
            straight(400),
            turn(90, 90),
            straight(250),
            turn(180, 40),
            straight(1060),
            hairpin(75, 150),
            straight(350),
            turn(95, 90),
            straight(200),
            esses(155, 165, angle=50),
            straight(200),
            turn(170, 80),
            straight(150),
            esses(220, 230, angle=30),
            straight(150),
            spiral(240, 180, 200),
            straight(300),
            turn(140, 90),
            straight(200),
            turn(140, 70),
            straight(200),
            turn(150, 60),
            straight(150),
            chicane(110, 120, angle=60),  # the encyclopedia's final chicane
            straight(450),
        ]


CIRCUITS: dict[str, type[Circuit]] = {circuit.__name__: circuit for circuit in Circuit.__subclasses__()}
