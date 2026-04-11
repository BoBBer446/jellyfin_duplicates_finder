from app.duplicate_finder import find_duplicate_groups


def test_find_duplicate_groups_keeps_best_quality_item():
    items = [
        {
            "Id": "a",
            "Name": "Film X",
            "SortName": "Film X",
            "Path": "/media/Film X 720p.mkv",
            "ProductionYear": 2020,
            "MediaSources": [
                {
                    "Size": 1_000,
                    "MediaStreams": [{"Type": "Video", "Width": 1280, "Height": 720}],
                }
            ],
        },
        {
            "Id": "b",
            "Name": "Film X",
            "SortName": "Film X",
            "Path": "/media/Film X 1080p.mkv",
            "ProductionYear": 2020,
            "MediaSources": [
                {
                    "Size": 2_000,
                    "MediaStreams": [{"Type": "Video", "Width": 1920, "Height": 1080}],
                }
            ],
        },
    ]

    groups, summary = find_duplicate_groups(items)

    assert summary.total_items == 2
    assert summary.duplicate_groups == 1
    assert summary.duplicate_items_to_delete == 1
    assert groups[0].keep_item_id == "b"
    assert groups[0].delete_candidates == ["a"]


def test_find_duplicate_groups_respects_sequence_markers():
    items = [
        {
            "Id": "a",
            "Name": "Film Y",
            "SortName": "Film Y",
            "Path": "/media/FilmY.CD1.mkv",
            "ProductionYear": 2001,
            "MediaSources": [],
        },
        {
            "Id": "b",
            "Name": "Film Y",
            "SortName": "Film Y",
            "Path": "/media/FilmY.CD2.mkv",
            "ProductionYear": 2001,
            "MediaSources": [],
        },
    ]

    groups, summary = find_duplicate_groups(items)

    assert summary.duplicate_groups == 0
    assert groups == []


def test_find_duplicate_groups_matches_padded_and_hyphenated_sequences():
    items = [
        {
            "Id": "a",
            "Name": "Film Z",
            "SortName": "Film Z",
            "Path": "/media/Film-Z-CD-01.mkv",
            "ProductionYear": 2002,
            "MediaSources": [],
        },
        {
            "Id": "b",
            "Name": "Film Z",
            "SortName": "Film Z",
            "Path": "/media/Film-Z-CD-02.mkv",
            "ProductionYear": 2002,
            "MediaSources": [],
        },
    ]

    groups, summary = find_duplicate_groups(items)

    assert summary.duplicate_groups == 0
    assert groups == []
