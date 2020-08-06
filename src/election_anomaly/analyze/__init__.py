import csv
import os.path

import pandas as pd
from election_anomaly import user_interface as ui
from election_anomaly import munge_routines as mr
import datetime
import os
import numpy as np
import matplotlib.pyplot as plt
from pathlib import Path
from pandas.api.types import is_numeric_dtype
from election_anomaly import db_routines as dbr
import scipy.spatial.distance as dist
from scipy import stats



def child_rus_by_id(session,parents,ru_type=None):
	"""Given a list <parents> of parent ids (or just a single parent_id), return
	list containing all children of those parents.
	(By convention, a ReportingUnit counts as one of its own 'parents',)
	If (ReportingUnitType_Id,OtherReportingUnit) pair <rutype> is given,
	restrict children to that ReportingUnitType"""
	cruj = pd.read_sql_table('ComposingReportingUnitJoin',session.bind)
	children = list(cruj[cruj.ParentReportingUnit_Id.isin(parents)].ChildReportingUnit_Id.unique())
	if ru_type:
		assert len(ru_type) == 2,f'argument {ru_type} does not have exactly 2 elements'
		ru = pd.read_sql_table('ReportingUnit',session.bind,index_col='Id')
		right_type_ru = ru[(ru.ReportingUnitType_Id == ru_type[0]) & (ru.OtherReportingUnitType == ru_type[1])]
		children = [x for x in children if x in right_type_ru.index]
	return children


def create_rollup(
		cursor, target_dir: str, top_ru_id: int, sub_rutype_id: int,
		election_id: int, datafile_list=None, by='Id') -> str:
	"""<target_dir> is the directory where the resulting rollup will be stored.
	<election_id> identifies the election; <datafile_id_list> the datafile whose results will be rolled up.
	<top_ru_id> is the internal cdf name of the ReportingUnit whose results will be reported
	<sub_rutype_id> identifies the ReportingUnitType
	of the ReportingUnits used in each line of the results file
	created by the routine. (E.g., county or ward)
	<datafile_list> is a list of files, with entries from field <by> in _datafile table.
	If no <datafile_list> is given, return all results for the given election.
	"""

	if not datafile_list:
		datafile_list, e = dbr.data_file_list(cursor, [election_id], by='Id')
		if e:
			return e
		by = 'Id'
		if len(datafile_list) == 0:
			return f'No datafiles found for Election_Id {election_id}'

	# set exclude_total
	vote_type_list, err_str = dbr.vote_type_list(cursor, datafile_list, by=by)
	if err_str:
		return err_str
	elif len(vote_type_list) == 0:
		return f'No vote types found for datafiles with {by} in {datafile_list} '

	if len(vote_type_list) > 1 and 'total' in vote_type_list:
		exclude_total = True
	else:
		exclude_total = False

	# get names from ids
	top_ru = dbr.name_from_id(cursor,'ReportingUnit',top_ru_id).replace(" ","-")
	election = dbr.name_from_id(cursor,'Election',election_id).replace(" ","-")
	sub_rutype = dbr.name_from_id(cursor, 'ReportingUnitType', sub_rutype_id)

	# create path to export directory
	leaf_dir = os.path.join(target_dir, election, top_ru, f'by_{sub_rutype}')
	Path(leaf_dir).mkdir(parents=True, exist_ok=True)

	# prepare inventory
	inventory_file = os.path.join(target_dir,'inventory.txt')
	inv_exists = os.path.isfile(inventory_file)
	if inv_exists:
		inv_df = pd.read_csv(inventory_file,sep='\t')
		# check that header matches inventory_columns
		with open(inventory_file,newline='') as f:
			reader = csv.reader(f,delimiter='\t')
			file_header = next(reader)
			# TODO: offer option to delete inventory file
			assert file_header == inventory_columns, \
				f'Header of file {f} is\n{file_header},\ndoesn\'t match\n{inventory_columns}.'

	with open(inventory_file,'a',newline='') as csv_file:
		wr = csv.writer(csv_file,delimiter='\t')
		if not inv_exists:
			wr.writerow(inventory_columns)
		wr.writerow(inventory_values)

	print(f'Results exported to {out_file}')
	return


