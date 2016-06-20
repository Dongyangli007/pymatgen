# coding: utf-8
# Copyright (c) Pymatgen Development Team.
# Distributed under the terms of the MIT License.

from __future__ import division, print_function, unicode_literals, absolute_import

"""
This module implements classes for generating/parsing Lammps data files.
"""

from six.moves import range
from io import open
import re
from collections import OrderedDict

import numpy as np

from monty.json import MSONable, MontyDecoder

from pymatgen.core.structure import Molecule, Structure

__author__ = 'Kiran Mathew'
__email__ = "kmathew@lbl.gov"
__credits__ = 'Brandon Wood'


class LammpsData(MSONable):
    """
    Basic Lammps data: just the atoms section

    Args:
        box_size (list): [[x_min, x_max], [y_min,y_max], [z_min,z_max]]
        atomic_masses (list): [[atom type, mass],...]
        atoms_data (list): [[atom id, mol id, atom type, charge, x, y, z ...], ... ]
    """

    def __init__(self, box_size, atomic_masses, atoms_data):
        self.box_size = box_size
        self.natoms = len(atoms_data)
        self.natom_types = len(atomic_masses)
        self.atomic_masses = list(atomic_masses)
        self.atoms_data = atoms_data

    def __str__(self):
        """
        string representation of LammpsData

        Returns:
            String representation of the data file
        """
        lines = []
        lines.append("Data file generated by pymatgen\n")
        lines.append("{} atoms\n".format(self.natoms))
        lines.append("{} atom types\n".format(self.natom_types))
        lines.append("{} {} xlo xhi\n{} {} ylo yhi\n{} {} zlo zhi".format(
            self.box_size[0][0], self.box_size[0][1],
            self.box_size[1][0], self.box_size[1][1],
            self.box_size[2][0], self.box_size[2][1]))
        self.set_lines_from_list(lines, "Masses", self.atomic_masses)
        self.set_lines_from_list(lines, "Atoms", self.atoms_data)
        return '\n'.join(lines)

    @staticmethod
    def check_box_size(molecule, box_size):
        """
        Check the box size and if necessary translate the molecule so that
        all the sites are contained within the bounding box.

        Args:
            molecule(Molecule)
            box_size (list): [[x_min, x_max], [y_min, y_max], [z_min, z_max]]
        """
        box_lengths_req = [np.max(molecule.cart_coords[:, i])-np.min(molecule.cart_coords[:, i])
                           for i in range(3)]
        box_lengths = [min_max[1] - min_max[0] for min_max in box_size]
        try:
            np.testing.assert_array_less(box_lengths_req, box_lengths)
        except AssertionError:
            box_size = [[0.0, np.ceil(i*1.1)] for i in box_lengths_req]
            print("Minimum required box lengths {} larger than the provided box lengths{}. "
                  "Resetting the box size to {}".format(
                box_lengths_req, box_lengths, box_size))
        com = molecule.center_of_mass
        new_com = [(side[1] + side[0]) / 2 for side in box_size]
        translate_by = np.array(new_com) - np.array(com)
        molecule.translate_sites(range(len(molecule)), translate_by)
        return box_size

    def write_data_file(self, filename):
        """
        write lammps data input file from the string representation
        of the data.

        Args:
            filename (string): data file name
        """
        with open(filename, 'w') as f:
            f.write(self.__str__())

    @staticmethod
    def get_basic_system_info(structure):
        """
        Return basic system info from the given structure.

        Args:
            structure (Structure)

        Returns:
            number of atoms, number of atom types, box size, mapping
            between the atom id and corresponding atomic masses
        """
        natoms = len(structure)
        natom_types = len(structure.symbol_set)
        elements = structure.composition.elements
        elements = sorted(elements, key=lambda el: el.atomic_mass)
        atomic_masses_dict = OrderedDict(
            [(el.symbol, [i + 1, el.data["Atomic mass"]])
             for i, el in enumerate(elements)])
        return natoms, natom_types, atomic_masses_dict

    @staticmethod
    def get_atoms_data(structure, atomic_masses_dict, set_charge=True):
        """
        return the atoms data:
        atom_id, molecule tag, atom_type, charge(if present else 0), x, y, z.
        The molecule_tag is set to 1(i.e the whole structure corresponds to
        just one molecule). This corresponds to lammps command: "atom_style
        charge"

        Args:
            structure (Structure)
            atomic_masses_dict (dict):
                { atom symbol : [atom_id, atomic mass], ... }
            set_charge (bool): whether or not to set the charge field in Atoms

        Returns:
            [[atom_id, molecule tag, atom_type, charge(if present), x, y, z], ... ]
        """
        atoms_data = []
        for i, site in enumerate(structure):
            atom_type = atomic_masses_dict[site.specie.symbol][0]
            if set_charge:
                if hasattr(site, "charge"):
                    atoms_data.append([i + 1, 1, atom_type, site.charge,
                                       site.x, site.y, site.z])
                else:
                    atoms_data.append([i + 1, 1, atom_type, 0.0,
                                       site.x, site.y, site.z])
            else:
                atoms_data.append([i + 1, 1, atom_type,
                                   site.x, site.y, site.z])
        return atoms_data

    @staticmethod
    def set_lines_from_list(lines, block_name, input_list):
        """
        Append the values from the input list that corresponds to the block
        with name 'block_name' to the list of lines.

        Args:
            lines (list)
            block_name (string): name of the data block,
                e.g. 'Atoms', 'Bonds' etc
            input_list (list): list of values
        """
        if input_list:
            lines.append("\n" + block_name + " \n")
            for ad in input_list:
                lines.append(" ".join([str(x) for x in ad]))

    @staticmethod
    def from_structure(input_structure, box_size, set_charge=True):
        """
        Set LammpsData from the given structure. If the input structure is
        a Structure, it is converted to a molecule. TIf the molecule doesnt fit
        in the input box, the box size is updated based on the max and min site
        coordinates of the molecules.

        Args:
            input_structure (Molecule/Structure)
            box_size (list): [[x_min, x_max], [y_min, y_max], [z_min, z_max]]
            set_charge (bool): whether or not to set the charge field in
            Atoms. If true, the charge will be non-zero only if the
            input_structure has the "charge" site property set.

        Returns:
            LammpsData
        """
        if isinstance(input_structure, Structure):
            input_structure = Molecule.from_sites(input_structure.sites)
        box_size = LammpsData.check_box_size(input_structure, box_size)
        natoms, natom_types, atomic_masses_dict = \
            LammpsData.get_basic_system_info(input_structure.copy())
        atoms_data = LammpsData.get_atoms_data(input_structure,
                                               atomic_masses_dict,
                                               set_charge=set_charge)
        return LammpsData(box_size, atomic_masses_dict.values(), atoms_data)

    @staticmethod
    def from_file(data_file, read_charge=True):
        """
        Return LammpsData object from the data file.
        Note: use this to read in data files that conform with
        atom_style = charge or atomic

        Args:
            data_file (string): data file name
            read_charge (bool): if true, read in data files that conform with
                atom_style = charge else atom_style = atomic

        Returns:
            LammpsData
        """
        atomic_masses = []  # atom_type(starts from 1): mass
        box_size = []
        atoms_data = []
        # atom_id, mol_id, atom_type, charge, x, y, z
        if read_charge:
            atoms_pattern = re.compile(
                "^\s*(\d+)\s+(\d+)\s+(\d+)\s+([0-9eE\.+-]+)\s+("
                "[0-9eE\.+-]+)\s+([0-9eE\.+-]+)\s+([0-9eE\.+-]+)\w*")
        # atom_id, mol_id, atom_type, x, y, z
        else:
            atoms_pattern = re.compile(
                "^\s*(\d+)\s+(\d+)\s+(\d+)\s+([0-9eE\.+-]+)\s+("
                "[0-9eE\.+-]+)\s+([0-9eE\.+-]+)\w*")
        # atom_type, mass
        masses_pattern = re.compile("^\s*(\d+)\s+([0-9\.]+)$")
        box_pattern = re.compile(
            "^([0-9eE\.+-]+)\s+([0-9eE\.+-]+)\s+[xyz]lo\s+[xyz]hi")
        with open(data_file) as df:
            for line in df:
                if masses_pattern.search(line):
                    m = masses_pattern.search(line)
                    atomic_masses.append([int(m.group(1)), float(m.group(2))])
                if box_pattern.search(line):
                    m = box_pattern.search(line)
                    box_size.append([float(m.group(1)), float(m.group(2))])
                m = atoms_pattern.search(line)
                if m:
                    # atom id, mol id, atom type
                    line_data = [int(i) for i in m.groups()[:3]]
                    # charge, x, y, z
                    line_data.extend([float(i) for i in m.groups()[3:]])
                    atoms_data.append(line_data)
        return LammpsData(box_size, atomic_masses, atoms_data)

    def as_dict(self):
        d = MSONable.as_dict(self)
        if hasattr(self, "kwargs"):
            d.update(**self.kwargs)
        return d

    @classmethod
    def from_dict(cls, d):
        decoded = {k: MontyDecoder().process_decoded(v) for k, v in d.items()
                   if not k.startswith("@")}
        return cls(**decoded)


