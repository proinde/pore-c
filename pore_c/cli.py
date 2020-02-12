import json
import logging
from pathlib import Path

import click
from intake import open_catalog

import pore_c.catalogs as catalogs

from .catalogs import ReferenceGenomeCatalog
from .cli_utils import expand_output_prefix, filename_matches_regex
from .config import INPUT_REFGENOME_REGEX
from .settings import setup_logging


logger = setup_logging()


class NaturalOrderGroup(click.Group):
    """Command group trying to list subcommands in the order they were added.
    """

    def list_commands(self, ctx):
        """List command names as they are in commands dict.
        """
        return self.commands.keys()


def command_line_json(ctx, param, value):
    # TODO: add support for json from file
    if value is None:
        return {}
    try:
        res = json.loads(value)
    except Exception as exc:  # noqa: F841
        logger.exception("Not valid json")
        raise
    return res


@click.group(cls=NaturalOrderGroup)
@click.option("-v", "--verbosity", count=True, help="Increase level of logging information, eg. -vvv")
@click.option("--quiet", is_flag=True, default=False, help="Turn off all logging")
@click.pass_context
def cli(ctx, verbosity, quiet):
    """Pore-C tools

    A suite of tools designed to analyse Oxford Nanopore reads with multiway chromatin contacts.
    """
    if quiet:
        logger.setLevel(logging.CRITICAL)
    elif verbosity > 0:
        LOG_LEVELS = [logging.CRITICAL, logging.ERROR, logging.WARNING, logging.INFO, logging.DEBUG]
        offset = 2
        idx = min(len(LOG_LEVELS) - 1, offset + verbosity)
        logger.setLevel(LOG_LEVELS[idx])
    else:
        logger.setLevel(logging.INFO)
    logger.debug("Logger set up")


@cli.group(cls=NaturalOrderGroup, short_help="Pre-process reference genome files.")
@click.pass_context
def refgenome(ctx):
    pass


@refgenome.command(short_help="Pre-process a reference genome")
@click.argument("reference_fasta", type=click.Path(exists=True), callback=filename_matches_regex(INPUT_REFGENOME_REGEX))
@click.argument("output_prefix", callback=expand_output_prefix(ReferenceGenomeCatalog))
@click.option("--genome-id", type=str, help="An ID for this genome assembly")
@click.pass_context
def prepare(ctx, reference_fasta, output_prefix, genome_id):
    """Pre-process a reference genome for use by pore-C tools.



    \b
        <output_prefix>.catalog.yaml
        <output_prefix>.fa
        <output_prefix>.chromsizes
        <output_prefix>.metadata.csv


    This cool makes a bgzipped copy of the reference genome along with some ancillary
    files for use by other tools. The paths to these files, along with metadata
    about the genome are stored in an intake yaml catalog.
    """
    from pore_c.datasources import IndexedFasta
    import pandas as pd
    import re
    import subprocess as sp
    import pysam
    from shutil import copyfile

    logger.info(f"Adding reference genome under prefix: {output_prefix}")
    file_paths = ctx.meta["file_paths"]
    reference_fasta = Path(reference_fasta)

    parts_m = re.compile(INPUT_REFGENOME_REGEX).match(reference_fasta.name)
    stem, _, compression = parts_m.groups()
    if not genome_id:
        genome_id = stem

    dest_fasta = file_paths["fasta"]
    if compression == ".gz":
        comd = f"gunzip -cd {reference_fasta} > {dest_fasta}"
        logger.debug(f"Decompressing source fasta: {comd}")
        try:
            sp.check_call(comd, shell=True)
        except Exception as exc:  # noqa: F841
            logger.exception(f"Error creating bgzipped reference: {dest_fasta}")
            raise
    else:
        logger.debug("Copying {reference_fasta} to {dest_fasta}")
        copyfile(reference_fasta, dest_fasta)
    logger.debug("Creating faidx file")
    pysam.faidx(str(dest_fasta))

    ref_source = IndexedFasta(dest_fasta)
    ref_source.discover()
    chrom_lengths = {c["chrom"]: c["length"] for c in ref_source.metadata["chroms"]}
    chrom_df = pd.DataFrame(ref_source.metadata["chroms"])[["chrom", "length"]]
    chrom_df.to_csv(file_paths["chrom_metadata"], index=False)
    chrom_df.to_csv(file_paths["chromsizes"], sep="\t", header=None, index=False)
    metadata = {"chrom_lengths": chrom_lengths, "genome_id": genome_id}
    rg_cat = ReferenceGenomeCatalog.create(file_paths, metadata, {})
    logger.info("Added reference genome: {}".format(str(rg_cat)))


