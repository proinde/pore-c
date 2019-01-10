import pytest
import re
#from pore_c.tools.map_to_frags import load_reference, assign_to_fragment, porec_iterator, map_to_fragments
from pore_c.tools.map_to_frags import FragmentMap, AlignedSegmentToFragment, AlignedSegmentMappingType


def test_endpoints_to_intervals():
    intervals = FragmentMap.endpoints_to_intervals("chr1", [10, 20, 30], 0)
    assert(intervals == [('chr1', 0, 10, '0'), ('chr1', 10, 20, '1'), ('chr1', 20, 30, '2')])
    intervals = FragmentMap.endpoints_to_intervals("chr1", [10, 20, 30], 100)
    assert(intervals == [('chr1', 0, 10, '100'), ('chr1', 10, 20, '101'), ('chr1', 20, 30, '102')])


def frag_map():
    data = {
        "chr1": [10, 20, 30, 100],
        "chr2": [5,  15, 25, 90],
    }
    fm = FragmentMap.from_dict(data)
    return fm

@pytest.fixture
def fm():
    return frag_map()

@pytest.mark.parametrize('query,expected', [
    (("chr1", 15, 25, "my_id"), (2, [5, 5,], None)), #overlap 2 frags
    (("chr1", 100, 110, "my_id"), (0, None, None)), #no overlap off end
    (("chr1", 5, 5, "my_id") , (0, None, None)), #no overlap zero-length interval
    (("chr1", 9, 10, "my_id"), (1, [1], [0])), #zero-based, overlaps left interval
])
def test_overlaps(query, expected):
    fm = frag_map()
    num_overlaps, overlap_lengths, overlap_ids = expected

    overlaps = list(fm.iter_overlaps(query))
    assert(len(overlaps) == num_overlaps)
    for x in range(num_overlaps):
        if overlap_lengths:
            assert(overlap_lengths[x] == overlaps[x].overlap)
        if overlap_ids:
            assert(overlap_ids[x] == overlaps[x].frag_id)


@pytest.mark.parametrize('start,end,frag_id,mapping_type', [
    (5, 10, 0, AlignedSegmentMappingType.simple),
    (5, 12, 0, AlignedSegmentMappingType.multi_frag), #smaller overlap on second fragment
    (5, 20, 1, AlignedSegmentMappingType.multi_frag), #larger overlap on second fragment
])
def test_frag_assingment(start, end, frag_id, mapping_type):
    fm = frag_map()
    segment = AlignedSegment("chr1", start, end, True, "read1", 300, 500, 0.1)
    segment.assign_to_fragment(fm)
    assert(segment.frag_id == frag_id)
    assert(segment.mapping_type == mapping_type)




def test_frag_file(fm, tmpdir):
    bed_file = str(tmpdir / "frag_map.bed.gz")
    fm.save_to_bed(str(bed_file))

    fm1 = FragmentMap.from_bed_file(bed_file)
    for i1, i2 in zip(fm.bt, fm1.bt):
        assert(i1==i2)


#def test_load_reference(hicREF_file):
#    ref_sizes, ref_IDs = load_reference(hicREF_file)
#
#    #the sizes dictionary and the IDs dictionary have the same number of keys and values
#    assert ref_sizes.keys() == ref_IDs.keys()
#    assert len(ref_sizes.values()) == len(ref_IDs.values())
#    IDs_collected = []
#
#    #all fragment IDs are unique
#    for ch, IDs in ref_IDs.items():
#        IDs_collected.extend(IDs)
#
#    assert len(set(IDs_collected)) == len(IDs_collected)
#
#    #that the position lists are loaded in sorted order
#    for positions in ref_sizes.values():
#        assert sorted(positions) == positions
#
##signature: assign_to_fragment(ref_frags: tuple, ref_IDs: dict, loc: tuple, method: str) -> NamedTuple:
##This is the function that actually does the assignment. map_to_fragments is a wrapper for it
##  that manages bam reading and fileIO, whose internal code is here for management purposes
##TODO [ ]: future testing should include different methods
#def test_assign_to_fragment(hicREF_file, namesorted_align_filename):
#    ref_sizes, ref_IDs = load_reference(hicREF_file)
#
#    results = []
#    for readID, aligns in porec_iterator(namesorted_align_filename):
#        walk = Cwalk(readID)
#        for monomer in aligns:
#            loc = (monomer.reference_name, monomer.reference_start,monomer.reference_end)
#            frag,pos = assign_to_fragment(ref_sizes, ref_IDs, loc, 'start')
#            new_contact = Contact(monomer.reference_name, frag, monomer.is_reverse, pos, monomer.mapping_quality)
#            walk.add(new_contact)
#        results.append(len(str(walk).split()))
#
#    assert results == [11, 26, 21, 21, 11, 6]
#
#def test_porec_iterator(namesorted_align_filename):
#    res = dict([aligns for aligns in porec_iterator(namesorted_align_filename)])
#    assert sorted(res.keys()) == ['0a0030d2-60a6-4498-8ea0-329d9dcac82b', '0a4cf95d-1410-42b1-867c-68e987123675', '0a6b6929-f064-42d4-afd4-24b38a966d03', '0aa14eb3-bdd8-40eb-97c3-d37c6eb99ef6', '0af7db4f-2804-4dc8-aae9-fc4611008d4a', '0b72d767-a437-43e2-a9ea-717d99864688']
#    assert([len(align) for align in res.values()] == [2, 5, 6, 5, 2, 1])
#
#    #check that all the alignments in each read bundle have the same query_name
#    # and that the order in query is preserved (i.e. that they're sorted by query_start)
#    for readID, aligns in res.items():
#        q_name = aligns[0].query_name
#        #bundle names are all identical
#        assert( all([x.query_name == q_name for x in aligns]))
#
#    for aligns in res.values():
#        #sorted order
#        assert( sorted(aligns,key=lambda x: x.query_alignment_start) == aligns)
#
