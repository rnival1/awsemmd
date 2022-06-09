#!/usr/bin/env python3
# -*- coding: utf-8 -*-

####################
# Written by Shikai Jin on 2019-Mar-18, latest modified on 2019-Jul-15
# Modified from Bin Zhang + Weihua Zheng + Mingchen Chen + Aram Davtyan's python2 version
# Combine BuildAllAtomsFromLammps_multiChain_dna.py, BuildAllAtomsFromLammps_multiChain_seq.py and
# 2011 original/ 2018 updated BuildAllAtomsFromLammps.py

# For atom desc in 3SPN2 DNA version, you should read https://github.com/groupdepablo/USER-3SPN2/blob/master/DSIM_ICNF/wrte_lammps.c
# and https://github.com/groupdepablo/USER-3SPN2/blob/master/utils/pdb2cg_dna.py .
# Index from 1-18, they are P S A T G C 5A 5T 5G 5C 3A 3T 3G 3C Na+ Mg2+ Cl- N+
# You can also check bdna_curv.xyz with dna_premerge.data in corresponding directory
# Since we don't have ions so type index 1-14 are used to represent pure DNA, and 15-20 are used to represent protein part

# sequence file (.seq) is required, and, supports multiple chain mode and will detect but each chain should only obtain ONE LINE
# If you open dna mode then a dna pdb file generated by 3SPN.2 is required (usually atomistic.pdb)
# Will try best to eliminate any changes from original code

# Example in Linux: python BuildAll_final_version_py3.py DUMP_FILE_temp300.lammpstrj casp.seq --dna --dna_pdb atomistic.pdb
####################

from __future__ import print_function
import argparse
import math
import numpy as np
import sys

# Parameters for recovering N and C-prime atom
an = 0.4831806
bn = 0.7032820
cn = -0.1864262
ap = 0.4436538
bp = 0.2352006
cp = 0.3211455

rNCa = 1.45808
rCaCp = 1.52469
rCpO = 1.23156
psi_NCaCp = 1.94437215835
psi_CaCpO = 2.10317155324
theta_NCaCpO = 2.4

protein_res = {"C" : "CYS", "I" : "ILE", "S" : "SER", "Q" : "GLN", "K" : "LYS", 
	 "N" : "ASN", "P" : "PRO", "T" : "THR", "F" : "PHE", "A" : "ALA", 
	 "H" : "HIS", "G" : "GLY", "D" : "ASP", "L" : "LEU", "R" : "ARG", 
	 "W" : "TRP", "V" : "VAL", "E" : "GLU", "Y" : "TYR", "M" : "MET"}

dna_res = {"A" : "DA", "T" : "DT", "C" : "DC", "G" : "DG"}

# PDB atom format
class PDB_Atom:
    def __init__(self, serial, atom_name, res_name, chain_id, res_index, x, y, z, atom_type):
        self.serial = serial
        self.atom_name = atom_name
        self.res_name = res_name
        self.chain_id = chain_id
        self.res_index = res_index
        self.x = x
        self.y = y
        self.z = z
        self.atom_type = atom_type

    def write_(self, f):
        # Avoid conflict with Python default key word write
        # Read this https://blog.csdn.net/tcx1992/article/details/80105645
        # For standard output the PDB format see this http://cupnet.net/pdb-format/
        f.write('ATOM  ')
        f.write("{:5d}".format(self.serial))
        f.write(' ')
        f.write("{:^4s}".format(self.atom_name[:4]))
        f.write(' ')
        f.write("{:3s}".format(self.res_name))
        f.write(' ')
        f.write("{:1s}".format(self.chain_id))
        f.write("{:4d}".format(self.res_index))
        f.write("    ")
        f.write("{:8.3f}".format(self.x))
        f.write("{:8.3f}".format(self.y))
        f.write("{:8.3f}".format(self.z))
        f.write('  1.00')  # Occupancy factor
        f.write('  0.00')  # B-factor
        f.write(('            ' + "{:>2s}".format(self.atom_type)[-12:]) + '  ')
        f.write('\n')


# Lammps atom format
class Lammps_Atom:
    def __init__(self, serial, atom_type, x, y, z, desc):
        self.serial = serial
        self.atom_type = atom_type
        self.x = x
        self.y = y
        self.z = z
        self.desc = desc

# Equations used for recovering terimnal atoms
def vnorm(v):
    return math.sqrt(v[0] * v[0] + v[1] * v[1] + v[2] * v[2])