@refgenome.command(short_help="Virtual digest of a reference genome.")
@click.argument("reference_catalog", type=click.Path(exists=True))
@click.argument("cut_on")
@click.argument("output_prefix")
@click.option("-n", "--n_workers", help="The number of dask_workers to use", default=1)
def virtual_digest(reference_catalog, cut_on, output_prefix, n_workers):
    """
    Carry out a virtual digestion of the genome listed in a reference catalog.

    Required arguments:
        - reference_catalog: An intake catalog produced by `pore_c refgenome catalog`
        - cut_on: An enzyme name to do the digest (see below for more details).
        - output_prefix:

    \b

    Some sample CUT_ONs:

    \b
      - an enzyme name, note case sensitive: "enzyme:HindIII"
      - a fixed width bin: "bin:50k"
      - a single site (HindIII): "regex:AAGCTT"
      - two sites (ecoRI and NotI): "regex:(GAATTC|GCGGCCGC)"
      - degenerate site (BglI): "regex:GCCNNNNNGGC"
      - degenerate site (ApoI): "regex:RAATY"

    """
    from pore_c.catalogs import ReferenceGenomeCatalog, VirtualDigestCatalog
    from pore_c.analyses.reference import create_virtual_digest

    rg_cat = ReferenceGenomeCatalog(reference_catalog)
    digest_type, digest_param = cut_on.split(":")
    assert digest_type in ["bin", "enzyme", "regex"]

    file_paths = VirtualDigestCatalog.generate_paths(output_prefix)
    path_kwds = {key: val for key, val in file_paths.items() if key != "catalog"}

    frag_df = create_virtual_digest(rg_cat.fasta, digest_type, digest_param, n_workers=n_workers, **path_kwds)

    metadata = {"digest_type": digest_type, "digest_param": digest_param, "num_fragments": len(frag_df)}
    file_paths["refgenome_catalog"] = Path(reference_catalog)
    vd_cat = VirtualDigestCatalog.create(file_paths, metadata, {})
    logger.debug("Created Virtual Digest catalog: {}".format(vd_cat))


@refgenome.command(short_help="Create a hicRef file for a virtual digest.")
@click.argument("virtual_digest_catalog", type=click.Path(exists=True))
@click.argument("hicref", type=click.Path(exists=False))
def to_hicref(virtual_digest_catalog, hicref):
    """
    Carry out a virtual digestion of the genome listed in a reference catalog.
    """
    from pore_c.catalogs import VirtualDigestCatalog

    vd_cat = VirtualDigestCatalog(virtual_digest_catalog)

    frag_df = vd_cat.fragments.to_dask().compute()
    with open(hicref, "w") as fh:
        for chrom, endpoints in frag_df.groupby("chrom")["end"].agg(lambda x: " ".join(map(str, x))).items():
            fh.write(f"{chrom} {endpoints}\n")

    logger.debug(f"Wrote hicRef file to {hicref}")


@cli.group(cls=NaturalOrderGroup, short_help="Analyse raw reads")
def reads():
    pass


@reads.command(short_help="Create a catalog file for a set of reads")  # noqa: F811
@click.argument("fastq", type=click.Path(exists=True))
@click.argument("output_prefix")
@click.option("--min-read-length", help="The minimum length read to run through porec", default=1)
@click.option(
    "--max-read-length",
    help="The maximum length read to run through porec. Note that bwa mem can crash on very long reads",
    default=500_000,
)
@click.option("--user-metadata", callback=command_line_json, help="Additional user metadata to associate with this run")
def catalog(fastq, output_prefix, min_read_length, max_read_length, user_metadata):
    """Preprocess a reference genome for use by pore_c tools
    """
    from pore_c.analyses.reads import filter_fastq

    file_paths = catalogs.RawReadCatalog.generate_paths(output_prefix)
    path_kwds = {key: val for key, val in file_paths.items() if key != "catalog"}
    summary = filter_fastq(
        input_fastq=fastq, min_read_length=min_read_length, max_read_length=max_read_length, **path_kwds
    )

    catalog = catalogs.RawReadCatalog.create(file_paths, {"summary_stats": summary}, user_metadata)
    logger.info("Created catalog for results: {}".format(catalog))

    c1 = open_catalog(str(file_paths["catalog"]))
    logger.info(c1)


