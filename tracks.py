from abstract_classes import Track, Straight, Corner


class Monza(Track):
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