def vscale(scale, v):
    return [scale * v[0], scale * v[1], scale * v[2]]


def vdot(v1, v2):
    return v1[0] * v2[0] + v1[1] * v2[1] + v1[2] * v2[2]


def vcross(v1, v2):
    return [v1[1] * v2[2] - v1[2] * v2[1], v1[2] * v2[0] - v1[0] * v2[2], v1[0] * v2[1] - v1[1] * v2[0]]


# First read protein sequence file
def load_protein_sequence_file(seq_file, verbose):  # remember sequence file must be one line for one chain
    protein_sequence_all = []
    protein_chain_length = []
    with open(seq_file, 'r') as fh:
        for line in fh.readlines():
            seq = line.strip()
            protein_sequence_all.append(seq)
            protein_chain_length.append(len(seq))

    if verbose:
        print ("Number of protein chain is %s" % len(protein_chain_length))
        print ("The total protein sequence is on protein_sequence_all variable")
        print (protein_sequence_all)
        print ("The total protein chain length is on protein_chain_length variable")
        print (protein_chain_length)
    return protein_sequence_all, protein_chain_length


# Second read the atomistic pdb file for DNA
def read_dna_pdb(dna_pdb_file, verbose):
    dna_atom_list = []  # Save all DNA atoms in dictionary but aborted
    dna_sequence = ''
    dna_sequence_all = []
    dna_chain_length = []
    with open(dna_pdb_file, 'r') as fh:
        for line in fh.readlines():
            items = line.split()
            if items[0] == 'ATOM':
                serial = int(items[1])
                atom_name = items[2]
                res_name = items[3]
                chain_id = items[4]
                res_index = int(items[5]) # Possible error may be caused by over 1000 residue index
                x = float(items[6])
                y = float(items[7])
                z = float(items[8])
                atom_type = items[-1]
                dna_atom_list.append(PDB_Atom(serial, atom_name, res_name, chain_id, res_index, x, y, z, atom_type))
    # Initialization
    dna_chain_id_flag = dna_atom_list[0].chain_id
    one_chain_length = 0
    current_residue_number = -1

    for i, dna_atom in enumerate(dna_atom_list):
        if dna_atom.chain_id != dna_chain_id_flag or i == len(dna_atom_list) - 1:
            dna_sequence_all.append(dna_sequence)
            dna_chain_length.append(one_chain_length)
            current_residue_number = -1
            one_chain_length = 0
            dna_chain_id_flag = dna_atom.chain_id
            dna_sequence = ''
        if int(dna_atom.res_index) != current_residue_number:
            dna_sequence = dna_sequence + dna_atom.res_name[-1]
            one_chain_length += 1  # Don't directly record index due to possible missing residue
            current_residue_number = dna_atom.res_index
            
    #print(dna_sequence_all)
    #print(dna_chain_length)
    if verbose:
        print ("Number of dna chain is %s" % len(dna_chain_length))
    return dna_sequence_all, dna_chain_length


def recover_N_terminal_atom(Ca, Cp, O):  # Directly copied from Aram's newest version code
    r = rNCa
    psi = psi_NCaCp
    theta = -theta_NCaCpO

    v1 = [Cp.x - O.x, Cp.y - O.y, Cp.z - O.z]
    v2 = [Cp.x - Ca.x, Cp.y - Ca.y, Cp.z - Ca.z]

    mz = v2
    my = vcross(v1, mz)
    mx = vcross(my, mz)

    mx = vscale(r * math.sin(psi) * math.cos(theta) / vnorm(mx), mx)
    my = vscale(r * math.sin(psi) * math.sin(theta) / vnorm(my), my)
    mz = vscale(r * math.cos(psi) / vnorm(mz), mz)

    nx = Ca.x + mx[0] + my[0] + mz[0]
    ny = Ca.y + mx[1] + my[1] + mz[1]
    nz = Ca.z + mx[2] + my[2] + mz[2]

    # N = Lammps_Atom(0, '2', nx, ny, nz, 'N')

    return nx, ny, nz