@cli.group(cls=NaturalOrderGroup, short_help="Analyse aligned porec reads")
def alignments():
    pass


@alignments.command(short_help="Reformat a BAM file to have a unique read name per alignment")
@click.argument("input_sam", type=click.File("r"))
@click.argument("output_sam", type=click.File("w"))
def reformat_bam(input_sam, output_sam):
    """Reformat INPUT_SAM to add a read_index and alignment_index to the query_name

    """
    import pysam

    infile = pysam.AlignmentFile(input_sam)
    outfile = pysam.AlignmentFile(output_sam, template=infile)
    read_indices = {}
    for align_idx, align in enumerate(infile.fetch(until_eof=True)):
        read_id = align.query_name
        read_idx = read_indices.get(read_id, None)
        if read_idx is None:
            read_idx = len(read_indices)
            read_indices[read_id] = read_idx
        align.set_tag(tag="BX", value=align.query_name, value_type="Z")
        align.query_name = f"{read_id}:{read_idx}:{align_idx}"
        outfile.write(align)
    outfile.close()


@alignments.command(short_help="Parse a namesortd bam to pore-C alignment format")
@click.argument("input_bam", type=click.Path(exists=True))
@click.argument("output_table", type=click.Path(exists=False))
@click.option("-n", "--n_workers", help="The number of dask_workers to use", default=1)
@click.option("--chunksize", help="Number of reads per processing chunk", default=50000)
@click.option("--phased", is_flag=True, default=False, help="Set if using a haplotagged BAM file")
def create_table(input_bam, output_table, n_workers, chunksize, phased):
    """Extract info required for fragment assignment from the BAM file

    """
    from pore_c import model
    from pore_c.io import TableWriter
    from pore_c.utils import DaskExecEnv

    import dask.dataframe as dd
    import os
    from toolz import partition_all
    from pysam import AlignmentFile

    tmp_table = output_table + ".tmp"
    chunk_writer = TableWriter(tmp_table)
    af = AlignmentFile(input_bam)
    chrom_order = list(af.references)
    assert "NULL" not in chrom_order
    chrom_order.append("NULL")
    logger.debug(f"Chromosome order {chrom_order}")

    for chunk_idx, aligns in enumerate(partition_all(chunksize, af)):
        align_df = model.AlignmentRecord.to_dataframe(
            [model.AlignmentRecord.from_aligned_segment(a) for a in aligns], chrom_order=chrom_order
        )
        chunk_writer(align_df)

    chunk_writer.close()

    logger.debug(f"Wrote {chunk_writer.row_counter} rows in {chunk_writer.counter} batch to {tmp_table}")
    with DaskExecEnv(n_workers=n_workers, empty_queue=True):
        logger.debug("Re-sorting alignment table by read_idx")
        (
            dd.read_parquet(tmp_table, engine="pyarrow")
            .set_index("read_idx")
            .to_parquet(output_table, engine="pyarrow", version="2.0")
        )
    logger.info(f"Wrote {chunk_writer.row_counter} alignments to {output_table}")
    os.unlink(tmp_table)