class LammpsForceFieldData(LammpsData):
    """
    Sets Lammps data input file from force field parameters.

    Args:
        box_size (list): [[x_min,x_max], [y_min,y_max], [z_min,z_max]]
        atomic_masses (list): [ [atom type, atomic mass], ... ]
        pair_coeffs (list): pair coefficients,
            [[unique id, sigma, epsilon ], ... ]
        bond_coeffs (list): bond coefficients,
            [[unique id, value1, value2 ], ... ]
        angle_coeffs (list): angle coefficients,
            [[unique id, value1, value2, value3 ], ... ]
        dihedral_coeffs (list): dihedral coefficients,
            [[unique id, value1, value2, value3, value4], ... ]
        improper_coeffs (list): improper dihedral coefficients,
            [[unique id, value1, value2, value3, value4], ... ]
        atoms_data (list): [[atom id, mol id, atom type, charge, x,y,z, ...], ... ]
        bonds_data (list): [[bond id, bond type, value1, value2], ... ]
        angles_data (list): [[angle id, angle type, value1, value2, value3], ... ]
        dihedrals_data (list):
            [[dihedral id, dihedral type, value1, value2, value3, value4], ... ]
        imdihedrals_data (list):
            [[improper dihedral id, improper dihedral type, value1, value2,
            value3, value4], ... ]
    """

    def __init__(self, box_size, atomic_masses, pair_coeffs, bond_coeffs,
                 angle_coeffs, dihedral_coeffs, improper_coeffs, atoms_data,
                 bonds_data, angles_data, dihedrals_data, imdihedrals_data):
        super(LammpsForceFieldData, self).__init__(box_size, atomic_masses,
                                                   atoms_data)
        # number of types
        self.nbond_types = len(bond_coeffs)
        self.nangle_types = len(angle_coeffs)
        self.ndih_types = len(dihedral_coeffs)
        self.nimdih_types = len(improper_coeffs)
        # number of parameters
        self.nbonds = len(bonds_data)
        self.nangles = len(angles_data)
        self.ndih = len(dihedrals_data)
        self.nimdihs = len(imdihedrals_data)
        # coefficients
        self.pair_coeffs = pair_coeffs
        self.bond_coeffs = bond_coeffs
        self.angle_coeffs = angle_coeffs
        self.dihedral_coeffs = dihedral_coeffs
        self.improper_coeffs = improper_coeffs
        # data
        self.bonds_data = bonds_data
        self.angles_data = angles_data
        self.dihedrals_data = dihedrals_data
        self.imdihedrals_data = imdihedrals_data

    def __str__(self):
        """
        returns a string of lammps data input file
        """
        lines = []
        # title
        lines.append("Data file generated by pymatgen\n")

        # count
        lines.append("{} atoms".format(self.natoms))
        lines.append("{} bonds".format(self.nbonds))
        lines.append("{} angles".format(self.nangles))
        if self.ndih > 0:
            lines.append("{} dihedrals".format(self.ndih))
        if self.nimdihs > 0:
            lines.append("{} impropers".format(self.nimdihs))

        # types
        lines.append("\n{} atom types".format(self.natom_types))
        lines.append("{} bond types".format(self.nbond_types))
        lines.append("{} angle types".format(self.nangle_types))
        if self.ndih > 0:
            lines.append("{} dihedral types".format(self.ndih_types))
        if self.nimdihs > 0:
            lines.append("{} improper types".format(self.nimdih_types))

        # box size
        lines.append("\n{} {} xlo xhi\n{} {} ylo yhi\n{} {} zlo zhi".format(
            self.box_size[0][0], self.box_size[0][1],
            self.box_size[1][0], self.box_size[1][1],
            self.box_size[2][0], self.box_size[2][1]))

        # masses
        self.set_lines_from_list(lines, "Masses", self.atomic_masses)

        # coefficients
        self.set_lines_from_list(lines, "Pair Coeffs", self.pair_coeffs)
        self.set_lines_from_list(lines, "Bond Coeffs", self.bond_coeffs)
        self.set_lines_from_list(lines, "Angle Coeffs", self.angle_coeffs)
        if self.ndih > 0:
            self.set_lines_from_list(lines, "Dihedral Coeffs",
                                     self.dihedral_coeffs)
        if self.nimdihs > 0:
            self.set_lines_from_list(lines, "Improper Coeffs",
                                     self.improper_coeffs)

        # data
        self.set_lines_from_list(lines, "Atoms", self.atoms_data)
        self.set_lines_from_list(lines, "Bonds", self.bonds_data)
        self.set_lines_from_list(lines, "Angles", self.angles_data)
        if self.ndih > 0:
            self.set_lines_from_list(lines, "Dihedrals", self.dihedrals_data)
        if self.nimdihs > 0:
            self.set_lines_from_list(lines, "Impropers", self.imdihedrals_data)
        return '\n'.join(lines)

    @staticmethod
    def get_param_coeff(forcefield, param_name):
        """
        get the parameter coefficients and mapping from the force field.

        Args:
            forcefield (ForceField): ForceField object
            param_name (string): name of the parameter for which
            the coefficients are to be set.

        Returns:
            [[parameter id, value1, value2, ... ], ... ] and
            {parameter key: parameter id, ...}
        """
        if hasattr(forcefield, param_name):
            param = getattr(forcefield, param_name)
            param_coeffs = []
            param_map = {}
            if param:
                for i, item in enumerate(param.items()):
                    param_coeffs.append([i + 1] + list(item[1]))
                    param_map[item[0]] = i+1
            return param_coeffs, param_map
        else:
            raise AttributeError

    @staticmethod
    def get_atoms_data(mols, mols_number, molecule, atomic_masses_dict, topologies):
        """
        Return the atoms data.

        Args:
            mols (list): list of Molecule objects.
            mols_number (list): number of each type of molecule in mols list.
            molecule (Molecule): the molecule assembled from the molecules
                in the mols list.
            topologies (list): list of Topology objects, one for each molecule
                type in mols list

        Returns:
            atoms_data: [[atom id, mol type, atom type, charge, x, y, z], ... ]
            molid_to_atomid: [ [global atom id 1, id 2, ..], ...], the
                index will be the global mol id
        """
        atom_to_mol = {}
        molid_to_atomid = []
        atoms_data = []
        nmols = len(mols)
        # set up map atom_id --> [mol_type, local atom id in the mol] in mols
        # set up map gobal molecule id --> [[atom_id,...],...]
        shift_ = 0
        for mol_type in range(nmols):
            natoms = len(mols[mol_type])
            for num_mol_id in range(mols_number[mol_type]):
                tmp = []
                for mol_atom_id in range(natoms):
                    atom_id = num_mol_id * natoms + mol_atom_id + shift_
                    atom_to_mol[atom_id] = [mol_type, mol_atom_id]
                    tmp.append(atom_id)
                molid_to_atomid.append(tmp)
            shift_ += len(mols[mol_type]) * mols_number[mol_type]
        # set atoms data from the molecule assembly consisting of
        # molecules from mols list with their count from mol_number list.
        # atom id, mol id, atom type, charge from topology, x, y, z
        for i, site in enumerate(molecule):
            atom_type = atomic_masses_dict[site.specie.symbol][0]
            # atom_type = molecule.symbol_set.index(site.species_string) + 1
            atom_id = i + 1
            mol_type = atom_to_mol[i][0] + 1
            mol_atom_id = atom_to_mol[i][1] + 1
            charge = 0.0
            if hasattr(topologies[0], "charges"):
                if topologies[mol_type - 1].charges:
                    charge = topologies[mol_type - 1].charges[mol_atom_id - 1]
            atoms_data.append([atom_id, mol_type, atom_type, charge,
                               site.x, site.y, site.z])
        return atoms_data, molid_to_atomid

    @staticmethod
    def get_param_data(param_name, param_map, mols, mols_number, topologies,
                       molid_to_atomid):
        """
        set the data for the parameter named param_name from the topology.

        Args:
            param_name (string): parameter name, example: "bonds"
            param_map (dict):
                { mol_type: {parameter_key : unique parameter id, ... }, ... }
                example: {0: {("c1","c2"): 1}} ==> c1-c2 bond in mol_type=0
                    has the global id of 1
            mols (list): list of molecules.
            mols_number (list): number of each type of molecule in mols list.
            topologies (list): list of Topology objects, one for each molecule
                type in mols list
            molid_to_atomid (list): [ [gloabal atom id 1, id 2, ..], ...],
                the index is the global mol id

        Returns:
            [ [parameter id, parameter type, global atom id1, global atom id2, ...], ... ]
        """
        param_data = []
        if hasattr(topologies[0], param_name) and getattr(topologies[0], param_name):
            nmols = len(mols)
            mol_id = 0
            # set the map param_to_mol:
            # {global param_id :[global mol id, mol_type, local param id in the param], ... }
            param_to_mol = {}
            shift_ = 0
            for mol_type in range(nmols):
                param_obj = getattr(topologies[mol_type], param_name)
                nparams = len(param_obj)
                for num_mol_id in range(mols_number[mol_type]):
                    mol_id += 1
                    for mol_param_id in range(nparams):
                        param_id = num_mol_id * nparams + mol_param_id + shift_
                        param_to_mol[param_id] = [mol_id - 1, mol_type, mol_param_id]
                shift_ += nparams * mols_number[mol_type]
            # set the parameter data using the topology info
            # example: loop over all bonds in the system
            skip = 0
            for param_id, pinfo in param_to_mol.items():
                mol_id = pinfo[0]  # global molecule id
                mol_type = pinfo[1]  # type of molecule
                mol_param_id = pinfo[2]  # local parameter id in that molecule
                # example: get the bonds list for mol_type molecule
                param_obj = getattr(topologies[mol_type], param_name)
                # connectivity info(local atom ids and type) for the parameter with the local id
                # 'mol_param_id'. example: single bond = [i, j, bond_type]
                param = param_obj[mol_param_id]
                param_atomids = []
                # loop over local atom ids that constitute the parameter
                # for the molecule type, mol_type
                # example: single bond = [i,j,bond_label]
                for atomid in param[:-1]:
                    # local atom id to global atom id
                    global_atom_id = molid_to_atomid[mol_id][atomid]
                    param_atomids.append(global_atom_id + 1)
                param_type = param[-1]
                param_type_reversed = tuple(reversed(param_type))
                # example: get the unique number id for the bond_type
                if param_type in param_map:
                    key = param_type
                elif param_type_reversed in param_map:
                    key = param_type_reversed
                else:
                    key = None
                if key:
                    param_type_id = param_map[key]
                    param_data.append([param_id + 1 - skip, param_type_id] + param_atomids)
                else:
                    skip += 1
                    print("{} or {} Not available".format(param_type, param_type_reversed))
        return param_data

    @staticmethod
    def from_forcefield_and_topology(mols, mols_number, box_size, molecule,
                                     forcefield, topologies):
        """
        Return LammpsForceFieldData object from force field and topology info.

        Args:
            mols (list): List of Molecule objects
            mols_number (list): List of number of molecules of each
                molecule type in mols
            box_size (list): [[x_min,x_max], [y_min,y_max], [z_min,z_max]]
            molecule (Molecule): The molecule that is assembled from mols
                and mols_number
            forcefield (ForceFiled): Force filed information
            topologies (list): List of Topology objects, one for each
                molecule type in mols.

        Returns:
            LammpsForceFieldData
        """
        # set the coefficients and map from the force field
        bond_coeffs, bond_map = LammpsForceFieldData.get_param_coeff(
            forcefield, "bonds")
        angle_coeffs, angle_map = LammpsForceFieldData.get_param_coeff(
            forcefield, "angles")
        pair_coeffs, _ = LammpsForceFieldData.get_param_coeff(
            forcefield, "pairs")
        dihedral_coeffs, dihedral_map = LammpsForceFieldData.get_param_coeff(
            forcefield, "dihedrals")
        improper_coeffs, imdihedral_map = LammpsForceFieldData.get_param_coeff(
            forcefield, "imdihedrals")
        # atoms data, topology used for setting charge if present
        box_size = LammpsForceFieldData.check_box_size(molecule, box_size)
        natoms, natom_types, atomic_masses_dict = \
            LammpsData.get_basic_system_info(molecule.copy())
        atoms_data, molid_to_atomid = LammpsForceFieldData.get_atoms_data(
            mols, mols_number, molecule, atomic_masses_dict, topologies)
        # set the other data from the molecular topologies
        bonds_data = LammpsForceFieldData.get_param_data(
            "bonds", bond_map, mols, mols_number, topologies, molid_to_atomid)
        angles_data = LammpsForceFieldData.get_param_data(
            "angles", angle_map, mols, mols_number, topologies, molid_to_atomid)
        dihedrals_data = LammpsForceFieldData.get_param_data(
            "dihedrals", dihedral_map, mols, mols_number, topologies, molid_to_atomid)
        imdihedrals_data = LammpsForceFieldData.get_param_data(
            "imdihedrals", imdihedral_map, mols, mols_number, topologies, molid_to_atomid)
        return LammpsForceFieldData(box_size, atomic_masses_dict.values(),
                                    pair_coeffs, bond_coeffs,
                                    angle_coeffs, dihedral_coeffs,
                                    improper_coeffs, atoms_data,
                                    bonds_data, angles_data, dihedrals_data,
                                    imdihedrals_data)

    @staticmethod
    def from_file(data_file):
        """
        Return LammpsForceFieldData object from the data file. It is assumed
        that the forcefield paramter sections for pairs, bonds, angles,
        dihedrals and improper dihedrals are named as follows(not case sensitive):
        "Pair Coeffs", "Bond Coeffs", "Angle Coeffs", "Dihedral Coeffs" and
        "Improper Coeffs". For "Pair Coeffs", values for factorial(n_atom_types)
        pairs must be specified.

        Args:
            data_file (string): the data file name

        Returns:
            LammpsForceFieldData
        """
        atomic_masses = []  # atom_type(starts from 1): mass
        box_size = []
        pair_coeffs = []
        bond_coeffs = []
        angle_coeffs = []
        dihedral_coeffs = []
        improper_coeffs = []
        atoms_data = []
        bonds_data = []
        angles_data = []
        dihedral_data = []
        imdihedral_data = []
        types_pattern = re.compile("^\s*(\d+)\s+([a-zA-Z]+)\s+types$")
        # atom_id, mol_id, atom_type, charge, x, y, z
        atoms_pattern = re.compile(
            "^\s*(\d+)\s+(\d+)\s+(\d+)\s+([0-9eE\.+-]+)\s+("
            "[0-9eE\.+-]+)\s+([0-9eE\.+-]+)\s+([0-9eE\.+-]+)\w*")
        masses_pattern = re.compile("^\s*(\d+)\s+([0-9\.]+)$")
        box_pattern = re.compile(
            "^\s*([0-9eE\.+-]+)\s+([0-9eE\.+-]+)\s+[xyz]lo\s+[xyz]hi")
        # id, value1, value2
        general_coeff_pattern = re.compile("^\s*(\d+)\s+([0-9\.]+)\s+([0-9\.]+)$")
        # id, type, atom_id1, atom_id2
        bond_data_pattern = re.compile("^\s*(\d+)\s+(\d+)\s+(\d+)\s+(\d+)\s*$")
        # id, type, atom_id1, atom_id2, atom_id3
        angle_data_pattern = re.compile(
            "^\s*(\d+)\s+(\d+)\s+(\d+)\s+(\d+)\s+(\d+)\s*$")
        # id, type, atom_id1, atom_id2, atom_id3, atom_id4
        dihedral_data_pattern = re.compile(
            "^\s*(\d+)\s+(\d+)\s+(\d+)\s+(\d+)\s+(\d+)\s+(\d+)\s*$")
        read_pair_coeffs = False
        read_bond_coeffs = False
        read_angle_coeffs = False
        read_dihedral_coeffs = False
        read_improper_coeffs = False
        with open(data_file) as df:
            for line in df:
                if types_pattern.search(line):
                    m = types_pattern.search(line)
                    if m.group(2) == "atom":
                        natom_types = int(m.group(1))
                        npair_types = natom_types # i != j skipped
                    if m.group(2) == "bond":
                        nbond_types = int(m.group(1))
                    if m.group(2) == "angle":
                        nangle_types = int(m.group(1))
                    if m.group(2) == "dihedral":
                        ndihedral_types = int(m.group(1))
                    if m.group(2) == "improper":
                        nimproper_types = int(m.group(1))
                if masses_pattern.search(line):
                    m = masses_pattern.search(line)
                    atomic_masses.append([int(m.group(1)), float(m.group(2))])
                if box_pattern.search(line):
                    m = box_pattern.search(line)
                    box_size.append([float(m.group(1)), float(m.group(2))])
                if "Pair Coeffs".lower() in line.lower():
                    read_pair_coeffs = True
                    continue
                if read_pair_coeffs:
                    tokens = line.split()
                    if tokens:
                        pair_coeffs.append([int(tokens[0])] + [float(i) for i in tokens[1:]])
                        read_pair_coeffs = False if len(pair_coeffs) >= npair_types else True
                if "Bond Coeffs".lower() in line.lower():
                    read_bond_coeffs = True
                    continue
                if read_bond_coeffs:
                    m = general_coeff_pattern.search(line)
                    if m:
                        bond_coeffs.append(
                            [int(m.group(1)), float(m.group(2)), float(m.group(3))])
                        read_bond_coeffs = False if len(bond_coeffs) >= nbond_types else True
                if "Angle Coeffs".lower() in line.lower():
                    read_angle_coeffs = True
                    continue
                if read_angle_coeffs:
                    m = general_coeff_pattern.search(line)
                    if m:
                        angle_coeffs.append(
                            [int(m.group(1)), float(m.group(2)), float(m.group(3))])
                        read_angle_coeffs = False if len(angle_coeffs) >= nangle_types else True
                if "Dihedral Coeffs".lower() in line.lower():
                    read_dihedral_coeffs = True
                    continue
                if read_dihedral_coeffs:
                    tokens = line.split()
                    if tokens:
                        dihedral_coeffs.append(
                            [int(tokens[0])] + [float(i) for i in tokens[1:]])
                        read_dihedral_coeffs = False if len(dihedral_coeffs) >= ndihedral_types else True
                if "Improper Coeffs".lower() in line.lower():
                    read_improper_coeffs = True
                    continue
                if read_improper_coeffs:
                    tokens = line.split()
                    if tokens:
                        improper_coeffs.append(
                            [int(tokens[0])] + [float(i) for i in tokens[1:]])
                        read_improper_coeffs = False if len(improper_coeffs) >= nimproper_types else True
                if atoms_pattern.search(line):
                    m = atoms_pattern.search(line)
                    # atom id, mol id, atom type
                    line_data = [int(i) for i in m.groups()[:3]]
                    # charge, x, y, z, vx, vy, vz ...
                    line_data.extend([float(i) for i in m.groups()[3:]])
                    atoms_data.append(line_data)
                if bond_data_pattern.search(line) and atoms_data:
                    m = bond_data_pattern.search(line)
                    bonds_data.append([int(i) for i in m.groups()])
                if angle_data_pattern.search(line) and atoms_data:
                    m = angle_data_pattern.search(line)
                    angles_data.append([int(i) for i in m.groups()])
                if dihedral_data_pattern.search(line) and atoms_data:
                    m = dihedral_data_pattern.search(line)
                    dihedral_data.append([int(i) for i in m.groups()])
        return LammpsForceFieldData(box_size, atomic_masses, pair_coeffs,
                                    bond_coeffs, angle_coeffs,
                                    dihedral_coeffs, improper_coeffs,
                                    atoms_data, bonds_data, angles_data,
                                    dihedral_data, imdihedral_data)
