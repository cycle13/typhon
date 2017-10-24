# -*- encoding: utf-8 -*-
import numpy as np
import pytest

try:
    from typhon.arts.workspace import Workspace
except:
    skip_arts_tests = True
else:
    skip_arts_tests = False


@pytest.mark.skipif(skip_arts_tests, reason='ARTS library not available')
class TestWorkspace:
    def setup_method(self):
        """This ensures a new Workspace for every test."""
        self.ws = Workspace()

    def test_index_transfer(self):
        self.ws.IndexCreate("index_variable")
        i = np.random.randint(0, 100)
        self.ws.index_variable = i
        assert self.ws.index_variable.value == i

    def test_array_of_index_transfer(self):
        self.ws.ArrayOfIndexCreate("array_of_index_variable")
        i = [np.random.randint(0, 100) for j in range(10)]
        self.ws.array_of_index_variable = i
        assert self.ws.array_of_index_variable.value == i

    def test_string_transfer(self):
        self.ws.StringCreate("string_variable")
        s = "some random string."
        self.ws.string_variable = s
        assert self.ws.string_variable.value == s

    def test_vector_transfer(self):
        self.ws.VectorCreate("vector_variable")
        v = np.random.rand(10)
        self.ws.vector_variable = v
        assert all(self.ws.vector_variable.value == v)

    def test_matrix_transfer(self):
        self.ws.MatrixCreate("matrix_variable")
        m = np.random.rand(10, 10)
        self.ws.matrix_variable = m
        assert all(self.ws.matrix_variable.value.ravel() == m.ravel())

    def test_supergeneric_overload_resolution(self):
        self.ws.ArrayOfIndexCreate("array_of_index")
        self.ws.ArrayOfArrayOfIndexCreate("array_of_array_of_index")
        self.ws.array_of_index = [1, 2, 3]
        self.ws.Append(self.ws.array_of_array_of_index, self.ws.array_of_index)
        self.ws.Append(self.ws.array_of_array_of_index, self.ws.array_of_index)

    def test_creation(self):
        self.ws.ArrayOfIndexCreate("array_of_index")
        self.ws.ArrayOfIndexCreate("array_of_index")