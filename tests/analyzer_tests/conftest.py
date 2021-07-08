import pytest
import os
from pathlib import Path
from electiondata import data_exists, external_data_exists


def pytest_addoption(parser):
    parser.addoption(
        "--runtime",
        action="store",
        default=os.path.join(Path(__file__).parents[1].absolute(), "run_time.ini"),
    )


def pytest_generate_tests(metafunc):
    # This is called for every test. Only get/set command line arguments
    # if the argument is specified in the list of test "fixturenames".
    option_value = metafunc.config.option.runtime
    if "runtime" in metafunc.fixturenames and option_value is not None:
        metafunc.parametrize("runtime", [option_value])


@pytest.fixture(scope="session")
def ok(runtime):
    return {
        "ga16g": data_exists("2016 General", "Georgia", p_path=runtime),
        "ga18g": data_exists("2018 General", "Georgia", p_path=runtime),
        "ga20p": data_exists("2020 Primary", "Georgia", p_path=runtime),
        "nc18g": data_exists("2018 General", "North Carolina", p_path=runtime),
        "ak16g": data_exists("2016 General", "Alaska", p_path=runtime),
        "ga18census": external_data_exists("2018 General", "Georgia", p_path=runtime),
    }