def recover_C_terminal_atom(Ca, N, O):  # Directly copied from Aram's newest version code
    sign = 1  # 1 or -1
    r1 = rNCa
    r2 = rCaCp
    r3 = rCpO
    psi1 = psi_NCaCp
    #psi2 = psi_CaCpO # Not sure why and what this line work

    xn = [N.x - Ca.x, N.y - Ca.y, N.z - Ca.z]
    xo = [O.x - Ca.x, O.y - Ca.y, O.z - Ca.z]

    ro = vnorm(xo)
    ro_sq = ro * ro
    rn_sq = vdot(xn, xn)
    r1o = vdot(xn, xo)
    A = r1 * r2 * math.cos(psi1)
    B = ro_sq + r2 * r2 - r3 * r3
    T1 = xn[1] * xn[1] + xn[2] * xn[2]
    T2 = xo[1] * xo[1] + xo[2] * xo[2]
    T3 = xn[1] * xo[1] + xn[2] * xo[2]
    T4 = xn[2] * xo[1] - xn[1] * xo[2]
    T5 = xn[0] * xo[2] - xn[2] * xo[0]
    T6 = xn[0] * xo[1] - xn[1] * xo[0]

    cprod = vcross(xn, xo)
    cprod_sq = vdot(cprod, cprod)
    #print("cprod_sq is " + str(cprod_sq))

    D = cprod_sq * r2 * r2 - A * A * ro_sq - 0.25 * B * B * rn_sq + A * B * r1o

    # If D<0 reduce the angle psi1 by changing A and B
    if D < 0:
        D = 0
        if abs(B) > 2.0 * ro * r2:
            B = 2.0 * ro * r2
            A = B * r1o / ro_sq
        else:
            A = 0.5 * (B * r1o + math.sqrt(cprod_sq * (4.0 * ro_sq * r2 * r2 - B * B))) / ro_sq
            if A > r1 * r2:
                print ("Warning: A value too large")

    px = (A * (-xo[0] * T3 + xn[0] * T2) + 0.5 * B * (xo[0] * T1 - xn[0] * T3) + sign * T4 * math.sqrt(
        D)) / cprod_sq
    py = (-A * xo[2] + 0.5 * B * xn[2] + px * T5) / T4
    pz = (A * xo[1] - 0.5 * B * xn[1] - px * T6) / T4

    px += Ca.x
    py += Ca.y
    pz += Ca.z

    # Cp = Lammps_Atom(0, '6', px, py, pz, 'C-Prime')
    return px, py, pz

