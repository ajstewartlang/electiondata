import os
import os.path

from electiondata import (
    database as db,
    munge as m,
    userinterface as ui,
    constants,
)
import pandas as pd
from pandas.api.types import is_numeric_dtype
from typing import Optional, Dict, Any, List
import numpy as np
from pathlib import Path
import inspect
import psycopg2
from sqlalchemy.orm import Session


def recast_options(
    options: Dict[str, str], types: Dict[str, str], munger_name: str
) -> (dict, Optional[Dict[str, Any]]):
    """Convert a dictionary <options> of string parameter values to typed objects,
    where type is determined by <types>"""
    err: Optional[Dict[str, Any]] = None
    keys = {k for k in options.keys() if k in types.keys()}
    for k in keys:
        if options[k]:
            if types[k] in ["int", "integer"]:
                try:
                    options[k] = int(options[k])
                except Exception:
                    options[k] = None
                    err = ui.add_new_error(
                        err,
                        "warn-munger",
                        munger_name,
                        f"{k} should be integer but isn't: {options[k]}",
                    )
            elif types[k] == "list-of-integers":
                try:
                    options[k] = [int(s) for s in options[k].split(",")]
                except Exception:
                    options[k] = list()
                    err = ui.add_new_error(
                        err,
                        "warn-munger",
                        munger_name,
                        f"{k} should be list of integers but isn't: {options[k]}",
                    )
            elif types[k] == "str":
                if options[k] == "":
                    # null string is read as None
                    options[k] = None
            elif types[k] == "list-of-strings":
                if options[k] != "":
                    try:
                        options[k] = [s for s in options[k].split(",")]
                    except Exception:
                        options[k] = list()
                        err = ui.add_new_error(
                            err,
                            "warn-munger",
                            munger_name,
                            f"{k} should be list of strings but isn't: {options[k]}",
                        )
                # if the string is empty, assign an empty list
                else:
                    options[k] = list()

            elif types[k] == "string-with-opt-list" and k == "count_location":
                if not options["count_location"]:
                    # if we're munging a lookup file
                    pass
                elif options["file_type"] in ["xml", "json-nested"]:
                    # nothing needs to be broken out for these file types
                    pass
                elif options[k].split(":")[0] == "by_name":
                    options["count_fields_by_name"] = [
                        s for s in options[k][8:].split(",")
                    ]
                    options[k] = "by_name"
                elif options[k].split(":")[0] == "by_number":
                    options["count_column_numbers"] = [
                        int(s) for s in options[k][10:].split(",")
                    ]
                    options[k] = "by_number"
    return options, err


def check_dictionary(dictionary_path: str) -> Optional[dict]:
    err = None
    dictionary_dir = Path(dictionary_path).parent.name

    # dedupe the dictionary
    clean_and_dedupe(dictionary_path, clean_candidates=True)
    # check that no entry is null
    df = pd.read_csv(dictionary_path, **constants.standard_juris_csv_reading_kwargs)
    null_mask = df.T.isnull().any()
    if null_mask.any():
        # drop null rows and report error
        err = ui.add_new_error(
            err,
            "jurisdiction",
            dictionary_dir,
            f"dictionary.txt has some null entries:\n{df[null_mask]}",
        )
        df = df[~null_mask]

    # check that cdf_element-raw_identifier_value pairs are unique
    two_column_df = df[["cdf_element", "raw_identifier_value"]]
    dupes_df, _ = ui.find_dupes(two_column_df)
    if not dupes_df.empty:
        err = ui.add_new_error(
            err,
            "jurisdiction",
            dictionary_dir,
            f"dictionary.txt has more than one entry for each of these:\n {dupes_df}",
        )
    # check that there are no candidate dupes after regularization
    cands = two_column_df[two_column_df.cdf_element == "Candidate"].copy()
    cands["regular"] = m.regularize_candidate_names(cands.raw_identifier_value)
    dupe_reg = list()
    for reg in cands.regular.unique():
        all_match = cands[cands.regular == reg].copy()
        if all_match.shape[0] > 1:
            dupe_reg.append(
                f"{reg} is regular version of: {list(all_match.raw_identifier_value.unique())}"
            )
    if dupe_reg:
        dupe_str = "\n".join(dupe_reg)
        err = ui.add_new_error(
            err,
            "jurisdiction",
            dictionary_dir,
            f"Some raw candidate names match after regularization, "
            f"so are effectively dupes and should be deduped.:\n{dupe_str}",
        )
    return err


