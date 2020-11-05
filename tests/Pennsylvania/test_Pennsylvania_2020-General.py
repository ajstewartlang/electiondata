import election_data_analysis as e

# Instructions:
#   Add in the election, jurisdiction, abbreviation and count_item_type
#   Delete any tests for contest types your state doesn't have in 2020 (e.g., Florida has no US Senate contest)
#   (Optional) Change district numbers
#   Replace each '-1' with the correct number calculated from the results file.
#   Move this testing file to the correct jurisdiction folder in `election_data_analysis/tests`

election = "2020 General"
jurisdiction = 'Pennsylvania'
abbr = 'PA'
count_item_type = 'absentee'

def data_exists(dbname):
    assert e.data_exists(
election,f"{jurisdiction}",dbname=dbname)

def test_presidential(dbname):
    assert(e.contest_total(

election,
        f"{jurisdiction}",
        f"US President ({abbr})",
        dbname=dbname,
        )
        == 6422156
    )

def test_statewide_totals(dbname):
    assert (e.contest_total(

election,
        f"{jurisdiction}",
        f"{abbr} Auditor General",
        dbname=dbname,
        )
        == 6274473
    )

def test_congressional_totals(dbname):
    assert (e.contest_total(

election,
        f"{jurisdiction}",
        f"US House {abbr} District 16",
        dbname=dbname,
        )
        == 315704
    )

def test_state_senate_totals(dbname):
    assert (e.contest_total(

election,
        f"{jurisdiction}",
        f"{abbr} Senate District 35",
        dbname=dbname,
        )
        == 122414
    )

def test_state_house_totals(dbname):
    assert (e.contest_total(

election,
        f"{jurisdiction}",
        f"{abbr} House District 116",
        dbname=dbname,
        )
        == 25615
    )

def test_standard_vote_types(dbname):
    assert e.check_count_types_standard(
election, jurisdiction, dbname=dbname)


def test_vote_type_counts_consistent(dbname):
    assert e.check_totals_match_vote_types(election, jurisdiction, dbname=None)

def test_count_type_subtotal(dbname):
    assert (e.count_type_total(
        election,
        jurisdiction,
        f"US President ({abbr})",
        count_item_type,
        dbname=dbname,
    ) == -1
    )