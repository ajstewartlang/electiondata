import election_data_analysis as e

def test_data_exists(dbname):
    assert e.data_exists("2018 General","Wisconsin",dbname=dbname)


def test_wi_statewide_totals(dbname):
    assert (not e.data_exists("2018 General","Wisconsin",dbname=dbname) or e.contest_total(
            "2018 General",
            "Wisconsin",
            "WI Governor",
            dbname=dbname,
        )
            == 2673305
    )
    # The total votes for the above was 2673305, but two write-in candidates appeared
    # with the same name "No candidate" after munging, the second of which received 3
    # votes that were lost.


def test_wi_senate_totals(dbname):
    assert (not e.data_exists("2018 General","Wisconsin",dbname=dbname) or e.contest_total(
            "2018 General",
            "Wisconsin",
            "WI Senate District 21",
            dbname=dbname,
        )
            == 83783
    )


def test_wi_house_totals(dbname):
    assert (not e.data_exists("2018 General","Wisconsin",dbname=dbname) or e.contest_total(
            "2018 General",
            "Wisconsin",
            "WI House District 10",
            dbname=dbname,
        )
            == 21149
    )


def test_us_house_totals(dbname):
    assert (not e.data_exists("2018 General","Wisconsin",dbname=dbname) or e.contest_total(
            "2018 General",
            "Wisconsin",
            "US House WI District 3",
            dbname=dbname,
        )
            == 314989
    )

# results not available by vote type