@alignments.command(short_help="Parse a namesortd bam to pore-C alignment format")
@click.argument("align_table", type=click.Path(exists=True))
@click.argument("virtual_digest_catalog", type=click.Path(exists=True))
@click.argument("porec_table")
@click.option("-n", "--n_workers", help="The number of dask_workers to use", default=1)
@click.option(
    "--mapping_quality_cutoff", type=int, default=1, help="Minimum mapping quality for an alignment to be considered"
)
@click.option(
    "--min_overlap_length",
    type=int,
    default=10,
    help="Minimum overlap in base pairs between an alignment and restriction fragment",
)
@click.option(
    "--containment_cutoff",
    type=float,
    default=99.0,
    help=(
        "Minimum percentage of a fragment included in an overlap for that "
        "fragment to be considered 'contained' within an alignment"
    ),
)
def assign_fragments(
    align_table,
    virtual_digest_catalog,
    porec_table,
    n_workers,
    mapping_quality_cutoff,
    min_overlap_length,
    containment_cutoff,
):
    """Filter the read-sorted alignments in INPUT_BAM and save the results under OUTPUT_PREFIX

    """
    from pore_c.analyses.alignments import assign_fragments
    from pore_c.model import PoreCRecord
    from pore_c.utils import DaskExecEnv
    import dask.dataframe as dd

    align_table = dd.read_parquet(align_table, engine="pyarrow")

    chrom_dtype = align_table.chrom.head(1).dtype

    vd_cat = open_catalog(str(virtual_digest_catalog))
    fragment_df = vd_cat.fragments.read().astype({"chrom": chrom_dtype}).sort_values(["fragment_id"])

    with DaskExecEnv(n_workers=n_workers) as env:
        fragment_df = env.scatter(fragment_df)
        porec_df = align_table.repartition(npartitions=1).map_partitions(
            assign_fragments,
            fragment_df,
            mapping_quality_cutoff=mapping_quality_cutoff,
            min_overlap_length=min_overlap_length,
            containment_cutoff=containment_cutoff,
            meta=PoreCRecord.pandas_dtype(overrides={"chrom": chrom_dtype}),
        )

        print(porec_df.compute().dtypes)

    raise ValueError


#    final_stats = parse_alignment_bam(
#        source_aligns,
#        fragment_df,
#        alignment_table=file_paths["alignment"],
#        read_table=file_paths["read"],
#        overlap_table=file_paths["overlap"],
#        alignment_summary=file_paths["alignment_summary"],
#        read_summary=file_paths["read_summary"],
#        n_workers=n_workers,
#        chunksize=chunksize,
#        phased=phased,
#        mapping_quality_cutoff=mapping_quality_cutoff,
#        min_overlap_length=min_overlap_length,
#        containment_cutoff=containment_cutoff,
#    )
#    metadata = {"final_stats": final_stats}
#    file_paths["virtual_digest"] = Path(virtual_digest_catalog)
#    file_paths["input_bam"] = Path(input_bam)
#    adf_cat = catalogs.AlignmentDfCatalog.create(file_paths, metadata, {})
#    logger.info(str(adf_cat))


@alignments.command(short_help="Parses the alignment table and converts to pairwise contacts")
@click.argument("align_table", type=click.Path(exists=True))
@click.argument("output_table")
@click.option("-n", "--n_workers", help="The number of dask_workers to use", default=1)
def clean_haplotypes(align_table, output_table, n_workers):
    """Clean up haplotype assignments for each read

    """
    from dask import dataframe as ddf
    from pore_c.analyses.alignments import clean_haplotypes

    align_df = ddf.read_parquet(align_table, engine="pyarrow")

    res = clean_haplotypes(align_df, output_table, n_workers=n_workers)
    raise ValueError(res)


@alignments.command(short_help="Parses the alignment table and converts to pairwise contacts")
@click.argument("align_catalog", type=click.Path(exists=True))
@click.argument("output_prefix")
@click.option("-n", "--n_workers", help="The number of dask_workers to use", default=1)
def to_contacts(align_catalog, output_prefix, n_workers):
    """Covert the alignment table to virtual pairwise contacts

    """
    from pore_c.analyses.alignments import convert_align_df_to_contact_df

    file_paths = catalogs.ContactCatalog.generate_paths(output_prefix)

    adf_cat = open_catalog(str(align_catalog))
    align_df = adf_cat.alignment.to_dask()

    logger.info(f"Converting alignments in {align_catalog} to contact format")
    convert_align_df_to_contact_df(align_df, contacts=file_paths["contacts"], n_workers=n_workers)
    metadata = {}
    contact_catalog = catalogs.ContactCatalog.create(file_paths, metadata, {})
    logger.info(str(contact_catalog))


