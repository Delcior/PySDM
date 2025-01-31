"""
random number generator class for Numba backend
"""
import numpy as np


#  TIP: can be called asynchronously
#  TIP: sometimes only half array is needed

class Random:  # pylint: disable=too-few-public-methods
    def __init__(self, size, seed):
        self.size = size
        self.generator = np.random.default_rng(seed)

    def __call__(self, storage):
        storage.data[:] = self.generator.uniform(0, 1, storage.shape)