def ensure_jurisdiction_dir(
    repository_content_root, juris_system_name: str, ignore_empty: bool = False
) -> Optional[dict]:
    # create directory if it doesn't exist
    juris_path = os.path.join(
        repository_content_root, "jurisdictions", juris_system_name
    )
    try:
        Path(juris_path).mkdir(parents=True)
    except FileExistsError:
        pass
    else:
        print(f"Directory created: {juris_path}")

    # ensure the contents of the jurisdiction directory are correct
    err = ensure_juris_files(
        repository_content_root, juris_path, ignore_empty=ignore_empty
    )
    return err


def ensure_juris_files(
    repository_content_root, juris_path: str, ignore_empty: bool = False
) -> Optional[dict]:
    """Check that the jurisdiction files are complete and consistent with one another.
    Check for extraneous files in Jurisdiction directory.
    Assumes Jurisdiction directory exists. Assumes dictionary.txt is in the template file"""

    # package possible errors from this function into a dictionary and return them
    err = None
    juris_name = Path(juris_path).name
    juris_true_name = juris_name.replace("-", " ")

    templates_dir = os.path.join(
        repository_content_root, "jurisdictions/000_jurisdiction_templates"
    )
    # notify user of any extraneous files
    extraneous = [
        f
        for f in os.listdir(juris_path)
        if f not in os.listdir(templates_dir) and f[0] != "."
    ]
    if extraneous:
        err = ui.add_new_error(
            err,
            "jurisdiction",
            juris_name,
            f"extraneous_files_in_juris_directory {extraneous}",
        )

    template_list = [x[:-4] for x in os.listdir(templates_dir)]

    # reorder template_list, so that first things are created first
    ordered_list = ["dictionary", "ReportingUnit", "Office", "CandidateContest"]
    template_list = ordered_list + [x for x in template_list if x not in ordered_list]

    # ensure necessary all files exist
    for juris_file in template_list:
        cf_path = os.path.join(juris_path, f"{juris_file}.txt")
        created = False
        # if file does not already exist in jurisdiction directory, create from template and invite user to fill
        template_path = os.path.join(templates_dir, f"{juris_file}.txt")
        try:
            if os.path.isfile(template_path):
                temp = pd.read_csv(
                    template_path, **constants.standard_juris_csv_reading_kwargs
                )
            else:
                err = ui.add_new_error(
                    err,
                    "" "system",
                    f"{Path(__file__).absolute().parents[0].name}.{inspect.currentframe().f_code.co_name}",
                    f"Template file {template_path} does not exist",
                )
                temp = pd.DataFrame()  # for syntax checker
        except pd.errors.EmptyDataError:
            if not ignore_empty:
                err = ui.add_new_error(
                    err,
                    "system",
                    f"{Path(__file__).absolute().parents[0].name}.{inspect.currentframe().f_code.co_name}",
                    f"Template file {template_path} has no contents",
                )
            temp = pd.DataFrame()

        # if file does not exist
        if not os.path.isfile(cf_path):
            # create the file
            temp.to_csv(
                cf_path, sep="\t", index=False, encoding=constants.default_encoding
            )
            created = True

        # if file exists, check format against template
        if not created:
            try:
                cf_df = pd.read_csv(
                    os.path.join(juris_path, f"{juris_file}.txt"),
                    **constants.standard_juris_csv_reading_kwargs,
                )
            except pd.errors.ParserError as pe:
                err = ui.add_new_error(
                    err,
                    "jurisdiction",
                    juris_name,
                    f"Error reading file {juris_file}.txt: {pe}",
                )
                return err

            if set(cf_df.columns) != set(temp.columns):
                print(juris_file)
                cols = "\t".join(temp.columns.to_list())
                err = ui.add_new_error(
                    err,
                    "jurisdiction",
                    juris_name,
                    f"Columns of {juris_file}.txt need to be (tab-separated):\n {cols}\n",
                )

            if juris_file == "dictionary":
                new_err = check_dictionary(cf_path)
                err = ui.consolidate_errors([err, new_err])

            else:
                # dedupe the file
                clean_and_dedupe(cf_path, clean_candidates=True)

                # TODO check for lines that are too long

                # check for problematic null entries
                null_columns = check_nulls(
                    juris_file,
                    cf_path,
                    os.path.join(repository_content_root, "electiondata"),
                )
                if null_columns:
                    err = ui.add_new_error(
                        err,
                        "jurisdiction",
                        juris_name,
                        f"Null entries in {juris_file} in columns {null_columns}",
                    )

                # check uniqueness of name field
                ambiguous_names = find_ambiguous_names(juris_file, cf_path)
                if ambiguous_names:
                    readable_list = "\n".join(ambiguous_names)
                    err = ui.add_new_error(
                        err,
                        "jurisdiction",
                        juris_name,
                        f"Some names are ambiguous, appearing in more than one row in {juris_file}.txt:"
                        f"\n{readable_list}",
                    )

    # check dependencies
    for juris_file in [x for x in template_list if x != "dictionary"]:
        # check dependencies
        d, new_err = check_dependencies(juris_path, juris_file, repository_content_root)
        if new_err:
            err = ui.consolidate_errors([err, new_err])

    # check ReportingUnit.txt for internal consistency
    new_err = check_ru_file(juris_path, juris_true_name)
    if new_err:
        err = ui.consolidate_errors([err, new_err])
    return err


