import results
from electiondata import Analyzer, DataLoader
from electiondata import data_exists
from electiondata import external_data_exists
from typing import Dict, Any, List, Optional
import os
import datetime
from pathlib import Path
import pytest


# some lists of dictionaries need to be sorted by a particular key
def dict_sort(
    list_of_dicts: List[Dict[str, Any]],
    sort_key: Optional[str] == None,
    drop_key: bool = True,
) -> List[Dict[str, Any]]:
    """If <key> is given, sort items by value of that key in each dictionary.
    If <key> is not given, return <list_of_dicts>"""

    if list_of_dicts and sort_key:
        new = sorted(list_of_dicts, key=lambda k: k[sort_key])
        if drop_key:
            for d in new:
                d.pop(sort_key)
    else:
        new = list_of_dicts

    return new


@pytest.fixture
def name_test_db():
    ts = datetime.datetime.now().strftime("%m%d_%H%M")
    pytest.test_db = f"pytest_{ts}"


# Required to initialize the pytest.* variables
def test_config(name_test_db):
    return pytest.test_db


# load test data to the test db
def test_load_test_data(param_file):
    dl = DataLoader(param_file=param_file)  # test db will be created later
    tests_path = os.path.join(Path(dl.d["repository_content_root"]).parent, "tests")
    db_dump = os.path.join(
        tests_path, "000_data_for_pytest", "postgres_test_db_dump.tar"
    )
    err_str = dl.load_data_from_db_dump(dbname=pytest.test_db, dump_file=db_dump)


def test_election_data_exists(param_file):
    ej_pairs = [
        ("2016 General", "Georgia"),
        ("2018 General", "Georgia"),
        ("2020 Primary", "Georgia"),
        ("2020 General", "Georgia"),
        ("2018 General", "North Carolina"),
        # ("2020 Primary", "Alaska"),
    ]
    has_data = [
        (e, j)
        for (e, j) in ej_pairs
        if data_exists(e, j, p_path=param_file, dbname=pytest.test_db)
    ]
    assert set(has_data) == set(ej_pairs)


"""def test_census_data_exists(param_file):
    assert external_data_exists("2018 General", "Georgia", p_path=param_file, dbname=pytest.test_db)
"""


def test_contest_updatelabels_display(param_file):
    analyzer = Analyzer(param_file=param_file, dbname=pytest.test_db)
    new = dict_sort(
        analyzer.display_options(
            "contest",
            verbose=True,
            filters=["2018 General", "Georgia", "State Senate"],
        ),
        sort_key="order_by",
    )
    correct = dict_sort(
        results.ga_2018_congressional_contests_state_senate, sort_key="order_by"
    )
    assert new == correct


# should be non-null on DB with any data
def test_election_display(param_file):
    analyzer = Analyzer(param_file=param_file, dbname=pytest.test_db)
    assert analyzer.display_options("election", verbose=True)


# should be non-null on DB with any data
def test_jurisdiction_display(param_file):
    analyzer = Analyzer(param_file=param_file, dbname=pytest.test_db)
    assert analyzer.display_options("jurisdiction", verbose=True)


# should be non-null on DB with data from 2018 General
def test_jurisdiction_display_filtered(param_file):
    analyzer = Analyzer(param_file=param_file, dbname=pytest.test_db)
    assert analyzer.display_options(
        "jurisdiction", verbose=True, filters=["2018 General"]
    )


# ### Test bar chart flow ###
def test_contest_type_display(param_file):
    analyzer = Analyzer(param_file=param_file, dbname=pytest.test_db)
    new = dict_sort(
        analyzer.display_options(
            "contest_type", verbose=True, filters=["2018 General", "Georgia"]
        ),
        sort_key="order_by",
    )
    expected = dict_sort(results.ga_2018_contest_types, sort_key="order_by")
    assert new == expected