def create_scatter(session, jurisdiction_id, subdivision_type_id, 
            h_election_id, h_category, h_count_id, h_type,
			v_election_id, v_category, v_count_id, v_type):
	"""<target_dir> is the directory where the resulting rollup will be stored.
	<election_id> identifies the election; <datafile_id_list> the datafile whose results will be rolled up.
	<top_ru_id> is the internal cdf name of the ReportingUnit whose results will be reported
	<sub_rutype_id>,<sub_rutype_othertext> identifies the ReportingUnitType
	of the ReportingUnits used in each line of the results file
	created by the routine. (E.g., county or ward)
	If <exclude_total> is True, don't include 'total' CountItemType
	(unless 'total' is the only CountItemType)"""
	# Get name of db for error messages
	dfh = get_data_for_scatter(session, jurisdiction_id, subdivision_type_id, h_election_id, \
		h_category, h_count_id, h_type)
	dfv = get_data_for_scatter(session, jurisdiction_id, subdivision_type_id, v_election_id, \
		v_category, v_count_id, v_type)
	unsummed = pd.concat([dfh, dfv])
	# package into dictionary
	if h_count_id == -1:
		x = f'All {h_type}'
	elif h_type == 'candidates':
		x = dbr.name_from_id(session, 'Candidate', h_count_id) 
	elif h_type == 'contests':
		x = dbr.name_from_id(session, 'CandidateContest', h_count_id) 
	if v_count_id == -1:
		y = f'All {v_type}'
	elif v_type == 'candidates':
		y = dbr.name_from_id(session, 'Candidate', v_count_id) 
	elif v_type == 'contests':
		y = dbr.name_from_id(session, 'CandidateContest', v_count_id) 
	results = {
		"x-election": dbr.name_from_id(session, 'Election', h_election_id),
		"y-election": dbr.name_from_id(session, 'Election', v_election_id),
		"jurisdiction": dbr.name_from_id(session, 'ReportingUnit', jurisdiction_id),
		#"contest": dbr.name_from_id(session, 'CandidateContest', unsummed.iloc[0]['Contest_Id']),
		"subdivision_type": dbr.name_from_id(session, 'ReportingUnitType', subdivision_type_id),
		"x-count_item_type": h_category,
		"y-count_item_type": v_category,
		"x": x,
		"y": y,
		"counts": []
	}
	pivot_df = pd.pivot_table(unsummed, values='Count',
		index=['Name'], columns='Selection').reset_index()
	for i, row in pivot_df.iterrows():
		results['counts'].append({
			'name': row['Name'],
			'x': row[x],
			'y': row[y],
		})			
	# only keep the ones where there are an (x, y) to graph
	to_keep = []
	for result in results['counts']:
		if len(result) == 3: #need reporting unit, x, and y
			to_keep.append(result)
	results['counts'] = to_keep
	return results