def find_ambiguous_names(element: str, cf_path: str) -> List[str]:
    name_field = db.get_name_field(element)
    df = pd.read_csv(cf_path, **constants.standard_juris_csv_reading_kwargs)
    ambiguous_names = [
        name
        for name in df[name_field].unique()
        if df[df[name_field] == name].shape[0] > 1
    ]
    return ambiguous_names


def check_ru_file(juris_path: str, juris_true_name: str) -> Optional[dict]:
    err = None
    ru = get_element(juris_path, "ReportingUnit")

    # create set of all parents, all lead rus
    parents = set()
    leadings = set()
    for _, r in ru.iterrows():
        components = r["Name"].split(";")
        parents.update(
            {";".join(components[: j + 1]) for j in range(len(components) - 1)}
        )
        leadings.update({components[0]})

    # identify and report parents that are missing from ReportingUnit.txt
    missing = [p for p in parents if p not in ru["Name"].unique()]
    missing.sort(reverse=True)
    if missing:
        m_str = "\n".join(missing)
        err = ui.add_new_error(
            err,
            "jurisdiction",
            Path(juris_path).name,
            f"Some parent reporting units are missing from ReportingUnit.txt:\n{m_str}",
        )

    # check that all reporting units start with true name
    bad = [j for j in leadings if j != juris_true_name]
    if bad:
        bad.sort(reverse=True)
        bad_str = "\n".join(bad)
        err = ui.add_new_error(
            err,
            "jurisdiction",
            Path(juris_path).name,
            f"Every ReportingUnit should start with the jurisdiction name. These do not:\n{bad_str}",
        )

    # check that there are no duplicate Names
    ru_freq = ru.groupby(["Name"]).count()
    duped = ru_freq[ru_freq["ReportingUnitType"] > 1]
    if not duped.empty:
        dupe_str = "\n".join(list(duped.index.unique()))
        err = ui.add_new_error(
            err,
            "jurisdiction",
            Path(juris_path).name,
            f"\nReportingUnit Names must be unique. These are listed on more than one row:\n{dupe_str}",
        )

    return err


def clean_and_dedupe(f_path: str, clean_candidates=False):
    """Dedupe the file, removing any leading or trailing whitespace and compressing any internal whitespace"""
    # TODO allow specification of unique constraints
    df = pd.read_csv(f_path, **constants.standard_juris_csv_reading_kwargs)

    if clean_candidates:
        if ("cdf_element" in df.columns) and (
            "raw_identifier_value" in df.columns
        ):  # for dictionary files
            mask = df["cdf_element"] == "Candidate"
            df.loc[mask, "raw_identifier_value"] = m.regularize_candidate_names(
                df.loc[mask, "raw_identifier_value"]
            )
            df.loc[mask, "cdf_internal_name"] = m.regularize_candidate_names(
                df.loc[mask, "cdf_internal_name"]
            )
        elif "BallotName" in df.columns:  # for Candidate files
            df["BallotName"] = m.regularize_candidate_names(df["BallotName"])

    if set(df.columns) == {
        "raw_identifier_value",
        "cdf_internal_name",
        "cdf_element",
    }:  # for dictionary files
        # get rid of lines with null information
        df = df[
            df["cdf_internal_name"].notnull() | df["raw_identifier_value"].notnull()
        ]

    # remove none or unknown Party in file
    if Path(f_path).name == "Party.txt":
        df = df[df.Name != "none or unknown"]
    for c in df.columns:
        if not is_numeric_dtype(df.dtypes[c]):
            df[c].fillna("", inplace=True)
            try:
                df[c] = df[c].apply(m.compress_whitespace)
            except Exception:
                # failure shouldn't break anything
                print(f"No whitespace compression on column {c} of {f_path}")
                pass
    dupes_df, df = ui.find_dupes(df)
    if not dupes_df.empty:
        df.to_csv(f_path, sep="\t", index=False, encoding=constants.default_encoding)
    return