@cli.group(cls=NaturalOrderGroup, short_help="Work the the contacts table")
def contacts():
    pass


@contacts.command(short_help="Convert pairwise contacts to a COO text file")
@click.argument("contact_catalog", type=click.Path(exists=True))
@click.argument("virtual_digest_catalog", type=click.Path(exists=True))
@click.argument("output_prefix")
@click.option("--phased", is_flag=True, default=False, help="Create set of phased coo files.")
@click.option("-r", "--resolution", help="The bin width of the resulting matrix", default=1000)
@click.option("-n", "--n_workers", help="The number of dask_workers to use", default=1)
def to_coo(contact_catalog, virtual_digest_catalog, output_prefix, phased, resolution, n_workers):
    from pore_c.analyses.contacts import contact_df_to_coo

    vd_cat = catalogs.VirtualDigestCatalog(virtual_digest_catalog)
    rg_cat = vd_cat.refgenome_catalog
    chrom_lengths = rg_cat.metadata["chrom_lengths"]

    contact_catalog = open_catalog(str(contact_catalog))

    contact_table_path = contact_catalog.contacts._urlpath
    fragment_df = vd_cat.fragments.to_dask().compute()
    res = contact_df_to_coo(
        contact_table_path, chrom_lengths, fragment_df, resolution, phased=phased, n_workers=n_workers
    )
    raise ValueError(res)
    pass


@alignments.command(short_help="Parses the alignment table and converts to paired-end like reads bed files for Salsa")
@click.argument("align_catalog", type=click.Path(exists=True))
@click.argument("salsa_bed", type=click.Path(exists=False))
@click.option("-n", "--n_workers", help="The number of dask_workers to use", default=1)
def to_salsa_bed(align_catalog, salsa_bed, n_workers):
    """Covert the alignment table to Salsa bed format.

    """
    from pore_c.analyses.pairs import convert_align_df_to_salsa

    adf_cat = open_catalog(str(align_catalog))
    align_df = adf_cat.alignment.to_dask()

    logger.info(f"Converting alignments in {align_catalog} to salsa2 bed format {salsa_bed}")
    res = convert_align_df_to_salsa(align_df, Path(salsa_bed), n_workers=n_workers)

    logger.info(res)


@alignments.command(short_help="Parses the alignment table and converts to hic text format")
@click.argument("align_catalog", type=click.Path(exists=True))
@click.argument("hic_txt", type=click.Path(exists=False))
@click.option("-n", "--n_workers", help="The number of dask_workers to use", default=1)
def to_hic_txt(align_catalog, hic_txt, n_workers):
    """Covert the alignment table to hic text format.

    """
    from pore_c.analyses.pairs import convert_align_df_to_hic

    adf_cat = open_catalog(str(align_catalog))
    align_df = adf_cat.alignment.to_dask()

    vd_cat = adf_cat.virtual_digest
    # FIXFIX: some invalid fragment ids are appearing in the alignment table
    # we need to fix at source, but for now we need to filter these records
    # out of the hic.txt files
    max_fragment_id = vd_cat.fragments.to_dask()["fragment_id"].max().compute()

    logger.info(f"Converting alignments in {align_catalog} to hic text format {hic_txt}")
    res = convert_align_df_to_hic(align_df, Path(hic_txt), n_workers=n_workers, max_fragment_id=max_fragment_id)

    logger.info(res)


@cli.group(cls=NaturalOrderGroup, short_help="Create pairs files")
def pairs():
    pass


@pairs.command(help="Convert from an alignment table to pairs format")
@click.argument("align_catalog", type=click.Path(exists=True))
@click.argument("output_prefix")
@click.option("-n", "--n_workers", help="The number of dask_workers to use", default=1)
def from_alignment_table(align_catalog, output_prefix, n_workers):
    from pore_c.analyses.pairs import convert_align_df_to_pairs

    file_paths = catalogs.PairsFileCatalog.generate_paths(output_prefix)

    adf_cat = open_catalog(str(align_catalog))
    rg_cat = adf_cat.virtual_digest.refgenome_catalog
    chrom_lengths = rg_cat.metadata["chrom_lengths"]
    genome_id = rg_cat.metadata["genome_id"]
    align_df = adf_cat.alignment.to_dask()
    # TODO: return number of pairs written
    metadata = convert_align_df_to_pairs(align_df, chrom_lengths, genome_id, file_paths["pairs"], n_workers=n_workers)

    file_paths["aligmentdf_cat"] = Path(align_catalog)
    pair_cat = catalogs.PairsFileCatalog.create(file_paths, metadata, {})
    logger.info(str(pair_cat))


