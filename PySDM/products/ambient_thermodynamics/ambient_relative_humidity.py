"""
ambient relative humidity
"""
from PySDM.products.impl.moist_environment_product import MoistEnvironmentProduct


class AmbientRelativeHumidity(MoistEnvironmentProduct):
    def __init__(self, name=None, unit='dimensionless', var=None):
        super().__init__(name=name, unit=unit, var=var)
