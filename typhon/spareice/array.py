"""Contains classes that extend the functionality of plain numpy ndarrays,
to bundle them in labeled groups and store them to netCDF4 files.
"""

from collections import defaultdict
import copy
import textwrap
import warnings

import numpy as np
import typhon.plots

try:
    from netCDF4 import Dataset, num2date, date2num
except ModuleNotFoundError:
    pass

try:
    import xarray as xr
except ModuleNotFoundError:
    pass

__all__ = [
    'Array',
    'ArrayGroup',
]


class Array(np.ndarray):
    """An extended numpy array with attributes and dimensions.

    """

    def __new__(cls, data, attrs=None, dims=None):
        obj = np.asarray(data).view(cls)

        if attrs is not None:
            obj.attrs = attrs

        if dims is not None:
            obj.dims = dims

        return obj

    def __array_finalize__(self, obj):
        if obj is None:
            return

        self.attrs = getattr(obj, 'attrs', {})
        self.dims = getattr(
            obj, 'dims',
            ["dim_%d" % i for i in range(len(self.shape))]
        )
        # self.dims = getattr(
        #     obj, 'dims',
        #     [None for _ in range(len(self.shape))]
        # )

    def __len__(self):
        return self.shape[0]

    def __str__(self):
        if self.shape[0] < 5:
            items = np.array_str(self[:self.shape[0]])
        else:
            items = ", ".join([
                np.array_str(self[0]), np.array_str(self[1]), ".. ",
                np.array_str(self[-2]), np.array_str(self[-1])])
        info = "[{}, dtype={}]".format(items, self.dtype)
        info += "\nDimensions: "
        info += ", ".join(
            ["%s (%d)" % (dim, self.shape[i])
             for i, dim in enumerate(self.dims)])
        info += "\nAttributes:\n"
        if self.attrs:
            for attr, value in self.attrs.items():
                info += "\t{} : {}\n".format(attr, value)
        else:
            info += "\t--\n"

        return info

    # def __repr__(self):
    #     return self.__str__()

    @classmethod
    def concatenate(cls, objects, dim=None):
        """Concatenate multiple Array objects together.

        The returned Array object contains the attributes and dimension labels
        from the first object in the list.

        TODO:
            Maybe this could be implemented via __array_wrap__ or
            __array_ufunc__?

        Args:
            objects: List of GeoData objects to concatenate.
            dim:

        Returns:
            An Array object.
        """
        concat_array = np.concatenate(objects, dim)
        array = Array(
            concat_array, objects[0].attrs, objects[0].dims
        )

        return array

    @classmethod
    def from_xarray(cls, xarray_object):
        return cls(xarray_object.data, xarray_object.attrs, xarray_object.dims)

    def to_xarray(self):
        return xr.DataArray(self, attrs=self.attrs, dims=self.dims)