def check_nulls(element, f_path, project_root):
    # TODO write description
    # TODO automatically drop null rows
    nn_path = os.path.join(
        project_root,
        "CDF_schema_def_info",
        "elements",
        element,
        "not_null_fields.txt",
    )
    not_nulls = pd.read_csv(nn_path, sep="\t", encoding=constants.default_encoding)
    df = pd.read_csv(f_path, **constants.standard_juris_csv_reading_kwargs)

    problem_columns = []

    for nn in not_nulls.not_null_fields.unique():
        # if nn is an Id, name in jurisdiction file is element name
        if nn[-3:] == "_Id":
            nn = nn[:-3]
        n = df[df[nn].isnull()]
        if not n.empty:
            problem_columns.append(nn)
            # drop offending rows
            df = df[df[nn].notnull()]

    return problem_columns


def check_dependencies(juris_dir, element, repository_content_root) -> (list, dict):
    """Looks in <juris_dir> to check that every dependent column in <element>.txt
    is listed in the corresponding jurisdiction file. Note: <juris_dir> assumed to exist.
    """
    err = None
    changed_elements = list()
    juris_name = Path(juris_dir).name
    d = juris_dependency_dictionary()
    f_path = os.path.join(juris_dir, f"{element}.txt")
    try:
        element_df = pd.read_csv(f_path, **constants.standard_juris_csv_reading_kwargs)
    except FileNotFoundError:
        err = ui.add_new_error(
            err,
            "system",
            f"{Path(__file__).absolute().parents[0].name}.{inspect.currentframe().f_code.co_name}",
            f"file doesn't exist: {f_path}",
        )
        return changed_elements, err

    # Find all dependent columns
    dependent = [c for c in element_df.columns if c in d.keys()]
    changed_elements = set()
    for c in dependent:
        target = d[c]
        ed = (
            pd.read_csv(
                os.path.join(juris_dir, f"{element}.txt"),
                **constants.standard_juris_csv_reading_kwargs,
            )
            .fillna("")
            .loc[:, c]
            .unique()
        )

        # create list of elements, removing any nulls
        # # look for required other element in the jurisdiction's directory; if not there, use global
        if os.path.isfile(os.path.join(juris_dir, f"{target}.txt")):
            target_path = os.path.join(juris_dir, f"{target}.txt")
        else:
            target_path = os.path.join(
                repository_content_root,
                "jurisdictions",
                "000_for_all_jurisdictions",
                f"{target}.txt",
            )
            if not os.path.isfile(target_path):
                err = ui.add_new_error(
                    err,
                    "jurisdiction",
                    "all jurisdictions",
                    f"{target}.txt file missing from both {juris_dir} and "
                    f"{os.path.join(repository_content_root, 'electiondata', '000_for_all_jurisdictions')}",
                )
                return changed_elements, err
        ru = list(
            pd.read_csv(
                target_path,
                **constants.standard_juris_csv_reading_kwargs,
            )
            .fillna("")
            .loc[:, db.get_name_field(target)]
        )
        try:
            ru.remove(np.nan)
        except ValueError:
            pass

        missing = [x for x in ed if x not in ru]
        # if the only missing is null or blank
        if len(missing) == 1 and missing == [""]:
            # exclude PrimaryParty, which isn't required to be not-null
            if c != "PrimaryParty":
                err = ui.add_new_error(
                    err, "jurisdiction", juris_name, f"Some {c} are null."
                )
        elif missing:
            changed_elements.add(element)
            changed_elements.add(target)
            m_str = "\n".join(missing)
            err = ui.add_new_error(
                err,
                "jurisdiction",
                juris_name,
                f"Every {c} in {element}.txt must be in {target}.txt. Offenders are:\n{m_str}",
            )

    return changed_elements, err


