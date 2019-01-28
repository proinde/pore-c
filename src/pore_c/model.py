from typing import Pattern, List, NamedTuple, Iterator, Union, Dict, Tuple
from pybedtools import BedTool
from collections import defaultdict
from dataclasses import dataclass

class SeqDigest(NamedTuple):
    """Holds the results of a digestion"""
    seq_name: str
    positions: List[int]
    seq_length: int



@dataclass
class BedToolsOverlap(object):
    """Datastructure to hold the results of a bedtools intersect command"""
    query_chrom: str
    query_start: int
    query_end: int
    query_id: str
    frag_chrom: str
    frag_start: int
    frag_end: int
    frag_id: int
    overlap: int

    def __post_init__(self):
        self.query_start = int(self.query_start)
        self.query_end = int(self.query_end)
        self.frag_start = int(self.frag_start)
        self.frag_end = int(self.frag_end)
        self.frag_id = int(self.frag_id)
        self.overlap = int(self.overlap)



class FragmentMap(object):
    """Represents the fragments created by a restriction digestion"""
    def __init__(self, bedtool: BedTool, chrom_lengths: Dict[str, int] = None):
        self.bt = bedtool #bedtool.saveas().tabix(is_sorted=True)
        self.chrom_lengths = chrom_lengths

    @staticmethod
    def endpoints_to_intervals(chrom, positions, id_offset) -> List[Tuple[str, int, int, int]]:
        if not positions[0] == 0:
            positions = [0] + positions
        return [
            (chrom, start, end, str(x + id_offset))
            for x, (start, end) in enumerate(zip(positions[:-1], positions[1:]))
        ]

    def save_to_bed(self, path):
        if not path.endswith(".bed.gz"):
            raise ValueError("Must end with .bed.gz: {}".format(path))
        self.bt.saveas(path.rsplit(".gz")[0]).tabix(in_place=True, is_sorted=True, force=True)

    def save_to_HiCRef(self, path):
        chrom_to_endpoints = defaultdict(list)
        for interval in self.bt:
            chrom_to_endpoints[interval.chrom].append(interval.stop)
        with open(path, "w") as fh:
            for chrom, endpoints in chrom_to_endpoints.items():
                fh.write("{} {}\n".format(chrom, " ".join(map(str, endpoints))))

    @classmethod
    def from_dict(cls, d: Dict[str, List[int]]):
        """Create a fragment map from a dictionary mapping chromosomes to fragment endpoints (useful for testing)"""
        intervals = []
        chrom_lengths = {}
        id_offset = 0
        for chrom, endpoints in d.items():
            intervals.extend(cls.endpoints_to_intervals(chrom, endpoints, id_offset))
            chrom_lengths[chrom] = endpoints[-1]
            id_offset += len(endpoints)
        bt = BedTool(intervals)
        return cls(bt, chrom_lengths)

    @classmethod
    def from_bed_file(cls, path):
        if not path.endswith(".bed.gz"):
            raise ValueError("Must end with .bed.gz: {}".format(path))
        return cls(BedTool(path))

    @classmethod
    def from_HiCRef(cls, fname):
        intervals = []
        chrom_lengths = {}
        id_offset = 0
        with open(fname) as fh:
            for line in fh:
                fields = line.strip().split()
                chrom = fields[0]
                endpoints = list(map(int, fields[1:]))
                intervals.extend(cls.endpoints_to_intervals(chrom, endpoints, id_offset))
                chrom_lengths[chrom] = endpoints[-1]
                id_offset += len(endpoints)
        bt = BedTool(intervals)
        return cls(bt, chrom_lengths)

    @classmethod
    def from_digest_iter(cls, i: Iterator[SeqDigest]):
        intervals = []
        chrom_lengths = {}
        id_offset = 0
        for digest in i:
            chrom = digest.seq_name
            endpoints = digest.positions
            intervals.extend(cls.endpoints_to_intervals(chrom, endpoints, id_offset))
            chrom_lengths[chrom] = endpoints[-1]
            id_offset += len(endpoints)
        bt = BedTool(intervals)
        return cls(bt, chrom_lengths)




    def _query_to_bedtool(self, query):
        def _interval_from_tuple(t, id_offset=0):
            if len(t) == 3:
                return (t[0], t[1], t[2], str(id_offset))
            else:
                assert(len(t) == 4)
                return t
        if isinstance(query, tuple):
            intervals = [_interval_from_tuple(query)]
        else:
            raise NotImplementedError
        return BedTool(intervals)

    def iter_overlaps(self, query, min_overlap=0):
        query_bt = self._query_to_bedtool(query)
        for overlap in (BedToolsOverlap(*i.fields) for i in query_bt.intersect(self.bt, sorted=True, wo=True)):
            if overlap.overlap <= min_overlap:
                continue
            yield overlap
