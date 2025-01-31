# pylint: disable=missing-module-docstring,missing-class-docstring,missing-function-docstring
import numpy as np
from ....backends_fixture import backend_class
from .displacement_settings import DisplacementSettings

assert hasattr(backend_class, '_pytestfixturefunction')


class TestExplicitEulerWithInterpolation:

    @staticmethod
    # pylint: disable=redefined-outer-name
    def test_single_cell(backend_class):
        # Arrange
        settings = DisplacementSettings()
        settings.courant_field_data = (np.array([[.1, .2]]).T, np.array([[.3, .4]]))
        settings.positions = [[0.5], [0.5]]
        sut, _ = settings.get_displacement(backend_class, scheme='ImplicitInSpace')

        # Act
        sut()

        # Assert

    @staticmethod
    # pylint: disable=redefined-outer-name
    def test_advection(backend_class):
        # Arrange
        settings = DisplacementSettings()
        settings.grid = (3, 3)
        settings.courant_field_data = (np.ones((4, 3)), np.zeros((3, 4)))
        settings.positions = [[1.5], [1.5]]
        sut, particulator = settings.get_displacement(backend_class, scheme='ImplicitInSpace')

        # Act
        sut()

        # Assert
        dim_x = 0
        np.testing.assert_array_equal(
            particulator.attributes['cell origin'][:, dim_x],
            np.array([2, 1])
        )

    @staticmethod
    # pylint: disable=redefined-outer-name
    def test_calculate_displacement(backend_class):
        # Arrange
        settings = DisplacementSettings()
        value_a = .1
        value_b = .2
        weight = .25
        settings.courant_field_data = (np.array([[value_a, value_b]]).T, np.array([[0, 0]]))
        settings.positions = [[weight], [0]]
        sut, particulator = settings.get_displacement(backend_class, scheme='ExplicitInSpace')

        # Act
        sut.calculate_displacement(sut.displacement, sut.courant,
                                   particulator.attributes['cell origin'],
                                   particulator.attributes['position in cell'])

        # Assert
        np.testing.assert_equal(
            sut.displacement[0, slice(0, 1)].to_ndarray(),
            (1 - weight) * value_a + weight * value_b
        )

    @staticmethod
    # pylint: disable=redefined-outer-name
    def test_calculate_displacement_dim1(backend_class):
        # Arrange
        settings = DisplacementSettings()
        value_a = .1
        value_b = .2
        weight = .25
        settings.courant_field_data = (np.array([[0, 0]]).T, np.array([[value_a, value_b]]))
        settings.positions = [[0], [weight]]
        sut, particulator = settings.get_displacement(backend_class, scheme='ExplicitInSpace')

        # Act
        sut.calculate_displacement(
            sut.displacement, sut.courant,
            particulator.attributes['cell origin'], particulator.attributes['position in cell']
        )

        # Assert
        np.testing.assert_equal(
            sut.displacement[1, slice(0, 1)].to_ndarray(),
            (1 - weight) * value_a + weight * value_b
        )

    @staticmethod
    # pylint: disable=redefined-outer-name
    def test_update_position(backend_class):
        # Arrange
        settings = DisplacementSettings()
        p_x = .1
        p_y = .2
        settings.positions = [[p_x], [p_y]]
        sut, particulator = settings.get_displacement(backend_class, scheme='ImplicitInSpace')

        droplet_id = slice(0, 1)
        sut.displacement[:] = particulator.backend.Storage.from_ndarray(np.asarray([[.1,], [.2]]))

        # Act
        sut.update_position(particulator.attributes['position in cell'], sut.displacement)

        # Assert
        for d in range(2):
            np.testing.assert_array_almost_equal(
                particulator.attributes['position in cell'][d, droplet_id].to_ndarray(),
                settings.positions[d][droplet_id] + sut.displacement[d, droplet_id].to_ndarray()
            )

    @staticmethod
    # pylint: disable=redefined-outer-name
    def test_update_cell_origin(backend_class):
        # Arrange
        settings = DisplacementSettings()
        sut, particulator = settings.get_displacement(backend_class, scheme='ImplicitInSpace')

        droplet_id = 0
        state = particulator.attributes
        state['position in cell'][:] = particulator.backend.Storage.from_ndarray(
            np.asarray([[1.1], [1.2]]))

        # Act
        sut.update_cell_origin(state['cell origin'], state['position in cell'])

        # Assert
        for d in range(2):
            assert state['cell origin'][d, droplet_id] == settings.positions[d][droplet_id] + 1
            assert state['position in cell'][d, droplet_id] == (
                state['position in cell'][d, droplet_id]
                -
                np.floor(state['position in cell'][d, droplet_id])
            )

    @staticmethod
    # pylint: disable=redefined-outer-name
    def test_boundary_condition(backend_class):
        # Arrange
        settings = DisplacementSettings()
        sut, particulator = settings.get_displacement(backend_class, scheme='ImplicitInSpace')

        droplet_id = 0
        state = particulator.attributes
        state['cell origin'][:] = particulator.backend.Storage.from_ndarray(np.asarray([[1], [1]]))

        # Act
        sut.boundary_condition(state['cell origin'])

        # Assert
        assert state['cell origin'][0, droplet_id] == 0
        assert state['cell origin'][1, droplet_id] == 0