@pairs.command(help="Convert from an alignment table to pairs format")
@click.argument("pairs_catalog", type=click.Path(exists=True))
@click.argument("output_prefix")
@click.option("-r", "--resolution", help="The bin width of the resulting matrix", default=1000)
@click.option("-n", "--n_workers", help="The number of dask_workers to use", default=1)
def to_matrix(pairs_catalog, output_prefix, resolution, n_workers):
    from pore_c.analyses.pairs import convert_pairs_to_matrix

    file_paths = catalogs.MatrixCatalog.generate_paths(output_prefix)
    pairs_cat = open_catalog(str(pairs_catalog))

    ds = pairs_cat.pairs
    metadata = convert_pairs_to_matrix(ds, resolution=resolution, n_workers=n_workers, coo=file_paths["coo"])
    metadata["resolution"] = resolution

    matrix_cat = catalogs.MatrixCatalog.create(file_paths, metadata, {})
    logger.info(str(matrix_cat))


@cli.group(cls=NaturalOrderGroup, short_help="Operations on matrices")
def matrix():
    pass


@matrix.command(help="Calculate correlations coefficient between a pair of matrices")
@click.argument("x_mcool", type=click.Path(exists=True))
@click.argument("y_mcool", type=click.Path(exists=True))
@click.argument("output_prefix")
@click.option("-r", "--resolution", help="The resolution to do the correlation at.", default=1_000_000)
def correlate(x_mcool, y_mcool, output_prefix, resolution):
    from pore_c.analyses.matrix import correlate
    from cooler import Cooler

    file_paths = catalogs.MatrixCorrelationCatalog.generate_paths(output_prefix)

    x_cool = Cooler(str(x_mcool) + f"::/resolutions/{resolution}")
    y_cool = Cooler(str(y_mcool) + f"::/resolutions/{resolution}")

    x_chrom_names = set(x_cool.chromnames)
    y_chrom_names = set(y_cool.chromnames)

    if x_chrom_names != y_chrom_names:
        x_not_y = x_chrom_names - y_chrom_names
        y_not_x = y_chrom_names - x_chrom_names
        if x_not_y and y_not_x:
            raise ValueError(f"Chromosomes are not sub/supersets x:{x_not_y}, y:{y_not_x}")
        elif x_not_y:
            logger.warning(f"Extra chromosomes in x, will not be included in calculations: {x_not_y}")
        else:
            logger.warning(f"Extra chromosomes in y, will not be included in calculations: {y_not_x}")

    metadata = correlate(
        x_cool, y_cool, xy_path=file_paths["xy"], coefficients_path=file_paths["coefficients"], resolution=resolution
    )
    metadata["resolution"] = resolution
    metadata["x"]["path"] = str(x_mcool)
    metadata["y"]["path"] = str(y_mcool)

    matrix_cat = catalogs.MatrixCorrelationCatalog.create(file_paths, metadata, {})
    logger.info(str(matrix_cat))


@cli.group(cls=NaturalOrderGroup, short_help="Dashboard")
def dashboard():
    pass


@dashboard.command(help="Alignment dashboard", context_settings=dict(ignore_unknown_options=True))
@click.argument("align_catalog", nargs=1, type=click.Path(exists=True))
@click.argument("bokeh_serve_args", nargs=-1, type=click.UNPROCESSED)
@click.pass_context
def alignment(ctx, align_catalog, bokeh_serve_args):
    import sys
    import pore_c

    # from pore_c.dashboard import main
    from bokeh.__main__ import main as bokeh_entry_point

    main_path = pore_c.__file__.rsplit("/", 1)[0] + "/dashboard/"
    sys.argv = ["bokeh", "serve"] + [main_path] + list(bokeh_serve_args) + ["--args", align_catalog]
    bokeh_entry_point()