def get_data_for_scatter(session, jurisdiction_id, subdivision_type_id, 
	election_id, count_item_type, filter_id, count_type):
	"""Since this could be data across 2 elections, grab data one election at a time"""
	db = session.bind.url.database

	# get names from ids
	top_ru = dbr.name_from_id(session,'ReportingUnit',jurisdiction_id).replace(" ","-")
	election = dbr.name_from_id(session,'Election',election_id).replace(" ","-")
	sub_rutype = dbr.name_from_id(session, 'ReportingUnitType', subdivision_type_id)

	# pull relevant tables
	df = {}
	for element in [
		'ElectionContestSelectionVoteCountJoin','VoteCount','ContestSelectionJoin',
		'ComposingReportingUnitJoin','Election','ReportingUnit',
		'ElectionContestJoin','CandidateContest','CandidateSelection','BallotMeasureContest',
		'BallotMeasureSelection','Office','Candidate']:
		# pull directly from db, using 'Id' as index
		df[element] = pd.read_sql_table(element,session.bind,index_col='Id')

	# pull enums from db, keeping 'Id as a column, not the index
	for enum in ["ReportingUnitType","CountItemType"]:
		df[enum] = pd.read_sql_table(enum,session.bind)

	#  limit to relevant Election-Contest pairs
	ecj = df['ElectionContestJoin'][df['ElectionContestJoin'].Election_Id == election_id]

	# create contest_selection dataframe, adding Contest, Selection and ElectionDistrict_Id columns
	contest_selection = df['ContestSelectionJoin'].merge(
		df['CandidateContest'],how='left',left_on='Contest_Id',right_index=True).rename(
		columns={'Name':'Contest','Id':'ContestSelectionJoin_Id'}).merge(
		df['CandidateSelection'],how='left',left_on='Selection_Id',right_index=True).merge(
		df['Candidate'],how='left',left_on='Candidate_Id',right_index=True).rename(
		columns={'BallotName':'Selection','CandidateContest_Id':'Contest_Id',
				'CandidateSelection_Id':'Selection_Id'}).merge(
		df['Office'],how='left',left_on='Office_Id',right_index=True)
	contest_selection = contest_selection[['Contest_Id','Contest','Selection_Id','Selection','ElectionDistrict_Id',
		'Candidate_Id']]
	if contest_selection.empty:
		contest_selection['contest_type'] = None
	else:
		contest_selection.loc[:,'contest_type'] = 'Candidate'

	# append contest_district_type column
	ru = df['ReportingUnit'][['ReportingUnitType_Id','OtherReportingUnitType']]
	contest_selection = contest_selection.merge(ru,how='left',left_on='ElectionDistrict_Id',right_index=True)
	contest_selection = mr.enum_col_from_id_othertext(contest_selection,'ReportingUnitType',df['ReportingUnitType'])
	contest_selection.rename(columns={'ReportingUnitType':'contest_district_type'},inplace=True)

	# Based on count_type param, we either filter on contest or candidate
	if count_type == 'candidates':
		filter_column = 'Candidate_Id'
	elif count_type == 'contests':
		filter_column = 'Contest_Id'
	
	# if the filter_id is -1, that means we want all of them and we'll do 
	# a group by later. otherwise, filter on the correct column
	if filter_id != -1:
		csj = contest_selection[contest_selection[filter_column].isin([filter_id])]
	else:
		csj = contest_selection

	# find ReportingUnits of the correct type that are subunits of top_ru
	sub_ru_ids = child_rus_by_id(session,[jurisdiction_id],ru_type=[subdivision_type_id, ''])
	if not sub_ru_ids:
		# TODO better error handling (while not sub_ru_list....)
		raise Exception(f'Database {db} shows no ReportingUnits of type {sub_rutype} nested inside {top_ru}')
	sub_ru = df['ReportingUnit'].loc[sub_ru_ids]

	# find all subReportingUnits of top_ru
	all_subs_ids = child_rus_by_id(session,[jurisdiction_id])

	# find all children of subReportingUnits
	children_of_subs_ids = child_rus_by_id(session,sub_ru_ids)
	ru_children = df['ReportingUnit'].loc[children_of_subs_ids]

