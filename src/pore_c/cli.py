import logging
import os.path

import click
import click_log

from pore_c.tools.analysis import cis_trans_analysis as cis_trans_analysis_tool
from pore_c.tools.analysis import \
    comparison_contact_map as comparison_contact_map_tool
from pore_c.tools.analysis import matrix_correlation as matrix_correlation_tool
from pore_c.tools.analysis import \
    plot_contact_distances as plot_contact_distances_tool
from pore_c.tools.analysis import plot_contact_map as plot_contact_map_tool
from pore_c.tools.cluster_reads import cluster_reads as cluster_reads_tool
from pore_c.tools.cluster_reads import fragDAG_filter as fragDAG_filter_tool
from pore_c.tools.cluster_reads import \
    measure_overlaps as measure_overlaps_tool
from pore_c.tools.cluster_reads import \
    remove_contained_segments as remove_contained_segments_tool
from pore_c.tools.correction import \
    compute_contact_probabilities as compute_contact_probabilities_tool
from pore_c.tools.correction import \
    join_contact_matrices as join_contact_matrices_tool
from pore_c.tools.generate_fragments import \
    create_bin_file as create_bin_file_tool
from pore_c.tools.generate_fragments import create_fragment_map
from pore_c.tools.map_to_bins import bin_hic_data as bin_hic_data_tool
from pore_c.tools.map_to_bins import \
    fragment_bin_assignments as fragment_bin_assignments_tool
from pore_c.tools.map_to_frags import map_to_fragments as map_to_fragments_tool
from pore_c.tools.poreC_flatten import \
    flatten_multiway as flatten_multiway_tool
from pore_c.tools.poreC_flatten import \
    fragment_end_metrics as fragment_end_metrics_tool
from pore_c.tools.poreC_flatten import \
    make_salsa_bedfile as make_salsa_bedfile_tool

# from pore_c.tools.hic_split import split_hic_data as split_hic_data_tool

logger = logging.getLogger(__name__)
click_log.basic_config(logger)


class NaturalOrderGroup(click.Group):
    """Command group trying to list subcommands in the order they were added.
    """

    def list_commands(self, ctx):
        """List command names as they are in commands dict.
        """
        return self.commands.keys()


@click.group(cls=NaturalOrderGroup)
@click_log.simple_verbosity_option(logger)
def cli():
    """Pore-C tools"""
    pass


@cli.command(short_help="Virtual digest of reference genome.")
@click.argument("reference_fasta", type=click.Path(exists=True))
@click.argument("restriction_pattern")
@click.argument("bedfile", type=click.Path(exists=False))
@click.argument("hicref", type=click.Path(exists=False))
def generate_fragments(reference_fasta, restriction_pattern, bedfile, hicref):
    """
    Carry out a virtual digestion of RESTRICTION_PATTERN on REFERENCE_FASTA writing results to BEDFILE and HICREF.

    The RESTRICTION_PATTERN can be specified using either i) the name of a
    restriction enzyme as available in the Biopython Restriction package (eg.
    HindIII, case sensitive) ii) as a fixed with bin prefixed by 'bin:', or
    iii) as a python regular expression prefixed by 'regex:'. Note that the
    positions returned by these two methods will differ as the biopython method
    will return fragments delimited by the actual cut site, whereas the regular
    expression will return the positions of the recognition patterns.

    Some sample RESTRICTION_PATTERNs:

    \b
      - an enzyme name, note case sensitive: "HindIII"
      - a fixed width bin: "bin:50k"
      - a single site (HindIII): "regex:AAGCTT"
      - two sites (ecoRI and NotI): "regex:(GAATTC|GCGGCCGC)"
      - degenerate site (BglI): "regex:GCCNNNNNGGC"
      - degenerate site (ApoI): "regex:RAATY"

    The BEDFILE contains an entry for each of the fragments generated by the by the digest.

    \b
    chr\tstart\tend\tfragment_id
    \b

    The HICREF follows the Juicer format generated by this script:
    (https://github.com/aidenlab/juicer/blob/master/misc/generate_site_positions.py):

    \b
    chr site1 site2 site3 ... chrLength
    \b
    as in:
    1 11160 12411 12461 ... 249250621
    2 11514 11874 12160 ... 243199373
    3 60138 60662 60788 ... 198022430

    """
    logger.info(
        "Creating fragments from reference genome: {} and digestion pattern {}".format(
            reference_fasta, restriction_pattern
        )
    )
    faidx_file = reference_fasta + ".fai"
    if not os.path.exists(faidx_file):
        raise IOError(
            "Faidx file doesn't exist, please run 'samtools faidx {}'".format(
                reference_fasta
            )
        )
    frag_map = create_fragment_map(reference_fasta, restriction_pattern)
    logger.debug("Created FragmentMap: {}".format(frag_map))
    frag_map.save_to_bed(bedfile)
    logger.info("FragmentMap saved to bed file: {}".format(bedfile))
    frag_map.save_to_HiCRef(hicref)
    logger.info("FragmentMap saved to HicREF file: {}".format(hicref))


