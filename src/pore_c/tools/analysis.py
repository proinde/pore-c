from typing import Optional

from collections import defaultdict, Counter

import numpy as np
import gzip
import matplotlib
matplotlib.use('agg')
import matplotlib.pyplot as plt
import matplotlib.colors as colors

from scipy.stats import pearsonr
from dataclasses import dataclass

@dataclass
class Matrix_Entry:
    bin1: int
    bin2: int
    raw_counts: float

    contact_probability: float = -1.0
    corrected_counts: float = -1.0
    E1: float = 0.0
    E2: float = 0.0

    @classmethod
    def from_string(cls, entry):
        l = entry.strip().split()
        for x in range(2):
            l[x] = int(l[x])
        l[2] = float(l[2])
        if len(l) > 3:
            for x in range(2,len(l)):
                l[x] = float(l[x])
        return cls(*l)

    def to_string(self):
        if self.contact_probability != 0.0 and self.corrected_counts != 0.0 and self.E1 != 0.0 and self.E2 != 0.0:
            return "{bin1} {bin2} {raw_counts} {contact_probability} {corrected_counts} {E1} {E2}\n".format(bin1 = self.bin1,
                                                                                                          bin2 = self.bin2,
                                                                                                          raw_counts = self.raw_counts,
                                                                                                          contact_probability = self.contact_probability,
                                                                                                          corrected_counts = self.corrected_counts,
                                                                                                          E1 = self.E1,
                                                                                                          E2 = self.E2)
        else:
            return "{bin1} {bin2} {raw_counts}\n".format(bin1 = self.bin1,
                                                       bin2 = self.bin2,
                                                       raw_counts = self.raw_counts)

def plot_contact_distances(EC_matrix_file_in: str,ref_bin_file: str,  graph_file_out: str) -> None:

    chr_sizes =  {}

    bin_size = -1
    for entry in gzip.open(ref_bin_file,'rt'):
        l = entry.strip().split()
        if l in ["M"]:
            continue
        l[3] = int(l[3])
        if bin_size == -1:
            bin_size = int(l[2]) - int(l[1])
        if l[0] not in chr_sizes:
            chr_sizes[l[0]] = l[3]
        elif chr_sizes[l[0]] < l[3]:
            chr_sizes[l[0]] = l[3]

    min_max_size = min(chr_sizes.values())
    print('distance cap: {}'.format(min_max_size))

    bin_data = {}

    for entry in gzip.open(ref_bin_file):
        l = entry.strip().split()
        l[1] = int(l[1])
        l[2] = int(l[2])
        l[3] = int(l[3])
        bin_data[int(l[3])] = l

    data = Counter()

    for entry in map(Matrix_Entry.from_string, open(EC_matrix_file_in)):
        bin1 = bin_data[entry.bin1]
        bin2 = bin_data[entry.bin2]
        if bin1[1] > bin2[1]:
            continue #forces removal of redundant entries
        if bin1[0] == bin2[0]:
            #intrachromosomal
            if bin2[3] - bin1[3] <= min_max_size:
                data[bin_size * (bin2[3] - bin1[3])] += l[3]

    fig, ax = plt.subplots(1,figsize=(12,6))
    plt.title("{} Contact Distance Distribution".format(EC_matrix_file_in))
    distances, counts = zip(*sorted(data.items(),key = lambda x: x[0]))
    print(distances[:100])
    print(counts[:100])

    distances_Mb = np.array(np.array(distances) / 10**6,dtype = int)
    print(distances_Mb[:100])    
    ax.plot(distances_Mb,counts, 'k:')
    ax.set_xlabel("distance (Mbp)", fontsize = "x-small")
    ax.set_ylabel("Contacts", fontsize = "x-small")
    ax.set_yscale('log')
    ax.set_xscale('log')
    ax.set_xlim(0,min_max_size)
    ax.set_ylim(100,max(counts))
    fig.savefig(graph_file_out)