def short_name(text,sep=';'):
	return text.split(sep)[-1]
	# check for any reporting units that should be included in roll-up but were missed
	# TODO list can be long and irrelevant. Instead list ReportingUnitTypes of the missing
	# missing = [str(x) for x in all_subs_ids if x not in children_of_subs_ids]
	# if missing:
	# TODO report these out to the export directory
	#	ui.report_problems(missing,msg=f'The following reporting units are nested in {top_ru["Name"]} '
	#							f'but are not nested in any {sub_rutype} nested in {top_ru["Name"]}')

	# limit to relevant vote counts
	ecsvcj = df['ElectionContestSelectionVoteCountJoin'][
		(df['ElectionContestSelectionVoteCountJoin'].ElectionContestJoin_Id.isin(ecj.index)) &
		(df['ElectionContestSelectionVoteCountJoin'].ContestSelectionJoin_Id.isin(csj.index))]

	# calculate specified dataframe with columns [ReportingUnit,Contest,Selection,VoteCount,CountItemType]
	#  1. create unsummed dataframe of results
	unsummed = ecsvcj.merge(
		df['VoteCount'],left_on='VoteCount_Id',right_index=True).merge(
		df['ComposingReportingUnitJoin'],left_on='ReportingUnit_Id',right_on='ChildReportingUnit_Id').merge(
		ru_children,left_on='ChildReportingUnit_Id',right_index=True).merge(
		sub_ru,left_on='ParentReportingUnit_Id',right_index=True,suffixes=['','_Parent'])
	unsummed.rename(columns={'Name_Parent':'ReportingUnit'},inplace=True)
	# add columns with names
	unsummed = mr.enum_col_from_id_othertext(unsummed,'CountItemType',df['CountItemType'])
	unsummed = unsummed.merge(contest_selection,how='left',left_on='ContestSelectionJoin_Id',right_index=True)

	# filter based on vote count type
	unsummed = unsummed[unsummed['CountItemType'] == count_item_type]
	
	# filter based on 

	# cleanup for purposes of flexibility
	unsummed = unsummed[['ReportingUnit', 'Count', 'Selection', 'Contest_Id', 'Candidate_Id']]
	unsummed.rename(columns={'ReportingUnit': 'Name'}, inplace=True)

	# if filter_id is -1, then that means we have all contests or candidates
	# so we need to group by
	if filter_id == -1:
		unsummed['Selection'] = f'All {count_type}'
		unsummed['Contest_Id'] = filter_id
		unsummed['Candidate_Id'] = filter_id

	if count_type == 'contests' and filter_id != -1:
		selection = dbr.name_from_id(session, 'CandidateContest', filter_id)
		unsummed['Selection'] = selection
	elif count_type == 'contests' and filter_id == -1:
		unsummed['Selection'] = 'All contests'

	columns = list(unsummed.drop(columns='Count').columns)
	unsummed = unsummed.groupby(columns)['Count'].sum().reset_index()

	return unsummed


