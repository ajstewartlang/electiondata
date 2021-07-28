import pytest


"""@pytest.fixture
def major_subdiv_type(dbname, param_file, jurisdiction, run_time_params):
    an = ed.Analyzer(dbname=dbname, param_file=param_file)
    major_subdiv_type = db.get_major_subdiv_type(
        an.session, jurisdiction, run_time_params["repository_content_root"]
    )
    return major_subdiv_type


@pytest.fixture
def testing_info(election, jurisdiction, run_time_params):
    data_file = os.path.join(
        run_time_params["repository_content_root"], "results_for_testing",election, f"{jurisdiction}.tsv"
    )
    df = pd.read_csv(data_file, sep="\t")
    # TODO check contest names, reporting unit and warn user if not found
    # run tests only on official-final lines
    # TODO handle Status = 'preliminary' with as-of date (by adding status parameter to test?)
    testing_info = [dic for dic in df.to_dict("records") if dic["Status"] == "official-final"]
    return testing_info
"""


def test_analyzer_exists(analyzer):
    assert analyzer is not None


def test_data_exists(analyzer, election, jurisdiction):
    assert analyzer.data_exists(election, jurisdiction)


def test_standard_vote_types(analyzer, election, jurisdiction):
    assert analyzer.check_count_types_standard(election,jurisdiction)


def test_vote_type_counts_consistent(analyzer, election, jurisdiction, major_subdiv_type):
    assert analyzer.check_totals_match_vote_types(election,jurisdiction, sub_unit_type=major_subdiv_type)


def test_all_candidates_known(analyzer, election, jurisdiction,  major_subdiv_type):
    contest_with_unknowns = analyzer.get_contest_with_unknown_candidates(
        election, jurisdiction)
    bad = "\n".join(contest_with_unknowns)
    if bad:
        print(f"\nContests with unknown candidates:\n{bad}\n")
    assert contest_with_unknowns == []

# per suggestion found on stackabuse
# https://stackoverflow.com/questions/55413277/can-pytest-hooks-use-fixtures
# to allow dynamic definition of fixture from data in file
REFERENCE_RESULT_LIST = []


@pytest.fixture(autouse=True)
def set_global_loaded_test_data(request):
    global REFERENCE_RESULT_LIST
    data_loader = request.getfixturevalue('load_data')
    orig,REFERENCE_RESULT_LIST = REFERENCE_RESULT_LIST, data_loader
    yield
    REFERENCE_RESULT_LIST = orig
# end code from stackabuase


def test_contest(analyzer,election,jurisdiction,major_subdiv_type):
    wrong_results = list()
    correct_results = list()
    for reference_result in REFERENCE_RESULT_LIST:
        count_from_db = analyzer.contest_total(
                    election,
                    jurisdiction,
                    reference_result["Contest"],
                    reporting_unit=reference_result["ReportingUnit"],
                    vote_type=reference_result["VoteType"],
                )
        if not count_from_db == reference_result["Count"]:
           wrong_results.append({**reference_result, **{"count_from_db":count_from_db}})
        else: correct_results.append(reference_result)
    if wrong_results:
        print(f"\nwrong results:\n{wrong_results}\n\ncorrect results:\n{correct_results}")
    assert wrong_results == list()