@cli.command(short_help="Cluster mappings by read")
@click.argument("input_bam", type=click.Path(exists=True))
@click.argument("keep_bam", type=click.Path(exists=False))
@click.argument("discard_bam", type=click.Path(exists=False))
@click.option(
    "--trim",
    default=20,
    type=int,
    help="The number of bases to ignore at the end of each aligned segment when calculating overlaps.",
)
@click.option(
    "--mapping_quality_cutoff",
    default=0,
    type=int,
    help="The minimum mapping quality for a alignment segment to be kept",
)
@click.option(
    "--alignment_stats",
    default=None,
    type=click.Path(exists=False),
    help="A filename for storing logged data about fragment assignment on a per-alignment basis.",
)
@click.option(
    "--contained",
    is_flag=True,
    help="If the contained flag is raised, cluster-filtering is not done, but instead alignments are removed based on whether they are fully contained in another alignment.",
)
def cluster_reads(
    input_bam,
    keep_bam,
    discard_bam,
    trim,
    contained,
    mapping_quality_cutoff,
    alignment_stats,
):
    if contained:
        if alignment_stats is not None:
            remove_contained_segments_tool(
                input_bam,
                keep_bam,
                discard_bam,
                mapping_quality_cutoff,
                alignment_stats,
            )
        else:
            remove_contained_segments_tool(
                input_bam, keep_bam, discard_bam, mapping_quality_cutoff
            )
    else:
        if alignment_stats is not None:
            num_reads, num_reads_kept, num_aligns, num_aligns_kept = cluster_reads_tool(
                input_bam,
                keep_bam,
                discard_bam,
                trim,
                mapping_quality_cutoff,
                alignment_stats,
            )
        else:
            num_reads, num_reads_kept, num_aligns, num_aligns_kept = cluster_reads_tool(
                input_bam, keep_bam, discard_bam, trim, mapping_quality_cutoff
            )


@cli.command(short_help="Cluster mappings by read")
@click.argument("input_bam", type=click.Path(exists=True))
@click.argument("keep_bam", type=click.Path(exists=False))
@click.argument("discard_bam", type=click.Path(exists=False))
@click.argument("aligner", default="bwa")
@click.argument("aligner_params", default="default")
@click.option(
    "--mapping_quality_cutoff",
    default=0,
    type=int,
    help="The minimum mapping quality for a alignment segment to be kept",
)
@click.option(
    "--filter_stats",
    default=None,
    type=click.Path(exists=False),
    help="A filename for storing logged data about fragment assignment on a per-alignment basis.",
)
@click.option(
    "--store_graph",
    default=None,
    type=click.Path(exists=False),
    help="A filename for storing a representation of the graph for logging purposes.",
)
def fragDAG_filter(
    input_bam,
    keep_bam,
    discard_bam,
    mapping_quality_cutoff,
    aligner,
    aligner_params,
    filter_stats,
    store_graph,
):
    if store_graph is not None:
        fragDAG_filter_tool(
            input_bam,
            keep_bam,
            discard_bam,
            mapping_quality_cutoff,
            aligner,
            aligner_params,
            filter_stats,
            store_graph,
        )
    else:
        fragDAG_filter_tool(
            input_bam,
            keep_bam,
            discard_bam,
            mapping_quality_cutoff,
            aligner,
            aligner_params,
            filter_stats,
        )