def create_bar(session, top_ru_id, contest_type, contest, election_id, datafile_id_list):
	"""<target_dir> is the directory where the resulting rollup will be stored.
	<election_id> identifies the election; <datafile_id_list> the datafile whose results will be rolled up.
	<top_ru_id> is the internal cdf name of the ReportingUnit whose results will be reported
	<sub_rutype_id>,<sub_rutype_othertext> identifies the ReportingUnitType
	of the ReportingUnits used in each line of the results file
	created by the routine. (E.g., county or ward)
	If <exclude_total> is True, don't include 'total' CountItemType
	(unless 'total' is the only CountItemType)"""
	# Get name of db for error messages
	db = session.bind.url.database

	# get names from ids
	top_ru = dbr.name_from_id(session,'ReportingUnit',top_ru_id).replace(" ","-")
	election = dbr.name_from_id(session,'Election',election_id).replace(" ","-")

	# pull relevant tables
	df = {}
	for element in [
		'ElectionContestSelectionVoteCountJoin','VoteCount','ContestSelectionJoin',
		'ComposingReportingUnitJoin','Election','ReportingUnit',
		'ElectionContestJoin','CandidateContest','CandidateSelection','BallotMeasureContest',
		'BallotMeasureSelection','Office','Candidate']:
		# pull directly from db, using 'Id' as index
		df[element] = pd.read_sql_table(element,session.bind,index_col='Id')

	# pull enums from db, keeping 'Id as a column, not the index
	for enum in ["ReportingUnitType","CountItemType"]:
		df[enum] = pd.read_sql_table(enum,session.bind)

	#  limit to relevant Election-Contest pairs
	ecj = df['ElectionContestJoin'][df['ElectionContestJoin'].Election_Id == election_id]

	# create contest_selection dataframe, adding Contest, Selection and ElectionDistrict_Id columns
	contest_selection = df['ContestSelectionJoin'].merge(
		df['CandidateContest'],how='left',left_on='Contest_Id',right_index=True).rename(
		columns={'Name':'Contest','Id':'ContestSelectionJoin_Id'}).merge(
		df['CandidateSelection'],how='left',left_on='Selection_Id',right_index=True).merge(
		df['Candidate'],how='left',left_on='Candidate_Id',right_index=True).rename(
		columns={'BallotName':'Selection','CandidateContest_Id':'Contest_Id',
				'CandidateSelection_Id':'Selection_Id'}).merge(
		df['Office'],how='left',left_on='Office_Id',right_index=True)
	contest_selection = contest_selection[['Contest_Id','Contest','Selection_Id','Selection','ElectionDistrict_Id',
		'Candidate_Id']]
	if contest_selection.empty:
		contest_selection['contest_type'] = None
	else:
		contest_selection.loc[:,'contest_type'] = 'Candidate'

	# append contest_district_type column
	ru = df['ReportingUnit'][['ReportingUnitType_Id','OtherReportingUnitType']]
	contest_selection = contest_selection.merge(ru,how='left',left_on='ElectionDistrict_Id',right_index=True)
	contest_selection = mr.enum_col_from_id_othertext(contest_selection,'ReportingUnitType',df['ReportingUnitType'])
	contest_selection.rename(columns={'ReportingUnitType':'contest_district_type'},inplace=True)

	if contest_type:
		contest_selection = contest_selection[contest_selection['contest_district_type'] == contest_type]
	if contest:
		contest_selection = contest_selection[contest_selection['Contest'] == contest]
	# limit to relevant ContestSelection pairs
	contest_ids = ecj.Contest_Id.unique()
	csj = contest_selection[contest_selection.Contest_Id.isin(contest_ids)]

	# limit to relevant vote counts
	ecsvcj = df['ElectionContestSelectionVoteCountJoin'][
		(df['ElectionContestSelectionVoteCountJoin'].ElectionContestJoin_Id.isin(ecj.index)) &
		(df['ElectionContestSelectionVoteCountJoin'].ContestSelectionJoin_Id.isin(csj.index))]

	# Create data frame of all our results at all levels
	unsummed = ecsvcj.merge(
		df['VoteCount'],left_on='VoteCount_Id',right_index=True).merge(
		df['ComposingReportingUnitJoin'],left_on='ReportingUnit_Id',right_on='ChildReportingUnit_Id').merge(
		df['ReportingUnit'],left_on='ChildReportingUnit_Id',right_index=True).merge(
		df['ReportingUnit'],left_on='ParentReportingUnit_Id',right_index=True,suffixes=['','_Parent'])
	
	# add columns with names
	unsummed = mr.enum_col_from_id_othertext(unsummed,'CountItemType',df['CountItemType'])
	unsummed = unsummed.merge(contest_selection,how='left',left_on='ContestSelectionJoin_Id',right_index=True)

	# cleanup: Rename, drop a duplicated column
	rename = {
		'Name_Parent': 'ParentName',
		'ReportingUnitType_Id_Parent': 'ParentReportingUnitType_Id'
	}
	unsummed.rename(columns=rename, inplace=True)
	unsummed.drop(columns=['_datafile_Id', 'OtherReportingUnitType', 
		'ChildReportingUnit_Id', 'ElectionContestJoin_Id','OtherReportingUnitType_Parent', 
		'ContestSelectionJoin_Id'],
		inplace=True)
	unsummed = unsummed[unsummed['ParentReportingUnit_Id'] != top_ru_id]

	ranked = assign_anomaly_score(unsummed)
	ranked_margin = calculate_margins(ranked)
	votes_at_stake = calculate_votes_at_stake(ranked_margin)
	top_ranked = get_most_anomalous(votes_at_stake, 3)
	#return top_ranked

	# package into list of dictionary
	result_list = []
	ids = top_ranked['unit_id'].unique()
	for id in ids:
		temp_df = top_ranked[top_ranked['unit_id'] == id]

		candidates = temp_df['Candidate_Id'].unique()
		x = dbr.name_from_id(session, 'Candidate', candidates[0])
		y = dbr.name_from_id(session, 'Candidate', candidates[1]) 
		results = {
			"election": dbr.name_from_id(session, 'Election', election_id),
			"jurisdiction": dbr.name_from_id(session, 'ReportingUnit', top_ru_id),
			"contest": dbr.name_from_id(session, 'CandidateContest', temp_df.iloc[0]['Contest_Id']),
			# TODO: remove hard coded subdivision type
			"subdivision_type": dbr.name_from_id(session, 'ReportingUnitType', 
				temp_df.iloc[0]['ReportingUnitType_Id']),
			"count_item_type": temp_df.iloc[0]['CountItemType'],
			"x": x,
			"y": y,
			"margin": temp_df.iloc[0]['margins'],
			"votes_at_stake": temp_df.iloc[0]['max_votes_at_stake'], 
			"counts": []
		}

		pivot_df = pd.pivot_table(temp_df, values='Count',
			index=['Name'], columns='Selection').reset_index()
		for i, row in pivot_df.iterrows():
			results['counts'].append({
				'name': row['Name'],
				'x': row[x],
				'y': row[y],
			})			
		result_list.append(results)
		
	return result_list


