from abstract_classes import Car, CarSpecification

CARS = {
    "Red Bull": Car(CarSpecification(power=740_000, drag=1.20, downforce=3.6)),
    "Ferrari": Car(CarSpecification(power=750_000, drag=1.25, downforce=3.4)),
    "McLaren": Car(CarSpecification(power=740_000, drag=1.24, downforce=3.9)),
    "Mercedes": Car(CarSpecification(power=750_000, drag=1.18, downforce=3.2)),
}