@cli.command(
    short_help="create a .poreC file from a namesorted alignment of poreC data"
)
@click.argument(
    "input_bed", type=click.Path(exists=True)
)  # bedtools overlap file between the filtered bam and the reference fragment file
@click.argument(
    "fragment_bed_file", type=click.Path(exists=True)
)  # A reference fragment bed file generated by the pore_c generate-fragments command.
@click.argument("output_porec", type=click.Path(exists=False))
@click.option(
    "--method",
    default="overlap",
    type=str,
    help="The method of determining fragment mapping of an alignment",
)
@click.option(
    "--stats",
    default=None,
    type=click.Path(exists=False),
    help="A filename for storing the per-mapping logging data about fragment mapping.",
)
def map_to_fragments(input_bed, fragment_bed_file, output_porec, method, stats):
    map_to_fragments_tool(input_bed, fragment_bed_file, output_porec, method, stats)


@cli.command(
    short_help="In each sequencing read, this tool measures the overlap intervals between all pairs of alignments (for diagnosing alignment filtering)."
)
@click.argument("input_bam", type=click.Path(exists=True))
@click.argument("output_table", type=click.Path(exists=False))
@click.option(
    "--no_zero",
    is_flag=True,
    help="for pairs of alignments that do not overlap, do not include a table entry. This cuts down the table size dramatically.",
)
def measure_overlaps(input_bam, output_table, no_zero):
    measure_overlaps_tool(input_bam, output_table, no_zero)


@cli.command(
    short_help="Flatten down a pore-C file filled with multiway contacts to a single specified contact dimension."
)
@click.argument("input_porec", type=click.Path(exists=True))
@click.argument("output_porec", type=click.Path(exists=False))
@click.option(
    "--sort",
    is_flag=True,
    help="Sort the monomers within each contact according to fragment ID. This does not sort the entries as they might need to be sorted for conversion to other formats or for visualisation tools..",
)
@click.option(
    "--size",
    default=2,
    type=int,
    help="The size of the generated contacts in the output file. Default is 2.",
)
@click.option(
    "--direct",
    is_flag=True,
    default=False,
    help="Decompose multiway contacts to pairwise by direct ligation, rather than by co-inclusion in a multiway contact.",
)
def flatten_multiway(input_porec, output_porec, size, sort, direct):
    flatten_multiway_tool(input_porec, output_porec, size, sort, direct)


@cli.command(
    short_help="Generate a reference bedfile of bin intervals provided a reference fasta index file and a bin size."
)
@click.argument("input_fai", type=click.Path(exists=True))
@click.argument("output_bin_bed", type=click.Path(exists=False))
@click.argument(
    "size", default=1000000, type=int
)  # 3 help="The bin size for the file. Default is 10**6 bp."
def create_bin_file(input_fai, output_bin_bed, size):
    create_bin_file_tool(input_fai, output_bin_bed, size)


@cli.command(
    short_help="Generate a mapping file which assigns fragments to bin intervals."
)
@click.argument("fragment_reference", type=click.Path(exists=True))
@click.argument("bin_reference", type=click.Path(exists=True))
@click.argument(
    "mapping_file_out", type=click.Path(exists=False)
)  # 3 help="The bin size for the file. Default is 10**6 bp."
def fragment_bin_assignments(fragment_reference, bin_reference, mapping_file_out):
    fragment_bin_assignments_tool(fragment_reference, bin_reference, mapping_file_out)


@cli.command(
    short_help="This command takes in a hictxt file, identifies the bin for each member of a pairwise contact and records it into a sparse .matrix raw contact file."
)
@click.argument("hictxt", type=click.Path(exists=True))
@click.argument("output_bin_matrix", type=click.Path(exists=False))
@click.argument("frag_bins", type=click.Path(exists=True))
def bin_hic_data(hictxt, output_bin_matrix, frag_bins):
    bin_hic_data_tool(hictxt, output_bin_matrix, frag_bins)


@cli.command(
    short_help="Splits hictxt file into a set of per-chromosome intrachromosomal contacts for normalisation, and an inter-chromosomal contacts dump file. This enables intrachromosomal correction at higher resolutions than are practically capable at a whole-genome scale, due to memory constraints."
)
@click.argument("input_hictxt", type=click.Path(exists=True))
@click.argument(
    "output_hictxt_prefix", type=click.Path(exists=False)
)  # this won't exist since it's just a prefix
@click.argument("output_inter_hictxt", type=click.Path(exists=False))
def split_hic_data(input_hictxt, output_hictxt_prefix, output_inter_hictxt):
    fragment_bin_assignments_tool(fragment_reference, bin_reference, mapping_file_out)


