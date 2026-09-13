from copy import deepcopy

import pytest

from app.duplicate_finder import find_duplicate_groups


def movie(item_id, **changes):
    item = {
        "Id": item_id,
        "Type": "Movie",
        "Name": "Ein Film",
        "ProductionYear": 2020,
        "Path": "/media/" + item_id + ".mkv",
        "ProviderIds": {"Tmdb": "123"},
        "MediaSources": [
            {
                "Size": 1000,
                "MediaStreams": [{"Type": "Video", "Width": 1920, "Height": 1080, "Codec": "h264"}],
            }
        ],
    }
    item.update(changes)
    return item


def test_provider_matches_translated_titles():
    groups, summary = find_duplicate_groups([movie("a"), movie("b", Name="Another title")])
    assert len(groups) == 1
    assert groups[0].confidence == "high"
    assert groups[0].reclaimable_bytes == summary.reclaimable_bytes == 1000


@pytest.mark.parametrize(
    "changes",
    [
        {"ProviderIds": {"Tmdb": "999"}},
        {"EditionName": "Extended"},
        {"Path": "/media/film.extended.mkv"},
        {"Path": "/media/film.CD2.mkv"},
        {"IsFolder": True},
        {"Type": "Series"},
        {"Path": ""},
        {"MediaSources": [{"Size": 1}, {"Size": 2}]},
    ],
)
def test_distinct_or_unsafe_entries_are_not_candidates(changes):
    assert not find_duplicate_groups([movie("a"), movie("b", **changes)])[0]


def test_runtime_difference_prevents_wrong_cut_match():
    a, b = (
        movie("a", RunTimeTicks=60 * 60 * 10_000_000),
        movie("b", RunTimeTicks=80 * 60 * 10_000_000),
    )
    assert not find_duplicate_groups([a, b])[0]


def test_duplicate_ids_and_shared_paths_are_not_deletable():
    a = movie("a")
    assert not find_duplicate_groups([a, deepcopy(a)])[0]
    assert not find_duplicate_groups([a, movie("b", Path=a["Path"])])[0]


def test_unicode_titles_do_not_collapse():
    assert not find_duplicate_groups(
        [movie("a", Name="猫", ProviderIds={}), movie("b", Name="犬", ProviderIds={})]
    )[0]
    assert (
        len(
            find_duplicate_groups(
                [
                    movie("a", Name="Amélie", ProviderIds={}),
                    movie("b", Name="Ame\u0301lie", ProviderIds={}),
                ]
            )[0]
        )
        == 1
    )


def test_unknown_year_and_generic_title_need_provider_ids():
    for changes in [{"ProductionYear": None}, {"Name": "movie"}]:
        assert not find_duplicate_groups(
            [
                movie("a", ProviderIds={}, **changes),
                movie("b", ProviderIds={}, **changes),
            ]
        )[0]


def test_unknown_provider_cannot_bridge_conflicting_groups():
    groups, _ = find_duplicate_groups(
        [
            movie("a"),
            movie("b", ProviderIds={"Tmdb": "999"}),
            movie("c", ProviderIds={}),
        ]
    )
    assert not groups


def test_episode_identity_includes_series_season_and_episode_range():
    base = {
        "Type": "Episode",
        "SeriesId": "series-1",
        "ParentIndexNumber": 1,
        "IndexNumber": 1,
        "ProviderIds": {},
    }
    a = movie("a", Path="/a/Series.S01E01.mkv", **base)
    assert len(find_duplicate_groups([a, movie("b", Path="/b/Series.S01E01.mkv", **base)])[0]) == 1
    for change in [
        {"IndexNumber": 2},
        {"ParentIndexNumber": 2},
        {"SeriesId": "series-2"},
        {"IndexNumberEnd": 2},
        {"IndexNumber": None},
    ]:
        assert not find_duplicate_groups(
            [a, movie("b", Path="/b/Series.S01E01.mkv", **(base | change))]
        )[0]


def test_custom_sequences_extend_defaults_and_windows_paths_work():
    a = movie("a", Path=r"C:\media\film.CD-01.mkv")
    b = movie("b", Path=r"D:\media\film.CD-02.mkv")
    assert not find_duplicate_groups([a, b], ["BONUS1"])[0]


def test_bad_optional_numeric_metadata_is_tolerated():
    a = movie(
        "a",
        MediaSources=[
            {
                "Size": "unknown",
                "MediaStreams": [{"Type": "Video", "Width": "bad", "Height": None}],
            }
        ],
    )
    groups, _ = find_duplicate_groups([a, movie("b")])
    assert groups[0].keep_item_id == "b"
    assert groups[0].items[-1].size == 0


def test_indirect_matches_require_one_shared_identifier_for_whole_group():
    items = [
        movie("a", Name="Alpha"),
        movie("b", Name="Beta"),
        movie("c", Name="Beta", ProviderIds={"Imdb": "tt999"}),
    ]
    groups, _ = find_duplicate_groups(items)
    assert len(groups) == 1
    assert {item.id for item in groups[0].items} == {"a", "b"}


def test_episodes_without_series_id_are_not_grouped_by_name():
    fields = {
        "Type": "Episode",
        "SeriesName": "The same name",
        "ParentIndexNumber": 1,
        "IndexNumber": 1,
    }
    assert not find_duplicate_groups([movie("a", **fields), movie("b", **fields)])[0]


@pytest.mark.parametrize("changes", [{"Type": []}, {"MediaSources": 42}, {"MediaSources": {}}])
def test_malformed_optional_metadata_is_skipped(changes):
    groups, summary = find_duplicate_groups([movie("a"), movie("b", **changes)])
    assert not groups
    assert summary.skipped_items == 1