#def build_all_atoms(atoms_one_frame, atom_index_to_chain_index, dna_flag, chain_length, protein_chain_length, dna_chain_length, build_terminal_atoms=True):
def build_all_atoms(atoms_per_frame, residue_index_to_chain_index, dna_flag, chain_length_list_cum, protein_chains_number, build_terminal_atoms=True):
    N_atom_map = {}
    Ca_atom_map = {}
    Cp_atom_map = {}
    O_atom_map = {}
    Cb_atom_map = {}
    P_atom_map = {} # from previous code, the DNA 3SPN site start from P, so 5' tail will always lose a P but 3' tail is safe
    S_atom_map = {}
    base_atom_map = {}
    #print(chain_length_list_cum)
    protein_chain_end_point = chain_length_list_cum[:protein_chains_number]
    #print("protein_chain_end_point is ")
    #print(protein_chain_end_point)

    #########
    # This part is VERY IMPORTANT and deal with the transition of terminal residue from protein to dna
    if dna_flag:
        dna_chain_end_point = chain_length_list_cum[protein_chains_number:]
        dna_chain_check_point = []
        dna_chain_check_point.append(protein_chain_end_point[-1])
        for i in range(len(dna_chain_end_point) - 1):
            dna_chain_check_point.append(dna_chain_end_point[i] + 1)
        #print("dna_chain_check_point (which is different from start or end point) is ")
        #print(dna_chain_check_point)
    all_atoms_after_recover = []
    #########
    
    if build_terminal_atoms:
        first_residues = []
        first_residues.append(1)  # Always start from 1
        for i in protein_chain_end_point:
            first_residues.append(i + 1)
        first_residues.pop()  # Delete last element which is wrong
        #print("first_residue" + first_residues)
        #print("last_residue" + last_residues)

    # Map all atoms in one frame
    res_no = 0
    for i in range(0, len(atoms_per_frame)):
        ia = atoms_per_frame[i]
        if ia.desc == 'C-Alpha':
            res_no += 1
            Ca_atom_map[res_no] = ia
        elif ia.desc == 'O':
            O_atom_map[res_no] = ia
        elif ia.desc == 'C-Beta' or ia.desc == 'H-Beta':
            Cb_atom_map[res_no] = ia

        if dna_flag:
            if ia.desc == 'S':                        
                if (res_no in dna_chain_check_point) or (res_no in base_atom_map):
                    res_no += 1
                S_atom_map[res_no] = ia
            elif ia.desc == 'P':
                res_no += 1
                P_atom_map[res_no] = ia
            elif ia.desc == 'B':
                base_atom_map[res_no] = ia

    # Recovering N and Cp atoms, leave DNA region alone
    nres_tot = protein_chain_end_point[-1]
    #nres_tot = chain_length_list_cum[-1-dna_chain_number]
    #print(nres_tot)
    for i in range(1, nres_tot+1):
        if i not in Ca_atom_map:
            # print ("Error! missing Ca atom in residue %d!\n" % i)
            sys.exit("Error! missing Ca atom in residue %d!\n" % i)
        if i not in Cb_atom_map:
            # print ("Error! missing Cb atom in residue %d!\n" % i)
            sys.exit("Error! missing Cb atom in residue %d!\n" % i)
        if i not in O_atom_map:
            # print ("Error! missing O atom in residue %d!\n" % i)
            sys.exit("Error! missing O atom in residue %d!\n" % i)

        if i not in protein_chain_end_point:  # Check whether the chain_id is consistent
            Cai = Ca_atom_map[i]
            Cai1 = Ca_atom_map[i + 1]
            Oi = O_atom_map[i]

            nx = an * Cai.x + bn * Cai1.x + cn * Oi.x
            ny = an * Cai.y + bn * Cai1.y + cn * Oi.y
            nz = an * Cai.z + bn * Cai1.z + cn * Oi.z

            px = ap * Cai.x + bp * Cai1.x + cp * Oi.x
            py = ap * Cai.y + bp * Cai1.y + cp * Oi.y
            pz = ap * Cai.z + bp * Cai1.z + cp * Oi.z

            if dna_flag:
                N = Lammps_Atom(int(i) + 1, '16', nx, ny, nz, 'N')
                Cp = Lammps_Atom(int(i), '20', px, py, pz, 'C-Prime')
            else:
                N = Lammps_Atom(int(i) + 1, '2', nx, ny, nz, 'N')
                Cp = Lammps_Atom(int(i), '6', px, py, pz, 'C-Prime')

            if build_terminal_atoms:
                if i in first_residues:
                    nx, ny, nz = recover_N_terminal_atom(Cai, Cp, Oi)
                    if dna_flag:
                        N = Lammps_Atom(int(i), '16', nx, ny, nz, 'N')
                    else:
                        N = Lammps_Atom(int(i), '2', nx, ny, nz, 'N')
                    N_atom_map[i] = N

            N_atom_map[i + 1] = N
            Cp_atom_map[i] = Cp

        else:
            if build_terminal_atoms:
                Ca = Ca_atom_map[i]
                N = N_atom_map[i]
                O = O_atom_map[i]
                px, py, pz = recover_C_terminal_atom(Ca, N, O)
                if dna_flag:
                    Cp = Lammps_Atom(int(i), '20', px, py, pz, 'C-Prime')
                else:
                    Cp = Lammps_Atom(int(i), '6', px, py, pz, 'C-Prime')
                Cp_atom_map[i] = Cp


    all_atoms_after_recover.append(N_atom_map)
    all_atoms_after_recover.append(Ca_atom_map)
    all_atoms_after_recover.append(Cp_atom_map)
    all_atoms_after_recover.append(O_atom_map)
    all_atoms_after_recover.append(Cb_atom_map)
    if dna_flag:
        all_atoms_after_recover.append(P_atom_map)
        all_atoms_after_recover.append(S_atom_map)
        all_atoms_after_recover.append(base_atom_map)
    return all_atoms_after_recover
        

def convert_to_pdb(all_atoms_after_recover, dna_flag, residue_index_to_chain_index, new_total_sequence_all, chain_length_list_cum, atom_type, pdb_type):
    all_atoms_to_PDB = []
    total_residues = chain_length_list_cum[-1]
    serial = 1
    for i in range(1, total_residues+1):
        for atom_each_type in all_atoms_after_recover:
            if i in atom_each_type:
                ia = atom_each_type[i]
                pdb_residue = PDB_Atom(serial, pdb_type[ia.atom_type], new_total_sequence_all[i-1], residue_index_to_chain_index[i], i, ia.x, ia.y, ia.z, atom_type[ia.atom_type])
                serial += 1
                all_atoms_to_PDB.append(pdb_residue)
    with open ('final_test.pdb', 'a') as fopen:
        for atom in all_atoms_to_PDB:
            atom.write_(fopen)
        fopen.write("END\n")