def test_contest_display(param_file):
    analyzer = Analyzer(param_file=param_file, dbname=pytest.test_db)
    contests = analyzer.display_options(
        "contest",
        verbose=True,
        filters=["2018 General", "Georgia", "Congressional"],
    )
    new = dict_sort(contests, sort_key="order_by")
    expected = dict_sort(results.ga_2018_congressional_contests, sort_key="order_by")
    assert new == expected


def test_bar_congressional(param_file):
    analyzer = Analyzer(param_file=param_file, dbname=pytest.test_db)
    assert (
        analyzer.bar(
            "2018 General", "Georgia", "Congressional", "US House GA District 3"
        )
        == results.ga_2018_bar_congressional
    )


"""def test_alaska_non_county_hierarchy(param_file):
    analyzer = Analyzer(param_file=param_file, dbname=pytest.test_db)
    assert (
        analyzer.scatter(
            "Alaska",
            "2020 General",
            "Candidate total",
            "Joseph R. Biden",
            "2020 General",
            "Candidate total",
            "Donald J. Trump",
        )
        == results.ak20g_pres_scatter
    )
"""


def test_bar_all_state(param_file):
    analyzer = Analyzer(param_file=param_file, dbname=pytest.test_db)
    assert (
        analyzer.bar("2018 General", "North Carolina", "State House", "All State House")
        == results.nc_2018_bar_statehouse
    )


def test_bar_all_congressional(param_file):
    analyzer = Analyzer(param_file=param_file, dbname=pytest.test_db)
    assert (
        analyzer.bar(
            "2018 General", "North Carolina", "Congressional", "All Congressional"
        )
        == results.nc_2018_bar_congressional
    )


### check scatter flow ###
# should be non-null if there is any georgia data in the DB
def test_election_display(param_file):
    analyzer = Analyzer(param_file=param_file, dbname=pytest.test_db)
    assert analyzer.display_options(
        "election", verbose=True, filters=["Georgia", "county"]
    )


def test_category_display(param_file):
    analyzer = Analyzer(param_file=param_file, dbname=pytest.test_db)
    new = dict_sort(
        analyzer.display_options(
            "category",
            verbose=True,
            filters=["North Carolina", "county", "2018 General"],
        ),
        sort_key="order_by",
    )
    expected = dict_sort(results.nc_2018_category, sort_key="order_by")
    assert new == expected


def test_count_display(param_file):
    analyzer = Analyzer(param_file=param_file, dbname=pytest.test_db)
    new = dict_sort(
        analyzer.display_options(
            "count",
            verbose=True,
            filters=["Georgia", "county", "2018 General", "Candidate total"],
        ),
        sort_key="order_by",
    )
    expected = dict_sort(results.ga_2018_count, sort_key="order_by")
    assert new == expected


def test_scatter_candidates(param_file):
    analyzer = Analyzer(param_file=param_file, dbname=pytest.test_db)
    assert (
        analyzer.scatter(
            "Georgia",
            "2018 General",
            "Candidate total",
            "Chris Carr",
            "2018 General",
            "Candidate total",
            "Charlie Bailey",
        )
        == results.ga_2018_scatter_candidates
    )


def test_scatter_candidates_longname(param_file):
    analyzer = Analyzer(param_file=param_file, dbname=pytest.test_db)
    assert (
        analyzer.scatter(
            "Georgia",
            "2018 General",
            "Candidate total",
            "Chris Carr - R - GAAttGen",
            "2018 General",
            "Candidate total",
            "Charlie Bailey - D - GAAttGen",
        )
        == results.ga_2018_scatter_candidates
    )


def test_scatter_candidates_votetype(param_file):
    analyzer = Analyzer(param_file=param_file, dbname=pytest.test_db)
    assert (
        analyzer.scatter(
            "Georgia",
            "2018 General",
            "Candidate absentee-mail",
            "Stacey Abrams",
            "2018 General",
            "Candidate election-day",
            "Stacey Abrams",
        )
        == results.ga_2018_scatter_candidates_votetype
    )