def plot_contact_map(matrix_file_in: str,ref_bin_file: str, heat_map_file_out: str, matrix_type: Optional[str] = "raw") -> None:

    names = []
    markers = []
    lastChr = False
    size = 0
    for idx, entry in enumerate(gzip.open(ref_bin_file,'rt')):
        l = entry.strip().split()
        if not lastChr:
            lastChr = l[0]
        if lastChr != l[0]:
            markers.append(idx - 1 - .5)
            names.append(lastChr)
        size = idx
        lastChr = l[0]

    #tail entry
    markers.append(idx - 0.5)
    _markers = [0] + markers
    minor_markers = [ (x+y) / 2 for x,y in zip(_markers[:-1],_markers[1:])]
    names.append(l[0])

    
    matrix = np.zeros((size+1,size+1))
    for entry in map(Matrix_Entry.from_string, open(matrix_file_in)):
        if entry.bin1 == entry.bin2:
            #the diagonal is never informative and only serves to scale down the rest of the data in the colorspace
            continue 
        if matrix_type == "corrected":
            matrix[entry.bin1,entry.bin2] = entry.corrected_counts
            matrix[entry.bin2,entry.bin1] = entry.corrected_counts
        elif matrix_type == "raw":
            matrix[entry.bin1,entry.bin2] = entry.raw_counts
            matrix[entry.bin2,entry.bin1] = entry.raw_counts
        elif matrix_type == "compare":
            matrix[entry.bin1,entry.bin2] = entry.raw_counts
            matrix[entry.bin2,entry.bin1] = entry.corrected_counts
        elif matrix_type == "contactprobability":
             matrix[entry.bin1,entry.bin2] = entry.contact_probability
             matrix[entry.bin2,entry.bin1] = entry.contact_probability

    fig, ax = plt.subplots(1,figsize= (12,6), dpi = 500)

    matrix[matrix < 2] = .1

    plt.imshow(matrix,norm=colors.LogNorm(vmin=.1, vmax=matrix.max()), cmap="gist_heat_r")


    null_markers = [""] * len(markers)
    ax.set_yticks(markers)
    ax.set_yticks(minor_markers, minor = True)
    ax.set_yticklabels(null_markers)
    ax.set_yticklabels(names, minor = True)
    ax.set_xticks(markers)
    ax.set_xticklabels(null_markers)
    ax.set_xticks(minor_markers, minor = True)
    ax.set_xticklabels(names, minor = True,rotation=90)

    ax.tick_params( axis="both", which="minor",labelsize= 'xx-small',length=0)
    ax.tick_params( axis="both", which="major",labelsize= 'xx-small',length=3)

    #TODO: chromosome names halfway between the major ticks

#    print("markers:",markers)
#    print("minor markers:",minor_markers)
#    print("names:",names)
#    print("size:",size)

    ax.vlines(markers,0,size, linestyle = ":", linewidth = .5, alpha=0.4, color = '#357BA1')
    ax.hlines(markers,0,size, linestyle = ":", linewidth = .5, alpha=0.4, color = '#357BA1')

    if matrix_type == "compare":
        ax.set_xlabel("corrected counts")
        ax.set_ylabel("raw counts")
        ax.yaxis.set_label_position("right")

    plt.savefig(heat_map_file_out)


def comparison_contact_map(matrix1_file_in: str,matrix2_file_in: str,ref_bin_file: str, heat_map_file_out: str, matrix_type: Optional[str] = "raw", normalise: Optional[bool] = True, chr_file: Optional[str] = "None" ) -> None:


    if chr_file != "None":

        chrs = set()
        for entry in open(chr_file):
            chrs.add(entry.strip())

#        print(chrs)
        names = []
        markers = []
        lastChr = False
        size = 0
        selected_binranges = []
        absolute_binranges = []
        idx = 0

        for net_idx, entry in enumerate(gzip.open(ref_bin_file,'rt')):
            l = entry.strip().split()
            if not lastChr:
                lastChr = l[0]
                intrachr_idx = 0

            if lastChr != l[0]:
#                print(l)
                if lastChr in chrs:
                    markers.append(idx + intrachr_idx - .5)
                    names.append(lastChr)
                    selected_binranges.extend(list(range(idx,idx + intrachr_idx)))
                    absolute_binranges.extend(list(range(net_idx - intrachr_idx, net_idx)))
                    idx +=  intrachr_idx
                intrachr_idx = 0
            intrachr_idx += 1
            lastChr = l[0]

        if lastChr in chrs:
            markers.append(intrachr_idx - 0.5)
            names.append(lastChr)
            selected_binranges.extend(list(range(idx,idx + intrachr_idx)))
            absolute_binranges.extend(list(range(net_idx - intrachr_idx, net_idx)))

        _markers = [0] + markers
        minor_markers = [ (x+y) / 2 for x,y in zip(_markers[:-1],_markers[1:])]