def juris_dependency_dictionary():
    """Certain fields in jurisdiction files refer to other jurisdiction files.
    E.g., ElectionDistricts are ReportingUnits"""
    d = {
        "ElectionDistrict": "ReportingUnit",
        "Office": "Office",
        "PrimaryParty": "Party",
        "Party": "Party",
        "Election": "Election",
    }
    return d


def load_juris_dframe_into_cdf(
    session,
    element,
    all_juris_path,
    juris_true_name: str,
    juris_system_name: str,
    err: Optional[dict],
    on_conflict: str = "NOTHING",
) -> Optional[dict]:
    """TODO"""

    # define paths
    project_root = Path(__file__).parents[1].absolute()
    cdf_schema_def_dir = os.path.join(
        project_root,
        "CDF_schema_def_info",
    )
    element_file = os.path.join(all_juris_path, juris_system_name, f"{element}.txt")
    fk_file = os.path.join(cdf_schema_def_dir, "elements", element, "foreign_keys.txt")

    # fail if <element>.txt does not exist
    if not os.path.exists(element_file):
        err = ui.add_new_error(
            err,
            "jurisdiction",
            juris_system_name,
            f"File {element}.txt not found",
        )
        return err

    clean_and_dedupe(element_file, clean_candidates=True)

    # read info from <element>.txt, filling null fields with 'none or unknown'
    df = pd.read_csv(
        element_file, **constants.standard_juris_csv_reading_kwargs
    ).fillna("none or unknown")
    # TODO check that df has the right format

    # add 'none or unknown' record
    df = add_none_or_unknown(df)

    # dedupe df
    dupes, df = ui.find_dupes(df)
    if not dupes.empty:
        err = ui.add_new_error(
            err,
            "warn-jurisdiction",
            juris_system_name,
            f"\nDuplicates were found in {element}.txt",
        )

    # get Ids for any foreign key (or similar) in the table, e.g., Party_Id, etc.
    if os.path.isfile(fk_file):
        foreign_keys = pd.read_csv(fk_file, sep="\t", index_col="fieldname")

        for fn in foreign_keys.index:
            ref = foreign_keys.loc[
                fn, "refers_to"
            ]  # NB: juris elements have no multiple referents (as joins may)
            col_map = {fn[:-3]: db.get_name_field(ref)}
            df = db.append_id_to_dframe(session.bind, df, ref, col_map=col_map).rename(
                columns={f"{ref}_Id": fn}
            )

    # commit info in df to corresponding cdf table to db
    new_err = db.insert_to_cdf_db(
        session.bind,
        df,
        element,
        "jurisdiction",
        juris_true_name,
        on_conflict=on_conflict,
    )
    if new_err:
        err = ui.consolidate_errors([err, new_err])
    return err


def system_name_from_true_name(true_name: str) -> str:
    """Replaces any spaces with hyphens"""
    return true_name.replace(" ", "-")


def add_none_or_unknown(df: pd.DataFrame, contest_type: str = None) -> pd.DataFrame:
    new_row = dict()
    for c in df.columns:
        if c == "contest_type":
            new_row[c] = contest_type
        elif c == "NumberElected":
            new_row[c] = 0
        elif df[c].dtype == "O":
            new_row[c] = "none or unknown"
        elif pd.api.types.is_numeric_dtype(df[c]):
            new_row[c] = 0
    # append row to the dataframe
    df = df.append(new_row, ignore_index=True)
    return df


def load_or_update_juris_to_db(
    session: Session,
    repository_content_root: str,
    juris_true_name: str,
    juris_system_name: str,
) -> Optional[dict]:
    """Load info from each element in the Jurisdiction's directory into the db.
    On conflict, update the db to match the files in the Jurisdiction's directory"""
    # load all from Jurisdiction directory (except Contests, dictionary, remark)
    juris_elements = ["ReportingUnit", "Office", "Party", "Candidate"]

    err = None
    for element in juris_elements:
        # read df from Jurisdiction directory
        new_err = load_juris_dframe_into_cdf(
            session,
            element,
            os.path.join(repository_content_root, "jurisdictions"),
            juris_true_name,
            juris_system_name,
            err,
            on_conflict="UPDATE",
        )
        err = ui.consolidate_errors([err, new_err])
        if ui.fatal_error(new_err):
            return err

    # Load CandidateContests and BallotMeasureContests
    for contest_type in ["BallotMeasure", "Candidate"]:
        new_err = load_or_update_contests(
            session.bind,
            os.path.join(repository_content_root, "jurisdictions", juris_system_name),
            juris_true_name,
            contest_type,
            err,
        )
        err = ui.consolidate_errors([err, new_err])
    return err


