# pylint: disable=missing-module-docstring,missing-class-docstring,missing-function-docstring
import pytest
import numpy as np

from PySDM_examples.Yang_et_al_2018 import Simulation, Settings
from PySDM.physics.constants import si
from PySDM.backends.impl_numba.test_helpers import bdf
from PySDM.backends import CPU, GPU

#  TODO #527
# from ...backends_fixture import backend_class
# assert hasattr(backend_class, '_pytestfixturefunction')


@pytest.mark.parametrize("scheme", ('default', 'BDF'))
@pytest.mark.parametrize("adaptive", (True, False))
# pylint: disable=redefined-outer-name
def test_just_do_it(scheme, adaptive, backend_class=CPU):
    # Arrange
    if scheme == 'BDF' and (not adaptive or backend_class is GPU):
        return

    settings = Settings(dt_output=10 * si.second)
    settings.adaptive = adaptive
    if scheme == 'BDF':
        settings.dt_max = settings.dt_output  # TODO #334 'BDF')
    elif not adaptive:
        settings.dt_max = 1 * si.second

    simulation = Simulation(settings, backend_class)
    if scheme == 'BDF':
        bdf.patch_particulator(simulation.particulator)

    # Act
    output = simulation.run()
    r = np.array(output['r']).T * si.metres
    n = settings.n / (settings.mass_of_dry_air * si.kilogram)

    # Assert
    condition = (r > 1 * si.micrometre)
    NTOT = n_tot(n, condition)
    N1 = NTOT[: int(1/3 * len(NTOT))]
    N2 = NTOT[int(1/3 * len(NTOT)): int(2/3 * len(NTOT))]
    N3 = NTOT[int(2/3 * len(NTOT)):]

    n_unit = 1/si.microgram
    assert min(N1) == 0.0 * n_unit
    assert .6 * n_unit < max(N1) < .8 * n_unit
    assert .17 * n_unit < min(N2) < .18 * n_unit
    assert .35 * n_unit < max(N2) < .41 * n_unit
    assert .1 * n_unit < min(N3) < .11 * n_unit
    assert .27 * n_unit < max(N3) < .4 * n_unit

    # TODO #527
    if backend_class is not GPU:
        assert max(output['ripening rate']) > 0


def n_tot(n, condition):
    return np.dot(n, condition)