class ArrayGroup:
    """A specialised dictionary for arrays.

    Still under development.
    """

    def __init__(self, name=None):
        """Initializes an ArrayGroup object.

        Args:
            name: Name of the ArrayGroup as string.
        """

        self.attrs = {}

        # All variables (excluding groups) will be saved into this dictionary:
        self._vars = {}

        # All groups will be saved here.
        self._groups = defaultdict(type(self))

        if name is None:
            self.name = "{}, {}:".format(type(self), id(self))
        else:
            self.name = name

    def __contains__(self, item):
        var, rest = self.parse(item)
        if var == "/":
            return True

        if var in self._vars:
            return True

        if var in self._groups:
            if rest:
                return rest in self[var]
            return True

        return False

    def __iter__(self):
        self._iter_vars = self.vars(deep=True)
        return self

    def __next__(self):
        return next(self._iter_vars)

    def __delitem__(self, key):
        var, rest = self.parse(key)

        # If the user tries to delete all variables:
        if not var:
            raise KeyError("The main group cannot be deleted. Use the clear "
                           "method to delete all variables and groups.")

        if rest:
            del self._vars[var][rest]
            return

        if var in self._vars:
            del self._vars[var]
        else:
            try:
                del self._groups[var]
            except KeyError:
                raise KeyError(
                    "Cannot delete! There is neither a variable nor group "
                    "named '{}'!".format(var))

    def __getitem__(self, item):
        """Enables dictionary-like access to the ArrayGroup.

        There are different ways to access one element of this ArrayGroup:

        * by *array_group["var"]*: returns a variable (Array) or group
            (ArrayGroup) object.
        * by *array_group["group/var"]*: returns the variable from the group
            object.
        * by *array_group["/"]*: returns this object itself.
        * by *array_group[0:10]*: returns a copy of the first ten elements
            for each variable in the ArrayGroup object. Note: all variables
            should have the same length.

        Args:
            item:

        Returns:
            Either an Array or an ArrayGroup object.
        """

        # Accessing via key:
        if isinstance(item, str):
            var, rest = self.parse(item)

            # All variables are requested (return the object itself)
            if not var:
                return self

            if not rest:
                if var in self._vars:
                    return self._vars[var]

                try:
                    return self._groups[var]
                except KeyError:
                    raise KeyError(
                        "There is neither a variable nor group named "
                        "'{}'!".format(var))
            else:
                if var in self._groups:
                    return self._groups[var][rest]
                else:
                    raise KeyError("'{}' is not a group!".format(var))
        else:
            # Selecting elements via slicing:
            return self.select(item, deep=True)

    def __setitem__(self, key, value):
        var, rest = self.parse(key)

        if not var:
            raise ValueError("You cannot change the main group directly!")

        if not rest:
            # Try automatic conversion from numpy array to Array.
            if not isinstance(value, (Array, ArrayGroup, type(self))):
                value = Array(value)

            if isinstance(value, Array):
                self._vars[var] = value

                # Maybe someone wants to create a variable with a name that
                # has been the name of a group earlier?
                if var in self._groups:
                    del self._groups[var]
            else:
                self._groups[var] = value

                # May be someone wants to create a group with a name that
                # has been the name of a variable earlier?
                if var in self._vars:
                    del self._vars[var]
        else:
            # Auto creation of groups
            if var not in self._groups:
                self._groups[var] = type(self)()

                # May be someone wants to create a group with a name that
                # has been the name of a variable earlier?
                if var in self._vars:
                    del self._vars[var]
            self._groups[var][rest] = value

    def __str__(self):
        info = "Name: {}\n".format(self.name)
        info += "  Attributes:\n"
        if self.attrs:
            for attr, value in self.attrs.items():
                info += "    {} : {}\n".format(attr, value)
        else:
            info += "    --\n"

        info += "  Groups:\n"
        if self._groups:
            for group in self.groups(deep=True):
                info += "    {}\n".format(group)
        else:
            info += "    --\n"

        info += "  Variables:\n"
        variables = list(self.vars(deep=True))
        if variables:
            coords = self.coords(deep=True)
            for var in variables:
                info += "    {}{}:\n{}".format(
                    var, " (coord)" if var in coords else "",
                    textwrap.indent(str(self[var]), ' ' * 6)
                )
        else:
            info += "  --\n"

        return info

    def bin(self, bins, fields=None, deep=False):
        """Bins all arrays in this object.

        Args:
            bins: List of lists which contain the indices for the bins.
            fields: Filter
            deep: Bins also the arrays of the subgroups.

        Returns:
            An ArrayGroup object with binned arrays.
        """
        new_data = type(self)()
        for var, data in self.items(deep):
            if fields is not None and var not in fields:
                continue
            binned_data = np.asarray([
                data[indices]
                for i, indices in enumerate(bins)
            ])
            new_data[var] = binned_data
        return new_data

    def collapse(self, bins, collapser=None,
                 variation_filter=None, deep=False):
        """Fills bins for each variables and apply a function to them.

        Args:
            bins: List of lists which contain the indices for the bins.
            collapser: Function that should be applied on each bin (
                numpy.nanmean is the default).
            variation_filter: Bins which exceed a certain variation limit
                can be excluded. For doing this, you must set this parameter to
                a tuple/list of at least two elements: field name and
                variation threshold. A third element is optional: the
                variation function (the default is numpy.nanstd).
            deep: Collapses also the variables of the subgroups.

        Returns:
            An ArrayGroup object.
        """
        # Default collapser is the mean function:
        if collapser is None:
            collapser = np.nanmean

        # Exclude all bins where the inhomogeneity (variation) is too high
        passed = np.ones_like(bins).astype("bool")
        if isinstance(variation_filter, tuple):
            if len(variation_filter) >= 2:
                if len(self[variation_filter[0]].shape) > 1:
                    raise ValueError(
                        "The variation filter can only be used for "
                        "1-dimensional data! I.e. the field '{}' must be "
                        "1-dimensional!".format(variation_filter[0])
                    )

                # Bin only one field for testing of inhomogeneities:
                binned = self.bin(bins, fields=(variation_filter[0]))

                # The user can define a different variation function (
                # default is the standard deviation).
                if len(variation_filter) == 2:
                    variation = np.nanstd(binned[variation_filter[0]], 1)
                else:
                    variation = variation_filter[2](
                        binned[variation_filter[0]], 1)
                passed = variation < variation_filter[1]
            else:
                raise ValueError("The inhomogeneity filter must be a tuple "
                                 "of a field name, a threshold and (optional)"
                                 "a variation function.")

        bins = np.asarray(bins)

        # Before collapsing the data, we must bin it:
        collapsed_data = self.bin(bins[passed], deep=deep)

        # Collapse the data:
        for var, data in collapsed_data.items(deep):
            collapsed_data[var] = collapser(data, 1)
        return collapsed_data

    @classmethod
    def concatenate(cls, objects, dimension=None):
        """Concatenate multiple GeoData objects.

        Notes:
            The attribute and dimension information of some arrays may get
            lost.

        Args:
            objects: List of GeoData objects to concatenate.
            dimension: Dimension on which to concatenate.

        Returns:
            A
        """
        new_data = cls()
        for var in objects[0]:
            if isinstance(objects[0][var], cls):
                new_data[var] = cls.concatenate(
                    [obj[var] for obj in objects],
                    dimension)
            else:
                if dimension is None:
                    dimension = 0
                new_data[var] = Array.concatenate(
                    [obj[var] for obj in objects],
                    dimension)

        return new_data

    def coords(self, deep=False):
        """Returns all variable names that are used as dimensions for other
        variables.

        Args:
            deep:

        Returns:

        """
        variables = list(self.vars(deep))
        coords = [
            coord
            for coord in variables
            for var in variables
            if coord in self[var].dims
        ]
        return list(set(coords))

    @classmethod
    def from_netcdf(cls, filename):
        """Creates a GeoData object from a xarray.Dataset object.

        Args:
            filename: Path and file name from where to load a new ArrayGroup.

        Returns:
            GeoData object
        """

        with Dataset(filename, "r") as root:
            array_group = cls._get_group_from_netcdf_group(root)

            return array_group

    @classmethod
    def _get_group_from_netcdf_group(cls, group):
        array_group = cls()

        array_group.attrs.update(**group.__dict__)

        # Add the variables:
        for var, data in group.variables.items():
            array_group[var] = Array(
                data[:], attrs=data.__dict__, dims=data.dimensions,
            )

        # Add the groups
        for subgroup, subgroup_obj in group.groups.items():
            array_group[subgroup] = \
                cls._get_group_from_netcdf_group(subgroup_obj)

        return array_group

    @classmethod
    def from_xarray(cls, xarray_object):
        """Creates a GeoData object from a xarray.Dataset object.

        Args:
            xarray_object: A xarray.Dataset object.

        Returns:
            GeoData object
        """

        array_dict = cls()
        for var in xarray_object:
            array_dict[var] = Array.from_xarray(xarray_object[var])

        array_dict.attrs.update(**xarray_object.attrs)

        return array_dict

    def get_range(self, field, deep=False, axis=None):
        """Get the minimum and maximum of one field.

        Args:
            field: Name of the variable.
            deep: Including also the fields in subgroups (not only main group).

        Returns:

        """
        variables = list(self.vars(deep, with_name=field))
        start = [np.nanmin(self[var], axis).item(0) for var in variables]
        end = [np.nanmax(self[var], axis).item(0) for var in variables]
        return min(start), max(end)

    def groups(self, deep=False):
        """Returns the names of all groups in this GeoData object.

        Args:
            deep: Including also subgroups (not only main group).

        Yields:
            Name of group.
        """

        for group in self._groups:
            yield group
            if deep:
                yield from (group + "/" + subgroup
                            for subgroup in self[group].groups(deep))

    def is_group(self, name):
        return name in self._groups

    def is_var(self, name):
        return name in self._vars

    def items(self, deep=False):
        """Iterate over all pairs of variables and their content.

        Args:
            deep: Including also variables from the subgroups.

        Yields:
            Tuple of variable name and content.
        """
        for var in self.vars(deep):
            yield var, self[var]

    @staticmethod
    def _level(var):
        level = len(var.split("/")) - 1
        if var.startswith("/"):
            level -= 1
        return level

    @classmethod
    def merge(cls, objects, groups=None, overwrite_error=True):
        """Merges multiple GeoData objects to one.

        Notes:
            Merging of sub groups with the same name does not work properly.

        Args:
            objects: List of GeoData objects.
            groups: List of strings. You can give each object in
                :param:`objects` a group. Must have the same length as
                :param:`objects`.
            overwrite_error: Throws a KeyError when trying to merge`
                ArrayGroups containing same keys.

        Returns:
            An ArrayGroup object.
        """
        inserted = set()
        merged_data = cls()
        for i, obj in enumerate(objects):
            for var in obj.vars(deep=True):
                if overwrite_error and var in inserted:
                    raise KeyError("The variable '{}' occurred multiple "
                                   "times!".format(var))
                else:
                    if groups is not None:
                        if groups[i] not in merged_data:
                            merged_data[groups[i]] = cls()
                        merged_data[groups[i]][var] = obj[var]
                    else:
                        merged_data[var] = obj[var]

        return merged_data

    @staticmethod
    def parse(key):
        """Parses *key* into first group and rest.

        You can access the groups and fields via different keys:

        * "value": Returns ("value", "")
        * "/value": Returns ("value", "")
        * "value1/value2/value3": Returns ("value1", "value2/value3")
        * "value/": Returns ("value", "")
        * "/": Returns ("", "")

        Args:
            key:

        Returns:

        """
        if key.startswith("/"):
            return key[1:], ""

        if "/" not in key:
            return key, ""

        var, rest = key.split("/", 1)
        return var, rest

    def plot(self, fields, plot_type="worldmap", fig=None, ax=None, **kwargs):
        """

        Args:
            plot_type:
            fields:
            fig:
            ax:
            **kwargs:

        Returns:

        """

        if plot_type == "worldmap":
            ax, scatter = typhon.plots.worldmap(
                self["lat"],
                self["lon"],
                self[fields[0]],
                fig, ax, **kwargs
            )
        else:
            raise ValueError("Unknown plot type: '{}'".format(plot_type))

        return ax

    def rename(self, mapping, inplace=True):
        if inplace:
            obj = self
        else:
            obj = copy.deepcopy(self)

        for old_name, new_name in mapping.items():
            array = obj[old_name]
            del obj[old_name]
            obj[new_name] = array

        return obj

    def select(self, indices, deep=False):
        """Select an TODO.

        Args:
            indices:
            deep:

        Returns:

        """
        selected_data = type(self)()

        for var in self.vars(deep):
            selected_data[var] = self[var][indices]

        return selected_data

    def to_netcdf(self, filename, attribute_warning=True,
                  avoid_dimension_errors=True):
        """Stores the ArrayGroup to a netcdf4 file.

        Args:
            filename: Path and file name to which to save this object.
            attribute_warning: Attributes in netCDF4 files may only be a
                number, list or string. If this is true, this method gives a
                warning whenever it tries to store an attribute not fulfilling
                these conditions.
            avoid_dimension_errors: This method raises an error if two
                variables use the same dimension but expecting different
                lengths. If this parameter is true, the error will not be
                raised but an additional dimension will be created.

        Returns:
            None
        """

        with Dataset(filename, "w", format="NETCDF4") as root_group:
            # Add all variables of the main group:
            self._add_group_to_netcdf(
                "/", root_group, attribute_warning, avoid_dimension_errors)

            # Add all variables of the sub groups:
            for group in self.groups(deep=True):
                nc_group = root_group.createGroup(group)
                self._add_group_to_netcdf(
                    group, nc_group, attribute_warning,
                    avoid_dimension_errors)

    def _add_group_to_netcdf(
            self, group, nc_group, attr_warning, avoid_dimension_errors):
        for attr, value in self[group].attrs.items():
            try:
                setattr(nc_group, attr, value)
            except TypeError:
                if attr_warning:
                    warnings.warn(
                        "Cannot store attribute '{}' since it is not "
                        "a number, list or string!".format(attr))

        coords = self[group].coords()
        for var, data in self[group].items():
            # Coordinates should be saved in the end, otherwise a netCDF error
            # will be raised.
            if var in coords:
                continue

            self._add_variable_to_netcdf_group(
                var, data, nc_group, attr_warning, avoid_dimension_errors
            )

        for coord in coords:
            data = self[group][coord]

            self._add_variable_to_netcdf_group(
                coord, data, nc_group, attr_warning, avoid_dimension_errors
            )

    @staticmethod
    def _add_variable_to_netcdf_group(
            var, data, nc_group, attr_warning, avoid_dimension_errors):
        for i, dim in enumerate(data.dims):
            if dim not in nc_group.dimensions:
                nc_group.createDimension(
                    dim, data.shape[i]
                )
            elif data.shape[i] != len(nc_group.dimensions[dim]):
                # The dimension already exists but have a different
                # length than expected. Either we raise an error or we
                # create a new dimension for this variable.
                if not avoid_dimension_errors:
                    raise ValueError(
                        "The dimension '{}' already exists and does not "
                        "have the same length as the same named dimension "
                        "from the variable '{}'. Maybe you should consider"
                        " renaming it?".format(dim, var))
                else:
                    while dim in nc_group.dimensions:
                        dim += "0"
                    nc_group.createDimension(
                        dim, data.shape[i]
                    )
                    data.dims[i] = dim

        if str(data.dtype).startswith("datetime64"):
            nc_var = nc_group.createVariable(
                var, "f8", data.dims
            )
            time_data = date2num(
                data.astype('M8[ms]').astype('O'),
                "milliseconds since 1970-01-01T00:00:00Z")
            nc_var.units = \
                "microseconds since 1970-01-01T00:00:00Z"
            nc_var[:] = time_data
        else:
            nc_var = nc_group.createVariable(
                var, data.dtype, data.dims
            )
            nc_var[:] = data

        for attr, value in data.attrs.items():
            try:
                setattr(nc_var, attr, value)
            except TypeError:
                if attr_warning:
                    warnings.warn(
                        "Cannot store attribute '{}' since it is not "
                        "a number, list or string!".format(attr))

    def to_xarray(self):
        """Converts this ArrayGroup object to a xarray.Dataset.

        Returns:
            A xarray.Dataset object
        """

        xarray_object = xr.Dataset()
        for var, data in self.items(deep=True):
            xarray_object[var] = data.to_xarray()

        xarray_object.attrs.update(**self.attrs)

        return xarray_object

    def values(self, deep=False):
        for var in self.vars(deep):
            yield self[var]

    def vars(self, deep=False, with_name=None):
        """Returns the names of all variables in this GeoData object main
        group.

        Args:
            deep: Searching also in subgroups (not only main group).
            with_name: Only the variables with this base name will be
                returned (makes only sense when *deep* is true).

        Yields:
            Full name of one variable (including group name).
        """

        # Only the variables of the main group:
        if with_name is None:
            yield from self._vars
        elif with_name in self._vars:
            yield with_name

        if deep:
            for group in self._groups:
                yield from (
                    group + "/" + sub_var
                    for sub_var in self[group].vars(deep, with_name)
                )