@cli.command(
    short_help="Takes in a corrected matrix file, and plots the distribution of contact distances."
)
@click.argument("ref_bin_file", type=click.Path(exists=True))
@click.argument("graph_file_out", type=click.Path(exists=False))
@click.argument("ec_matrix_files_in", type=click.Path(exists=True), nargs=-1)
def plot_contact_distances(ref_bin_file, graph_file_out, ec_matrix_files_in):
    plot_contact_distances_tool(ref_bin_file, graph_file_out, *ec_matrix_files_in)


@cli.command(
    short_help="Takes in a corrected matrix file, and plots a comparative contact heat map with raw and corrected values in lower and upper halves respectively."
)
@click.argument("matrix_file_in", type=click.Path(exists=True))
@click.argument("ref_bin_file", type=click.Path(exists=True))
@click.argument("graph_file_out", type=click.Path(exists=False))
@click.option(
    "--matrix_type",
    default="raw",
    type=click.Choice(["corrected", "raw", "compare", "contactprobability"]),
)
def plot_contact_map(matrix_file_in, ref_bin_file, graph_file_out, matrix_type):
    plot_contact_map_tool(matrix_file_in, ref_bin_file, graph_file_out, matrix_type)


# comparison_contact_map(matrix1_file_in: str,matrix2_file_in: str,ref_bin_file: str, heat_map_file_out: str, matrix_type: Optional[str] = "raw") -> None:
@cli.command(
    short_help="Takes in a pair of matrix files, and plots a comparative contact heat map between the two."
)
@click.argument("matrix1_file_in", type=click.Path(exists=True))
@click.argument("matrix2_file_in", type=click.Path(exists=True))
@click.argument("ref_bin_file", type=click.Path(exists=True))
@click.argument("graph_file_out", type=click.Path(exists=False))
@click.option(
    "--normalise",
    is_flag=True,
    default=False,
    help="Normalise the values so the greater data set doesn't wash out the data set with fewer contacts.",
)
@click.option(
    "--matrix_type",
    default="raw",
    type=click.Choice(["corrected", "raw", "compare", "contactprobability"]),
)
@click.option("--chr_file", default="None", type=str)
def comparison_contact_map(
    matrix1_file_in,
    matrix2_file_in,
    ref_bin_file,
    graph_file_out,
    matrix_type,
    normalise,
    chr_file,
):
    if chr_file == "None":
        comparison_contact_map_tool(
            matrix1_file_in,
            matrix2_file_in,
            ref_bin_file,
            graph_file_out,
            matrix_type,
            normalise,
        )
    else:
        comparison_contact_map_tool(
            matrix1_file_in,
            matrix2_file_in,
            ref_bin_file,
            graph_file_out,
            matrix_type,
            normalise,
            chr_file,
        )


@cli.command(
    short_help="Takes in a pair of corrected matrix files, and calculates the pearson coefficient of the individual matrix values that are non-zero. Generates a correlation plot for non-zero values."
)
@click.argument("matrix1_file_in", type=click.Path(exists=True))
@click.argument("matrix2_file_in", type=click.Path(exists=True))
@click.argument("plot_out", type=click.Path(exists=False))
@click.argument("result_out", type=click.Path(exists=False))
@click.argument("data_out", type=click.Path(exists=False))
@click.option("--matrix_type", default="raw", type=click.Choice(["corrected", "raw"]))
def matrix_correlation(
    matrix1_file_in, matrix2_file_in, plot_out, result_out, data_out, matrix_type
):
    matrix_correlation_tool(
        matrix1_file_in, matrix2_file_in, plot_out, result_out, data_out, matrix_type
    )


