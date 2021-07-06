import electiondata as e

# Instructions:
#   Change the constants to values from your file
#   Delete any tests for contest types your state doesn't have in 2020 (e.g., Florida has no US Senate contest)
#   (Optional) Change district numbers
#   Replace each '-1' with the correct number calculated from the results file.
#   Move this testing file to the correct jurisdiction folder in `elections/tests`

# constants - CHANGE THESE!! - use internal db names
election = "2020 General"
jurisdiction = "Montana"
jurisdiction_type = "state"
abbr = "MT"
county_type = (
    "county"  # unless major subdivision is something else, e.g. 'parish' for Louisiana
)
total_pres_votes = 603640  # total of all votes for President
cd = 3  # congressional district
total_cd_votes = 601509  # total votes in the chosen cd
shd = 1  # state house district
total_shd_votes = 6734
ssd = 9  # state senate district
total_ssd_votes = 12826
# pick any one from your file. only 'total' available for MT
single_vote_type = "total"
pres_votes_vote_type = 603640
single_county = "Montana;Deer Lodge County"  # pick any one from your file
pres_votes_county = 4891  # total votes for pres of that county


def test_data_exists(dbname):
    assert e.data_exists(election, jurisdiction, dbname=dbname)


def test_presidential(dbname):
    assert (
        e.contest_total(
            election,
            jurisdiction,
            f"US President ({abbr})",
            dbname=dbname,
            sub_unit_type=jurisdiction_type,
        )
        == total_pres_votes
    )


def test_statewide_totals(dbname):
    assert (
        e.contest_total(
            election,
            jurisdiction,
            f"US Senate {abbr}",
            dbname=dbname,
            sub_unit_type=jurisdiction_type,
        )
        == 605637
    )


def test_congressional_totals(dbname):
    assert (
        e.contest_total(
            election,
            jurisdiction,
            f"US House {abbr} District 1",
            dbname=dbname,
            sub_unit_type=jurisdiction_type,
        )
        == total_cd_votes
    )


def test_state_senate_totals(dbname):
    assert (
        e.contest_total(
            election,
            jurisdiction,
            f"{abbr} Senate District 2",
            dbname=dbname,
            sub_unit_type=jurisdiction_type,
        )
        == total_ssd_votes
    )


def test_state_house_totals(dbname):
    assert (
        e.contest_total(
            election,
            jurisdiction,
            f"{abbr} House District 13",
            dbname=dbname,
            sub_unit_type=jurisdiction_type,
        )
        == total_shd_votes
    )


def test_standard_vote_types(dbname):
    assert e.check_count_types_standard(election, jurisdiction, dbname=dbname)


def test_vote_type_counts_consistent(dbname):
    assert e.check_totals_match_vote_types(election, jurisdiction, dbname=dbname)


def test_count_type_subtotal(dbname):
    assert (
        e.count_type_total(
            election,
            jurisdiction,
            f"US President ({abbr})",
            single_vote_type,
            sub_unit_type=jurisdiction_type,
            dbname=dbname,
        )
        == pres_votes_vote_type
    )


def test_one_county_vote_type(dbname):
    assert (
        e.contest_total(
            election,
            jurisdiction,
            f"US President ({abbr})",
            dbname=dbname,
            county=single_county,
            vote_type=single_vote_type,
        )
        == pres_votes_county
    )


def test_all_candidates_known(dbname):
    assert (
        e.get_contest_with_unknown_candidates(election, jurisdiction, dbname=dbname)
        == []
    )