def load_or_update_contests(
    engine,
    path_to_jurisdiction_dir,
    juris_true_name,
    contest_type: str,
    err: Optional[dict],
) -> Optional[dict]:
    # read <contest_type>Contests from jurisdiction folder
    element_fpath = os.path.join(path_to_jurisdiction_dir, f"{contest_type}Contest.txt")
    if not os.path.exists(element_fpath):
        err = ui.add_new_error(
            err,
            "jurisdiction",
            juris_true_name,
            f"file not found: {contest_type}Contest.txt",
        )
        return err
    df = pd.read_csv(
        element_fpath, **constants.standard_juris_csv_reading_kwargs
    ).fillna("none or unknown")

    # add contest_type column
    df = m.add_constant_column(df, "contest_type", contest_type)

    # add 'none or unknown' record
    df = add_none_or_unknown(df, contest_type=contest_type)

    # dedupe df
    dupes, df = ui.find_dupes(df)

    # insert into in Contest table
    # Structure of CandidateContest vs Contest table means there is nothing to update in the CandidateContest table.
    # TODO check handling of BallotMeasure contests -- do they need to be updated?
    new_err = db.insert_to_cdf_db(
        engine,
        df[["Name", "contest_type"]],
        "Contest",
        "jurisdiction",
        juris_true_name,
        on_conflict="NOTHING",
    )
    if new_err:
        err = ui.consolidate_errors([err, new_err])
        if ui.fatal_error(new_err):
            return err

    # append Contest_Id
    col_map = {"Name": "Name", "contest_type": "contest_type"}
    df = db.append_id_to_dframe(engine, df, "Contest", col_map=col_map)

    if contest_type == "BallotMeasure":
        # append ElectionDistrict_Id, Election_Id
        for fk, ref in [
            ("ElectionDistrict", "ReportingUnit"),
            ("Election", "Election"),
        ]:
            col_map = {fk: "Name"}
            df = (
                db.append_id_to_dframe(engine, df, ref, col_map=col_map)
                .rename(columns={f"{ref}_Id": f"{fk}_Id"})
                .drop(fk, axis=1)
            )

    else:
        # append Office_Id, PrimaryParty_Id
        for fk, ref in [("Office", "Office"), ("PrimaryParty", "Party")]:
            col_map = {fk: "Name"}
            df = db.append_id_to_dframe(engine, df, ref, col_map=col_map).rename(
                columns={f"{ref}_Id": f"{fk}_Id"}
            )

    # create entries in <contest_type>Contest table
    # commit info in df to <contest_type>Contest table to db
    try:
        new_err = db.insert_to_cdf_db(
            engine,
            df.rename(columns={"Contest_Id": "Id"}),
            f"{contest_type}Contest",
            "jurisdiction",
            juris_true_name,
            on_conflict="NOTHING",
        )
        if new_err:
            err = ui.consolidate_errors([err, new_err])
    except psycopg2.InternalError as ie:
        err = ui.add_new_error(
            err,
            "jurisdiction",
            juris_true_name,
            f"Contests not loaded to database (sql error {ie}). "
            f"Check CandidateContest.txt or BallotMeasureContest.txt for errors.",
        )
    return err


def primary(row: pd.Series, party: str, contest_field: str) -> str:
    try:
        pr = f"{row[contest_field]} ({party})"
    except KeyError:
        pr = None
    return pr


def get_element(juris_path: str, element: str) -> pd.DataFrame:
    """<juris> is path to jurisdiction directory. Info taken
    from <element>.txt file in that directory. If file doesn't exist,
    empty dataframe returned"""
    f_path = os.path.join(juris_path, f"{element}.txt")
    if os.path.isfile(f_path):
        element_df = pd.read_csv(
            f_path,
            sep="\t",
            dtype="object",
            encoding=constants.default_encoding,
        )
    else:
        element_df = pd.DataFrame()
    return element_df


def remove_empty_lines(df: pd.DataFrame, element: str) -> pd.DataFrame:
    """return copy of <df> with any contentless lines removed.
    For dictionary element, such lines may have a first entry (e.g., CandidateContest)"""
    working = df.copy()
    # remove all rows with nothing
    working = working[((working != "") & (working != '""')).any(axis=1)]

    if element == "dictionary":
        working = working[(working.iloc[:, 1:] != "").any(axis=1)]
    return working


