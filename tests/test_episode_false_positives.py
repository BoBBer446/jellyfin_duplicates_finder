"""Reproduce misleading episode assignments from the reported series scan.

The shared Jellyfin IDs/numbers are synthetic: the report contained rendered paths,
not raw Jellyfin records. Identical provider IDs deliberately must not defeat checks.
"""

import pytest

from app.duplicate_finder import find_duplicate_groups


def episode(item_id, path, **changes):
    raw = {
        "Id": item_id,
        "Type": "Episode",
        "Name": "Imported episode",
        "SeriesId": "series",
        "ParentIndexNumber": 1,
        "IndexNumber": 1,
        "Path": path,
        "ProviderIds": {"Tvdb": "same-incorrect-id"},
        "RunTimeTicks": 20 * 60 * 10_000_000,
    }
    raw.update(changes)
    return raw


@pytest.mark.parametrize("first,second", [(1, 2), (1, 7), (8, 5), (5, 4), (6, 3)])
def test_halo_ova_numbers_cannot_be_merged_by_shared_metadata(first, second):
    raw = [
        episode("a", f"/Halo/Halo.Legends.OVA{first}.720p.mkv"),
        episode("b", f"/Halo/Halo.Legends.OVA{second}.720p.mkv"),
    ]
    assert not find_duplicate_groups(raw)[0]


@pytest.mark.parametrize("number", [53, 54, 55, 56])
def test_yakari_absolute_number_conflict_overrides_same_sxe_and_provider(number):
    raw = [
        episode(
            "a",
            f"/Yakari/Yakari_-_S01E{number}_-_Yakari_Folge_{number}_Titel.mp4",
            IndexNumber=number,
        ),
        episode(
            "b",
            f"/Yakari/Yakari_-_S01E{number}_-_Yakari_Folge_{number + 100}_Titel.mp4",
            IndexNumber=number,
        ),
    ]
    assert not find_duplicate_groups(raw)[0]


def test_episode_zero_is_not_an_identity_even_with_identical_titles_and_ids():
    raw = [
        episode(str(i), f"/Ringe/Season_1/Ringe.S01E00.{place}.mkv", IndexNumber=0)
        for i, place in enumerate(["Numenor", "Rhovanion", "Suedlande", "Lindon", "Khazad.dum"])
    ]
    groups, summary = find_duplicate_groups(raw)
    assert not groups
    assert summary.skipped_items == 5


def test_plex_optimized_episode_is_not_a_deletion_candidate():
    raw = [
        episode("a", "/Die_Tudors/Season_1/Die_Tudors.S01E01.mkv", Name="In Cold Blood"),
        episode(
            "b",
            "/Die_Tudors/S01/Plex Versions/Optimized for TV/Die Tudors/S01E01.mp4",
            Name="In Cold Blood",
        ),
    ]
    groups, summary = find_duplicate_groups(raw)
    assert not groups
    assert summary.skipped_items == 1


def test_renamed_episode_titles_are_conservatively_kept_separate():
    raw = [
        episode("a", "/a/Show.S01E01.mkv", Name="The first story"),
        episode("b", "/b/Show.S01E01.mkv", Name="Another story"),
    ]
    assert not find_duplicate_groups(raw)[0]


@pytest.mark.parametrize(
    "path", ["Show.S01E02.mkv", "Show.S02E01.mkv", "Show.S01E01E02.mkv", "Show.1x02.mkv"]
)
def test_filename_must_agree_with_jellyfin_season_and_episode(path):
    raw = [episode("a", "/a/Show.S01E01.mkv"), episode("b", "/b/" + path)]
    assert not find_duplicate_groups(raw)[0]


def test_metadata_and_display_name_are_not_independent_filename_evidence():
    raw = [
        episode("a", "/a/a.mkv", Name="Show.S01E01"),
        episode("b", "/b/b.mkv", Name="Show.S01E01"),
    ]
    assert not find_duplicate_groups(raw)[0]


@pytest.mark.parametrize(
    "first,second,changes",
    [
        ("Show.S01E01.720p.mkv", "Show.S01E01.1080p.mkv", {}),
        ("Show.1x01.mkv", "Show.S01E01.mkv", {}),
        ("Show.S00E01.mkv", "Show.S00E01.mp4", {"ParentIndexNumber": 0}),
        ("Show.S01E01E02.mkv", "Show.S01E01-E02.mp4", {"IndexNumberEnd": 2}),
        ("Show.OVA1.mkv", "Show.OVA01.mp4", {}),
    ],
)
def test_supported_duplicate_episodes_still_match_without_high_confidence(first, second, changes):
    raw = [episode("a", "/a/" + first, **changes), episode("b", "/b/" + second, **changes)]
    groups, _ = find_duplicate_groups(raw)
    assert len(groups) == 1
    assert groups[0].confidence == "medium"
    assert "Dateinummerierung" in groups[0].match_reason


def test_conflicting_filename_and_display_name_absolute_markers_are_excluded():
    raw = [
        episode("a", "/a/Show.OVA1.mkv", Name="Show OVA2"),
        episode("b", "/b/Show.OVA1.mkv", Name="Show OVA2"),
    ]
    assert not find_duplicate_groups(raw)[0]


def test_windows_optimized_path_is_excluded():
    raw = [
        episode("a", "C:/Show/Show.S01E01.mkv"),
        episode("b", "D:/Show/Plex_Versions/Show.S01E01.mp4".replace("/", chr(92))),
    ]
    assert not find_duplicate_groups(raw)[0]