def assign_anomaly_score(data):
	"""adds a new column called score between 0 and 1; 1 is more anomalous.
	Also adds a `unit_id` column which assigns a score to each unit of analysis
	that is considered. For example, we may decide to look at anomalies across each
	distinct combination of contest, reporting unit type, and vote type. Each 
	combination of those would get assigned an ID. This means rows may get added
	to the dataframe if needed."""

	# Group data by parent info. This works because each child is also its own
	# parent in the DB table
	grouped_df = data.groupby(['ParentReportingUnit_Id', 'ParentName', 
			'ParentReportingUnitType_Id', 'Candidate_Id',
            'CountItemType', 'Contest_Id', 'Contest', 'Selection', 
            'contest_type', 'contest_district_type'], as_index=False)['Count'].sum().reset_index()
	grouped_df.drop(columns='index', inplace=True)
	grouped_df.rename(columns={
		'ParentReportingUnit_Id': 'ReportingUnit_Id',
		'ParentName': 'Name',	
		'ParentReportingUnitType_Id': 'ReportingUnitType_Id'
	}, inplace=True)

	# assign unit_ids to contest, ru_type, and count type
	# currently this only looks at the most granular level, not rolled up
	#data = data[data['ReportingUnit_Id'] == data['ParentReportingUnit_Id']]
	df_unit = grouped_df[['Contest_Id', 'ReportingUnitType_Id', 'CountItemType']].drop_duplicates()
	df_unit = df_unit.reset_index()

	######### FOR TESTING PURPOSES ONLY!!!!! ###########
	df_unit = df_unit[df_unit['Contest_Id'] == 14949]


	df_unit['unit_id'] = df_unit.index
	df_with_units = grouped_df.merge(df_unit, how='left', on=['Contest_Id', 'ReportingUnitType_Id', 'CountItemType'])
	unit_ids = df_with_units['unit_id'].unique()
	df = pd.DataFrame()

	for unit_id in unit_ids:
		temp_df = df_with_units[df_with_units['unit_id'] == unit_id]
		# if there are more than 2 candidates, just take the top 2
		# TODO: do pairwise comparison against winner
		if len(temp_df['Selection'].unique()) > 2:
			contest_id = temp_df.iloc[0]['Contest_Id']
			reporting_unit_type_id = temp_df.iloc[0]['ReportingUnitType_Id']
			total_df = df_with_units[(df_with_units['Contest_Id'] == contest_id) &
						(df_with_units['CountItemType'] == 'total') &
						(df_with_units['ReportingUnitType_Id'] == reporting_unit_type_id)]
			counts = total_df.groupby('Selection')['Count'].sum().sort_values(ascending=False)
			top = list(counts.index[0:2])
			temp_df = temp_df[temp_df['Selection'].isin(top)]
		# pivot so each candidate gets own column
		pivot_df = pd.pivot_table(temp_df, values='Count', index=['ReportingUnit_Id'], \
			columns='Selection').sort_values('ReportingUnit_Id').reset_index()
		# filter out no votes
		pivot_df['sum'] = pivot_df.drop('ReportingUnit_Id', axis=1).sum(axis=1)
		pivot_df = pivot_df[pivot_df['sum'] > 100]
		if pivot_df.shape[0] >= 5:
			# keep the candidate column names only
			pivot_df_values = pivot_df.drop(columns=['ReportingUnit_Id', 'sum'])
			to_drop = pivot_df_values.columns
			# pass in proportions instead of raw vlaues
			row_totals = pivot_df_values.values.sum(axis=1)
			vote_proportions = np.array(np.divide(pivot_df_values, row_totals.reshape(-1, 1)))
			np.nan_to_num(vote_proportions, copy=False)
			# assign z score and then add back into final DF
			scored = euclidean_zscore(vote_proportions)
			#scored = density_score(vote_proportions)
			pivot_df['score'] = scored
			temp_df = temp_df.merge(pivot_df, how='left', on='ReportingUnit_Id') \
						.drop(columns=to_drop)
			df = pd.concat([df, temp_df])
	return df