#        print(selected_binranges)
#        print(absolute_binranges)
#        print(names,minor_markers)
        size = selected_binranges[-1]
        bin_mappings = dict(zip(absolute_binranges, selected_binranges))

    else:

        names = []
        markers = []
        lastChr = False
        size = 0
        for idx, entry in enumerate(gzip.open(ref_bin_file,'rt')):
            l = entry.strip().split()
            if not lastChr:
                lastChr = l[0]
            if lastChr != l[0]:
                markers.append(idx - 1 - .5)
                names.append(lastChr)
            size = idx
            lastChr = l[0]

        markers.append(idx - 0.5)
        _markers = [0] + markers
        minor_markers = [ (x+y) / 2 for x,y in zip(_markers[:-1],_markers[1:])]
        names.append(l[0])

###    
    matrix = np.zeros((size + 1,size + 1)) + .1

    upper_sum = 0
    for entry in map(Matrix_Entry.from_string, open(matrix1_file_in)):
        if entry.bin1 == entry.bin2:
            #the diagonal is never informative and only serves to scale down the rest of the data in the colorspace
            continue 

        if chr_file != "None":
            if entry.bin1 in bin_mappings and entry.bin2 in bin_mappings:
                x = bin_mappings[entry.bin1]
                y = bin_mappings[entry.bin2]
                if matrix_type == "corrected":
                    matrix[x,y] = entry.corrected_counts
                    upper_sum += entry.corrected_counts
                elif matrix_type == "raw":
                    matrix[x,y] = entry.raw_counts
                    upper_sum += entry.raw_counts
            else:
                continue

        else:
            if matrix_type == "corrected":
                matrix[entry.bin1,entry.bin2] = entry.corrected_counts
                upper_sum += entry.corrected_counts
            elif matrix_type == "raw":
                matrix[entry.bin1,entry.bin2] = entry.raw_counts
                upper_sum += entry.raw_counts


    lower_sum = 0
    for entry in map(Matrix_Entry.from_string, open(matrix2_file_in)):
        if entry.bin1 == entry.bin2:
            #the diagonal is never informative and only serves to scale down the rest of the data in the colorspace
            continue 
        if chr_file != "None":
            if entry.bin1 in bin_mappings and entry.bin2 in bin_mappings:
                x = bin_mappings[entry.bin1]
                y = bin_mappings[entry.bin2]
                if matrix_type == "corrected":
                    matrix[y,x] = entry.corrected_counts
                    lower_sum += entry.corrected_counts
                elif matrix_type == "raw":
                    matrix[y,x] = entry.raw_counts
                    lower_sum += entry.raw_counts
            else:
                continue
        else:
            if matrix_type == "corrected":
                matrix[entry.bin2,entry.bin1] = entry.corrected_counts
                lower_sum += entry.corrected_counts
            elif matrix_type == "raw":
                matrix[entry.bin2,entry.bin1] = entry.raw_counts
                lower_sum += entry.raw_counts
    
    if normalise:

        print('normalising two datasets.')
        print('lower factor: X  / {}'.format(lower_sum))
        print('upper factor: X  / {}'.format(upper_sum))

        if upper_sum > lower_sum:
            factor = lower_sum / upper_sum
            flag = True
        else:
            factor = upper_sum / lower_sum
            flag = False
        for x in range(size):
            for y in range(size):
                if x  == y:
                    continue
                elif x > y: 
                    if flag:
                        matrix[x,y] = matrix[x,y] /factor
                else:
                    if not flag:
                        matrix[x,y] = matrix[x,y] /factor


    fig, ax = plt.subplots(1,figsize= (12,12), dpi = 2000)

    plt.imshow(matrix,norm=colors.LogNorm(vmin=1, vmax=matrix.max()), cmap="gist_heat_r")
#    plt.imshow(matrix, cmap="gist_heat_r")


    null_markers = [""] * len(markers)
    ax.set_yticks(markers)
    ax.set_yticks(minor_markers, minor = True)
    ax.set_yticklabels(null_markers)
    ax.set_yticklabels(names, minor = True)
    ax.set_xticks(markers)
    ax.set_xticklabels(null_markers)
    ax.set_xticks(minor_markers, minor = True)
    ax.set_xticklabels(names, minor = True,rotation=90)

    ax.set_ylabel(matrix1_file_in)
    ax.set_xlabel(matrix2_file_in)
    ax.yaxis.set_label_position("right")    

    ax.tick_params( axis="both", which="minor",labelsize= 'xx-small',length=0)
    ax.tick_params( axis="both", which="major",labelsize= 'xx-small',length=3)

    ax.vlines(markers,0,size, linestyle = ":", linewidth = .5, alpha=0.4, color = '#357BA1')
    ax.hlines(markers,0,size, linestyle = ":", linewidth = .5, alpha=0.4, color = '#357BA1')

    plt.savefig(heat_map_file_out)