@cli.command(
    short_help="Takes in a corrected matrix file, and generates a cis-trans plot (for all non-zero matrix rows, plot the ratio of cis contacts to trans contacts). Calculates the cis/trans contact ratio."
)
@click.argument("ec_matrix_file_in", type=click.Path(exists=True))
@click.argument("ref_bin_file", type=click.Path(exists=True))
@click.argument("data_file_out", type=click.Path(exists=False))
@click.argument("results_file_out", type=click.Path(exists=False))
@click.argument("scatter_map_file_out", type=click.Path(exists=False))
def cis_trans_analysis(
    ec_matrix_file_in,
    ref_bin_file,
    results_file_out,
    data_file_out,
    scatter_map_file_out,
):
    cis_trans_analysis_tool(
        ec_matrix_file_in,
        ref_bin_file,
        results_file_out,
        data_file_out,
        scatter_map_file_out,
    )


@cli.command(
    short_help="Applies zero-masking, extreme value masking and iterative correction and eigenvector decomposition to a raw matrix file."
)
@click.argument("matrix_file_in", type=click.Path(exists=True))
@click.argument(
    "bin_ref", type=click.Path(exists=True)
)  # a reference bin bed file. This is only used to create the initial matrix based on the number of bins in the genome.
@click.argument(
    "corrected_matrix_file_out", type=click.Path(exists=False)
)  # this will be identical to the input file, but with additional fields for cP and corrected count number
@click.option(
    "--correction_method",
    default="SK",
    type=str,
    help="The correction method used. SK = Sinkhorn-Knopp, KR = Knight Ruiz. KR is not yet implemented.",
)
@click.option(
    "--ci",
    default=0.999,
    type=float,
    help="In order to prevent artifacts in correction due to saturated data, matrix values outside the indicated confidence interval about the mean can be masked.",
)
@click.option(
    "--mask_zeros",
    is_flag=True,
    default=True,
    help="Indicates whether zero values matrix positions be masked from the iterative correction process. This is true by default.",
)
@click.option(
    "--max_iter",
    default=1000,
    type=int,
    help="The maximum iterations of correction allowed on the sample.",
)
@click.option(
    "--epsilon",
    default=0.0001,
    type=float,
    help="The correction-tolerance that indicates successful correction.",
)
@click.option(
    "--eigen",
    is_flag=True,
    default=False,
    help="Calculates the first two eigenvectors for the matrix and includes them in the .matrix file.",
)
def compute_contact_probabilities(
    matrix_file_in,
    bin_ref,
    corrected_matrix_file_out,
    correction_method,
    ci,
    mask_zeros,
    epsilon,
    max_iter,
    eigen,
):
    compute_contact_probabilities_tool(
        matrix_file_in,
        bin_ref,
        corrected_matrix_file_out,
        correction_method,
        ci,
        mask_zeros,
        epsilon,
        max_iter,
        eigen,
    )


@cli.command(
    short_help="Takes in a series of .matrix files, and joins them into a single .matrix file."
)
@click.argument("ref_bin_file", type=click.Path(exists=True))
@click.argument("matrix_file_out", type=click.Path(exists=False))
@click.argument("matrix_files_in", type=click.Path(exists=True), nargs=-1)
def join_contact_matrices(ref_bin_file, matrix_file_out, matrix_files_in):
    print("joining:", matrix_files_in)
    print("using bin_ref:", ref_bin_file)
    print("and printing to:", matrix_file_out)
    join_contact_matrices_tool(ref_bin_file, matrix_file_out, *matrix_files_in)


@cli.command(
    short_help="Generates a bedfile in the form required for the Hi-C hybrid genome assembly tool SALSA."
)
@click.argument("hictxt_file_in", type=click.Path(exists=True))
@click.argument("bedfile_out", type=click.Path(exists=False))
@click.argument("frag_bed_ref", type=click.Path(exists=True))
def make_salsa_bedfile(hictxt_file_in, bedfile_out, frag_bed_ref):
    make_salsa_bedfile_tool(hictxt_file_in, bedfile_out, frag_bed_ref)


@cli.command(
    short_help="calculates distances from the start and end of each alignment to the nearest reference restriction fragment."
)
@click.argument("bam_file_in", type=click.Path(exists=True))
@click.argument("csv_out", type=click.Path(exists=False))
@click.argument("hicref", type=click.Path(exists=True))
def fragment_end_metrics(bam_file_in, csv_out, hicref):
    fragment_end_metrics_tool(bam_file_in, csv_out, hicref)