def get_most_anomalous(data, n):
	"""gets the n contests with the highest votes_at_stake score"""
	# get rid of all contest-counttypes with 0 votes
	# not sure we really want to do this in final version
	zeros_df = data[['Contest_Id', 'ReportingUnitType_Id', 'CountItemType', 'ReportingUnit_Id', 'Count']]
	zeros_df = zeros_df.groupby(['Contest_Id', 'ReportingUnitType_Id', 'ReportingUnit_Id', 'CountItemType']).sum()
	zeros_df = zeros_df.reset_index()
	no_zeros = zeros_df[zeros_df['Count'] != 0]
	data = data.merge(no_zeros, how='inner', on=['Contest_Id', 'ReportingUnitType_Id', 'ReportingUnit_Id', 'CountItemType'])
	data.rename(columns={'Count_x':'Count'}, inplace=True)
	data.drop(columns=['Count_y'], inplace=True)

	# Now do the filtering on most anomalous
	df = data.groupby('unit_id')['votes_at_stake'].max().reset_index()
	df.rename(columns={'votes_at_stake': 'max_votes_at_stake'}, inplace=True)
	data = data.merge(df, on='unit_id')
	unique_scores = sorted(set(df['max_votes_at_stake']), reverse=True)
	top_scores = unique_scores[:n]
	result = data[data['max_votes_at_stake'].isin(top_scores)]

	# Eventually we want to return the winner and the most anomalous
	# for each contest grouping (unit). For now, just 2 random ones
	ids = result['unit_id'].unique()
	df = pd.DataFrame()
	for id in ids:
		temp_df = result[result['unit_id'] == id]
		#unique = temp_df['Candidate_Id'].unique()
		#candidates = unique[0:2]
		candidates = temp_df['Candidate_Id'].unique()
		candidate_df = temp_df[temp_df['Candidate_Id'].isin(candidates)]
		unique = candidate_df['ReportingUnit_Id'].unique()
		reporting_units = unique[0:8]
		df_final = candidate_df[candidate_df['ReportingUnit_Id'].isin(reporting_units)]. \
			sort_values(['ReportingUnit_Id', 'score'], ascending=False)
		df = pd.concat([df, df_final])
	return df