def test_scatter_multi_election(param_file):
    analyzer = Analyzer(param_file=param_file, dbname=pytest.test_db)
    assert (
        analyzer.scatter(
            "Georgia",
            "2018 General",
            "Contest total",
            "US House GA District 14",
            "2016 General",
            "Contest total",
            "US House GA District 14",
        )
        == results.ga_multi_election
    )


def test_scatter_party(param_file):
    analyzer = Analyzer(param_file=param_file, dbname=pytest.test_db)
    assert (
        analyzer.scatter(
            "Georgia",
            "2018 General",
            "Party total",
            "Republican State House",
            "2018 General",
            "Party total",
            "Democratic State House",
        )
        == results.ga_2018_scatter_party
    )


def test_scatter_party_votetype(param_file):
    analyzer = Analyzer(param_file=param_file, dbname=pytest.test_db)
    assert (
        analyzer.scatter(
            "Georgia",
            "2018 General",
            "Party absentee-mail",
            "Republican State House",
            "2018 General",
            "Candidate absentee-mail",
            "Stacey Abrams",
        )
        == results.ga_2018_scatter_party_votetype
    )


# check that rollup_dataframe to county level works correctly
def test_scatter_county_rollup(param_file):
    analyzer = Analyzer(param_file=param_file, dbname=pytest.test_db)
    assert (
        analyzer.scatter(
            "North Carolina",
            "2018 General",
            "Candidate total",
            "Mark Harris - R - USHouse9",
            "2018 General",
            "Candidate total",
            "Dan McCready - D - USHouse9",
        )
        == results.nc_2018_scatter_county_rollup
    )


# check that search works correctly
def test_candidate_search_display(param_file):
    analyzer = Analyzer(param_file=param_file, dbname=pytest.test_db)
    new = dict_sort(
        analyzer.display_options(
            "bishop",
            verbose=True,
            filters=["Georgia", "county", "2018 General", "Congressional"],
        ),
        sort_key="order_by",
    )
    expected = dict_sort(results.ga_2018_candidate_search_display, sort_key="order_by")
    assert new == expected


def test_count_contest_display(param_file):
    analyzer = Analyzer(param_file=param_file, dbname=pytest.test_db)
    new = dict_sort(
        analyzer.display_options(
            "count",
            verbose=True,
            filters=["Georgia", "county", "2018 General", "Contest total"],
        ),
        sort_key="order_by",
    )
    expected = dict_sort(results.ga_2018_count_contest, sort_key="order_by")
    assert new == expected


"""def test_census_count_display(param_file):
    analyzer = Analyzer(param_file=param_file, dbname=pytest.test_db)
    new = dict_sort(
        analyzer.display_options(
            "count",verbose=True,filters=["Georgia","2018 General","Census data"]
        ),
        sort_key="order_by"
    )
    expected = dict_sort(results.ga_2018_census_display_count,sort_key="order_by")
    assert new == expected



def test_census_category_display(param_file):
    analyzer = Analyzer(param_file=param_file, dbname=pytest.test_db)
    new = dict_sort(
        analyzer.display_options(
            "category",verbose=True,filters=["Georgia","county","2018 General"]
        ),
        sort_key="order_by"
    )
    expected = dict_sort(results.ga_2018_census_display_category,sort_key="order_by")
    assert new == expected



def test_census_scatter(param_file):
    analyzer = Analyzer(param_file=param_file, dbname=pytest.test_db)
    assert (
        analyzer.scatter(
            "Georgia",
            "2018 General",
            "Candidate absentee-mail",
            "Stacey Abrams",
            "2018 General",
            "Census data",
            "White",
        )
        == results.ga_2018_census_scatter
    )
"""
# delete test database
def delete_test_db(param_file):
    dl = DataLoader(param_file=param_file, dbname=pytest.test_db)
    dl.close_and_erase()
