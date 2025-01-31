"""
groups of attributes used in either singular or time-dependent immmersion freezing regimes
"""
from collections import namedtuple


class SingularAttributes(namedtuple("SingularAttributes", (
    'freezing_temperature',
    'wet_volume'
))):
    """ groups attributes required in singular regime """
    __slots__ = ()


class TimeDependentAttributes(namedtuple("TimeDependentAttributes", (
    'immersed_surface_area',
    'wet_volume'
))):
    """ groups attributes required in time-dependent regime """
    __slots__ = ()