def euclidean_zscore(li):
    """Take a list of vectors -- all in the same R^k,
    returns a list of the z-scores of the vectors -- each relative to the ensemble"""
    distance_list = [sum([dist.euclidean(item,y) for y in li]) for item in li]
    if len(set(distance_list)) == 1:
        # if all distances are the same, which yields z-score nan values
        return [0]*len(li)
    else:
        return list(stats.zscore(distance_list))


def density_score(points):
	"""Take a list of vectors -- all in the same R^k,
	return a list of comparison of density with or without the anomaly"""
	density_list = [0] * len(points)
	x_order = list(points[:, 0])
	xs = points[:, 0]
	xs.sort()
	head, *tail = xs
	density = (tail[-2] - tail[0]) / (len(tail) - 1)
	total_density = (xs[-2] - xs[0]) / (len(xs) - 1)
	density_asc = total_density / density
	density_asc_xval = xs[0]

	# Sort in reverse order
	xs = xs[::-1]
	head, *tail = xs
	density = (tail[-2] - tail[0]) / (len(tail) - 1)
	total_density = (xs[-2] - xs[0]) / (len(xs) - 1)
	density_desc = total_density / density
	density_desc_xval = xs[0]
	if density_asc > density_desc:
		i = x_order.index(density_asc_xval)
		density_list[i] = density_asc
	else:
		i = x_order.index(density_desc_xval)
		density_list[i] = density_desc
	return density_list


def calculate_margins(data):
	return data


def calculate_votes_at_stake(data):
	"""Move the most anomalous pairing to the equivalent of the second-most anomalous
	and calculate the differences in votes that would be returned"""
	df = pd.DataFrame()
	unit_ids = data['unit_id'].unique()
	for unit_id in unit_ids:
		temp_df = data[data['unit_id'] == unit_id]
		if temp_df.shape[0] > 2:
			try:
				temp_df['abs_score'] = temp_df['score'].abs()
				temp_df.sort_values('abs_score', ascending=False, inplace=True)
				# The first 2 rows are the most anomalous candidate pairing
				anomalous_df = temp_df.iloc[0:2]
				# Resort so we have the DF back in order by scores
				temp_df.sort_values('score', ascending=False, inplace=True)
				# Now we need to know whether the original score was pos or neg
				is_positive = (anomalous_df.iloc[0]['score'] > 0)
				if is_positive:
					next_anomalous_df = temp_df[temp_df['score'] < anomalous_df.iloc[0]['score']][0:2]
				elif not is_positive:
					next_anomalous_df = temp_df[temp_df['score'] > anomalous_df.iloc[0]['score']][0:2]	
				anomalous_total = int(anomalous_df['Count'].sum())
				next_anomalous_total = int(next_anomalous_df['Count'].sum())
				candidate_1 = anomalous_df.iloc[0]['Candidate_Id']
				candidate_2 = anomalous_df.iloc[1]['Candidate_Id']
				candidate_1_cnt = anomalous_df[anomalous_df['Candidate_Id'] == candidate_1].iloc[0]['Count']
				candidate_2_cnt = anomalous_df[anomalous_df['Candidate_Id'] == candidate_2].iloc[0]['Count']
				candidate_1_prop = int(next_anomalous_df[next_anomalous_df['Candidate_Id'] == candidate_1].iloc[0]['Count']) / \
									int(next_anomalous_total)
				candidate_2_prop = int(next_anomalous_df[next_anomalous_df['Candidate_Id'] == candidate_2].iloc[0]['Count']) / \
									int(next_anomalous_total)
				margin = abs(candidate_1_prop * anomalous_total - candidate_1_cnt) + \
							abs(candidate_2_prop * anomalous_total - candidate_2_cnt)
				temp_df['votes_at_stake'] = margin / temp_df.iloc[0].margins
			except:
				temp_df['votes_at_stake'] = 0
		else:
			temp_df['votes_at_stake'] = 0
		df = pd.concat([df, temp_df])
	return df