def lammps_load_and_convert(lammpsdump_file, atom_type, atom_desc, pdb_type, dna_flag, new_total_sequence_all, residue_index_to_chain_index, chain_length_list_cum, protein_chains_number):
    # Initialization
    box_type = []
    box_boundary = []
    atoms_per_frame = [] # List not dictionary so have the order
    n_frame = 0
    n_atoms = 0
    snapshots = -1
    total_length = chain_length_list_cum[-1]

    with open(lammpsdump_file, 'r') as dump_file:
        if snapshots < 0:  # Calculate all frames
            for dump_line in dump_file:
                dump_line = dump_line.strip()
                if dump_line[:5] == "ITEM:":
                    item = dump_line[6:]  # Then check next part what happened
                    if item[:10] == "BOX BOUNDS":  # Record box type
                        box_type.append(item[10:]) # Not used here
                else:
                    if item == "TIMESTEP":
                        n_frame += 1
                        if len(atoms_per_frame) > 0:  # Check do we have previous frame to calculate
                            if len(atoms_per_frame) != n_atoms:
                                sys.exit("Error! Number of atoms in dump file is different from loaded!\n")
                            #print(atoms_per_frame[-1].x)
                            #print(atoms_per_frame[-1].serial)
                            #print(atoms_per_frame[-1].atom_type)
                            #print(box_boundary)
                            all_atoms_after_recover = build_all_atoms(atoms_per_frame, residue_index_to_chain_index, dna_flag, chain_length_list_cum, protein_chains_number, build_terminal_atoms=True)
                            convert_to_pdb(all_atoms_after_recover, dna_flag, residue_index_to_chain_index, new_total_sequence_all, chain_length_list_cum, atom_type, pdb_type)
                            # Build previous frame

                            # atom_name = convert_atom_id_to_name(i_atom)
                            # res_index = convert_atom_id_to_res(i_atom)
                            # res_name = convert_res_index_to_res_name(res_index)
                            # chain_id = convert_res_index_to_chain_id(res_index)
                            # convert_to_pdb()
                            # print_pdb()
                            
                            box_boundary = []
                            atoms_per_frame = []
                    # check chain length with range
                    # build atoms
                    # atoms2
                    # convert to PDB
                    # build DNA
                    # print all to PDB
                    # end build and re-initialization
                    elif item == "NUMBER OF ATOMS":
                        n_atoms = int(dump_line)
                        if dna_flag:
                            if n_atoms != total_length * 3 - 2: # here should change to the number of dna chain later
                                sys.exit("Error! Number of atoms in dump file is different from input!\n")
                        else:
                            if n_atoms != total_length * 3:
                                sys.exit("Error! Number of atoms in dump file is different from input!\n")
                    # check atoms per frame
                    # Calc_chain_id
                    elif item[:10] == "BOX BOUNDS":
                        dump_line = dump_line.split()
                        box_boundary.append([float(dump_line[0]), float(dump_line[1])])
                    elif item[:5] == "ATOMS":
                        dump_line = dump_line.split()
                        i_atom = dump_line[0]
                        x = float(dump_line[2])
                        y = float(dump_line[3])
                        z = float(dump_line[4])
                        x_position = (box_boundary[0][1] - box_boundary[0][0]) * x + box_boundary[0][0]
                        y_position = (box_boundary[1][1] - box_boundary[1][0]) * y + box_boundary[1][0]
                        z_position = (box_boundary[2][1] - box_boundary[2][0]) * z + box_boundary[2][0]
                        desc = atom_desc[dump_line[1]]
                        atom = Lammps_Atom(i_atom, dump_line[1], x_position, y_position, z_position, desc)
                        atoms_per_frame.append(atom)
                        

                        # return pdb_atoms_all_frame

                        # atom_chain_id = atom_index_to_chain_index[int(i_atom) - 1]
                        # if dna_flag and int(dump_line[1]) < 15:
                        #   desc = "DNA"
                        #   atom = PDB_Atom(i_atom, atom_type[dump_line[1]], residue_name, atom_chain_id, dump_line[1], x_position, y_position, z_position, desc)
                        #   self, serial, atom_name, res_name, chain_id, res_index, x, y, z, atom_type
                        #   atom = Atom(i_atom, 'P', dump_line[1], x_position, y_position, z_position, atom_chain_id,desc)
                        # else:
                        #   desc = atom_desc[dump_line[1]]
                        #   atom = Atom(i_atom, atom_type[dump_line[1]],residue_name,atom_chain_id, dump_line[1], x_position, y_position, z_position,desc)
            #if len(atoms_per_frame) > 0:  # Check do we have previous frame to calculate
                #build_all_atoms(atoms_per_frame, atom_index_to_chain_index, dna_flag, chain_length, protein_chain_length, dna_chain_length, build_terminal_atoms=True)
                #convert_to_pdb()
                
            # To deal with last frame
            if len(atoms_per_frame) > 0:  # Check do we have previous frame to calculate
                if len(atoms_per_frame) != n_atoms:
                    sys.exit("Error! Number of atoms in dump file is different from loaded!\n")
                #print(atoms_per_frame[-1].x)
                #print(atoms_per_frame[-1].serial)
                #print(atoms_per_frame[-1].atom_type)
                #print(box_boundary)
                all_atoms_after_recover = build_all_atoms(atoms_per_frame, residue_index_to_chain_index, dna_flag, chain_length_list_cum, protein_chains_number, build_terminal_atoms=True)
                convert_to_pdb(all_atoms_after_recover, dna_flag, residue_index_to_chain_index, new_total_sequence_all, chain_length_list_cum, atom_type, pdb_type)


        else:  # Calculate specific frame
            found = False
            for dump_line in dump_file:
                dump_line = dump_line.strip()
                if dump_line[:5] == "ITEM:":
                    item = dump_line[6:]  # Then check next line what happened
                    if item == "TIMESTEP":
                        n_frame += 1
                        if n_frame == snapshots + 1: #需要反复检查到底是不是多跑了一个
                            found = True
                        elif n_frame == snapshots + 2: # For the next frame close the loop
                            break
                elif found:
                    if item == "TIMESTEP":
                        pass
                        #step = int(l)
                    elif item == "NUMBER OF ATOMS":
                        n_atoms = int(dump_line)
                    elif item[:10] == "BOX BOUNDS":
                        dump_line = dump_line.split()
                        box_boundary.append([float(dump_line[0]), float(dump_line[1])])
                    elif item[:5] == "ATOMS":
                        dump_line = dump_line.split()
                        i_atom = dump_line[0]
                        x = float(dump_line[2])
                        y = float(dump_line[3])
                        z = float(dump_line[4])
                        x_position = (box_boundary[0][1] - box_boundary[0][0]) * x + box_boundary[0][0]
                        y_position = (box_boundary[1][1] - box_boundary[1][0]) * y + box_boundary[1][0]
                        z_position = (box_boundary[2][1] - box_boundary[2][0]) * z + box_boundary[2][0]
                        desc = atom_desc[dump_line[1]]
                        atom = Lammps_Atom(i_atom, dump_line[1], x_position, y_position, z_position, desc)
                        atoms_per_frame.append(atom)

            if len(atoms_per_frame) > 0:  # Check do we have previous frame to calculate
                if len(atoms_per_frame) != n_atoms:
                    sys.exit("Error! Number of atoms in dump file is different from loaded!\n")
                #print(atoms_per_frame[-1].x)
                #print(atoms_per_frame[-1].serial)
                #print(atoms_per_frame[-1].atom_type)
                #print(box_boundary)
                all_atoms_after_recover = build_all_atoms(atoms_per_frame, residue_index_to_chain_index, dna_flag, chain_length_list_cum, protein_chains_number, build_terminal_atoms=True)
                convert_to_pdb(all_atoms_after_recover, dna_flag, residue_index_to_chain_index, new_total_sequence_all, chain_length_list_cum, atom_type, pdb_type)