#this is done on corrected values
def cis_trans_analysis(EC_matrix_file_in: str, ref_bin_file: str, data_file_out:str, results_file_out: str, scatter_map_file_out: str ) -> None:

    #coordinate the bins with their chromosomes based on the 
    chrs = {}
    for entry in gzip.open(ref_bin_file,'rt'):
        l = entry.strip().split()
        chrs[l[3]] = l[0]

    #key these on matrix bin with values equal to count
    intra = Counter()
    inter = Counter()
    for entry in open(EC_matrix_file_in):
        l = entry.strip().split()
        l[0] = int(l[0])
        l[1] = int(l[1])
        if l[0] > l[1]:
            continue
        c_count = float(l[2]) # raw counts
        #c_count = float(l[2]) #corrected counts
        
        if chrs[l[0]] == chrs[l[1]]:
            intra[l[0]] += c_count
        else:
            inter[l[0]] += c_count


    shared = sorted(list(set(intra.keys()).intersection(set(inter.keys()))))
    print("data sizes:")
    print("intra:",len(intra))
    print("inter:",len(inter))
    print("shared data coordinates:",len(shared))
    fig, ax = plt.subplots(1,figsize= (12,6))
    intra_values = np.array([intra[x] for x in shared])
    inter_values = np.array([inter[x] for x in shared])

    print("max intra:",max(intra_values))
    print("max inter:",max(inter_values))
    ratios = intra_values / inter_values
    plt.hexbin(intra_values,inter_values,gridsize = (200,200))

    ax.set_xlabel("cis counts")
    ax.set_ylabel("trans counts")
#    ax.set_yscale('log')
#    ax.set_xscale('log')

    plt.savefig(scatter_map_file_out)

    f_out = open(data_file_out,'w')
    for idx, val in enumerate( shared):
        f_out.write("{}\t{}\n".format(val, ratios[idx]))

    f_out.close()

    f_out = open(results_file_out,'w')
    f_out.write("intra,inter,ratio\n")
    x = np.sum(intra_values)
    y = np.sum(inter_values)

    ratio = x / y
    print(x,y, ratio)

    f_out.write("{},{},{}".format(x, y, ratio))
    f_out.close()
    

####
#plots a log-log scatter plot of point-matched raw count values and calculates the pearson correlation coefficient for that distribution.
def matrix_correlation(matrix1_file_in: str, matrix2_file_in: str, plot_out: str, result_out:str) -> None:
    matrix1_data = {}
    matrix2_data = {}
    for entry in map(Matrix_Entry.from_string, open(matrix1_file_in)):
        matrix1_data[(entry.bin1,entry.bin2)] = entry.raw_counts

    for entry in map(Matrix_Entry.from_string, open(matrix2_file_in)):
        matrix2_data[(entry.bin1,entry.bin2)] = entry.raw_counts

    matrix1_nonzero = set(matrix1_data.keys())
    shared_nonzero = list(matrix1_nonzero.intersection(set(matrix2_data.keys())))

    shared_matrix1 = [matrix1_data[x] for x in shared_nonzero]
    shared_matrix2 = [matrix2_data[x] for x in shared_nonzero]


    r, p = pearsonr(shared_matrix1, shared_matrix2)
    fig, ax = plt.subplots(1,figsize= (12,6))

    plt.plot(shared_matrix1,shared_matrix2, 'b,')
    ax.set_yscale('log')
    ax.set_xscale('log')
    ax.set_xlabel("{} distances (bp)".format(matrix1_file_in))
    ax.set_ylabel("{} distances (bp)".format(matrix2_file_in))
    plt.savefig(plot_out)

    f_out = open(result_out,'w')

    header = "matrix1,matrix2,shared_points,pearson_coeff,p_val\n"
    form = "{matrix1},{matrix2},{shared_points},{pearson_coeff},{p_val}\n"
    f_out.write(header)
    f_out.write(form.format(matrix1= matrix1_file_in,
                            matrix2 = matrix2_file_in,
                            shared_points = len(shared_nonzero),
                            pearson_coeff = r,
                            p_val = p)
            )
    f_out.close()