def write_element(
    juris_path: str, element: str, df: pd.DataFrame, file_name=None
) -> dict:
    """<juris> is path to target directory. Info taken
    from <element>.txt file in that directory.
    <element>.txt is overwritten with info in <df>"""
    err = None
    # set name of target file
    if not file_name:
        file_name = f"{element}.txt"
    # dedupe the input df
    dupes_df, deduped = ui.find_dupes(df)

    if element == "dictionary":
        # remove empty lines
        deduped = remove_empty_lines(deduped, element)
    try:
        # write info to file (note: this overwrites existing info in file!)
        deduped.drop_duplicates().fillna("").to_csv(
            os.path.join(juris_path, file_name),
            index=False,
            sep="\t",
            encoding=constants.default_encoding,
        )
    except Exception as e:
        err = ui.add_new_error(
            err,
            "system",
            "REMOVEpreparation.write_element",
            f"Unexpected exception writing to file: {e}",
        )
    return err


def add_defaults(juris_path: str, juris_template_dir: str, element: str) -> dict:
    old = get_element(juris_path, element)
    new = get_element(juris_template_dir, element)
    err = write_element(juris_path, element, pd.concat([old, new]).drop_duplicates())
    return err


def add_candidate_contests(
    juris_path: str,
    df: pd.DataFrame,
    file_path: str,
) -> Optional[dict]:
    """
    Inputs:
        juris_path: str, path to directory containing info for jurisdiction
        df: pd.DataFrame, dataframe with info for candidate contests
            (ContestName,NumberElected,OfficeName,PrimaryParty,ElectionDistrict, ReportingUnitType)
        file_path: str, for error reporting, the path of the file from which the dataframe was taken

    Adds any contests in <df> to the CandidateContest file in <juris_path>, along with dependent info

    Returns:
        Optional[dict], error dictionary
    """
    err = None
    necessary_columns = {
        "ContestName",
        "NumberElected",
        "OfficeName",
        "PrimaryParty",
        "ElectionDistrict",
        "ReportingUnitType",
    }
    if necessary_columns.issubset(set(df.columns)):
        # read files (or return errors)
        df_dict = dict()
        path_dict = dict()
        for element in ["ReportingUnit", "Office", "CandidateContest"]:
            path_dict[element] = os.path.join(juris_path, f"{element}.txt")
            try:
                df_dict[element] = pd.read_csv(path_dict[element], sep="\t")
            except FileNotFoundError:
                err = ui.add_new_error(
                    err, "jurisdiction", juris_path, f"{element}.txt file not found"
                )
            except Exception as e:
                err = ui.add_new_error(
                    err, "jurisdiction", juris_path, f"Error reading {element}.txt: {e}"
                )
        if ui.fatal_error(err):
            return err

        # add to ReportingUnit if necessary
        mask = df.ElectionDistrict.notin(df_dict["ReportingUnit"].Name.unique())
        if mask.any():
            new = pd.concat(
                [
                    df[["ElectionDistrict", "ReportingUnitType"]].rename(
                        column={"ElectionDistrict": "Name"}
                    ),
                    df_dict["ReportingUnit"],
                ]
            )
            new.to_csv(path_dict["ReportingUnit"], sep="\t", index=False)

        # add to Office
        mask = df.OfficeName.notin(df_dict["Office"].Name.unique())
        if mask.any():
            new = pd.concat(
                [
                    df[["OfficeName", "ElectionDistrict"]].rename(
                        column={"OfficeName": "Name"}
                    )
                ]
            )
            new.to_csv(path_dict["Office"], sep="\t", index=False)

        # add to CandidateContest
        mask = df.ContestName.notin(cc.Name.unique())
        if mask.any():
            new = pd.concat(
                [
                    df[
                        ["ContestName", "NumberElected", "OfficeName", "PrimaryParty"]
                    ].rename(column={"OfficeName": "Office", "ContestName": "Name"})
                ]
            )
            new.to_csv(path_dict["CandidateContest"], sep="\t", index=False)
    else:
        err = ui.add_new_error(
            err,
            "file",
            file_path,
            f"Missing columns: {[col for col in necessary_columns if col not in df.columns]}",
        )
    return err