def main():
    #########
    # Prepare the input options
    parser = argparse.ArgumentParser(
        description="This script converts the lammps dump file to pdb file, works for multiple chain, capable of protein only and protein-DNA mode")
    parser.add_argument("dump", help="The file name of dump file", type=str)
    parser.add_argument("seq", help="The file name of protein sequence file", type=str)
    parser.add_argument("--dna", help="The dna mode", action="store_true", default=False)
    parser.add_argument("--dna_pdb", help="The dna topology pdb file name", type=str)
    parser.add_argument("-v", "--verbose", help="The print or mute mode", action="store_true", default=False)
    args = parser.parse_args()
    lammpsdump_file = args.dump
    protein_sequence_file = args.seq
    dna_flag = args.dna
    if dna_flag:
        dna_pdb_file = args.dna_pdb
    verbose = args.verbose
    #########

    #########
    # Initialization
    dna_chain_length = []
    dna_sequence_all = []
    total_sequence_all = []
    total_chain_length = []
    new_total_sequence_all = []
    residue_index_to_chain_index = {}
    if not dna_flag:
        atom_type = {'1': 'C', '2': 'N', '3': 'O', '4': 'C', '5': 'H', '6': 'C'}
        atom_desc = {'1': 'C-Alpha', '2': 'N', '3': 'O', '4': 'C-Beta', '5': 'H-Beta', '6': 'C-Prime'}
        pdb_type = {'1': 'CA', '2': 'N', '3': 'O', '4': 'CB', '5': 'HB', '6': 'C'}
    else:
        atom_type = {'1': 'P', '2': 'S', '3': 'N', '4': 'N', '5': 'N', '6': 'N',
                     '7': 'N', '8': 'N', '9': 'N', '10': 'N',
                     '11': 'N', '12': 'N', '13': 'N', '14': 'N',
                     '15': 'C', '16': 'N', '17': 'O', '18': 'C', '19': 'H', '20': 'C'
                     }
        atom_desc = {'1': 'P', '2': 'S', '3': 'B', '4': 'B', '5': 'B', '6': 'B',
                     '7': 'B', '8': 'B', '9': 'B', '10': 'B',
                     '11': 'B', '12': 'B', '13': 'B', '14': 'B',
                     '15': 'C-Alpha', '16': 'N', '17': 'O', '18': 'C-Beta', '19': 'H-Beta', '20': 'C-Prime'
                     }
        pdb_type = {'1': 'P', '2': 'S', '3': 'N', '4': 'N', '5': 'N', '6': 'N',
                    '7': 'N', '8': 'N', '9': 'N', '10': 'N',
                    '11': 'N', '12': 'N', '13': 'N', '14': 'N',
                    '15': 'CA', '16': 'N', '17': 'O', '18': 'CB', '19': 'HB', '20': 'C'
                    }
    #########

    #########
    # This part read pdb sequence file and dna topology file if given, then calculate the each chain length and sequence
    protein_sequence_all, protein_chain_length = load_protein_sequence_file(protein_sequence_file, verbose)
    total_chain_length.extend(protein_chain_length)
    total_sequence_all.extend(protein_sequence_all)
    protein_chains_number = len(protein_chain_length)

    if dna_flag:
        dna_sequence_all, dna_chain_length = read_dna_pdb(dna_pdb_file, verbose)
        total_chain_length.extend(dna_chain_length)
        total_sequence_all.extend(dna_sequence_all)
        dna_chains_number = len(dna_chain_length)

    if verbose:
        print (total_chain_length)
        print(total_sequence_all)

    chain_length_list_cum = np.cumsum(total_chain_length)
    if verbose:
        print("The cumulative length of each chain in the system is ")
        print(chain_length_list_cum)
    total_length = chain_length_list_cum[-1]
    #########

    #########
    # This part assign each chain residue index and its matched chain id
    for residue_index in range(chain_length_list_cum[-1]):
        index = 1
        for length in chain_length_list_cum:
            if residue_index + 1 > length:  # residue index start from 0 in dictionary, important!
                index = index + 1
        residue_index_to_chain_index[residue_index + 1] = chr(index + 64)

    if verbose:
        print("The residue index and its matched chain id is ")
        print(residue_index_to_chain_index)

    chain_id = 1
    for chain in total_sequence_all:
        if chain_id <= protein_chains_number:
            for i in chain:
                three_letter = protein_res[i]
                new_total_sequence_all.append(three_letter)
                #print(three_letter)
        else:
            for i in chain:
                three_letter = dna_res[i]
                new_total_sequence_all.append(three_letter)
                #print(three_letter)
        chain_id += 1

    if verbose:
        print("The new sequence in 3-letter mode is ")
        print(new_total_sequence_all)
    #########

    # Finally read lammps dump file and do all converts
    lammps_load_and_convert(lammpsdump_file, atom_type, atom_desc, pdb_type, dna_flag, new_total_sequence_all, residue_index_to_chain_index, chain_length_list_cum, protein_chains_number)

if __name__ == '__main__':
    main()
