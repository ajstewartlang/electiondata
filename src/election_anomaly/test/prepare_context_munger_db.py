import db_routines as dbr
import user_interface as ui
from sqlalchemy.orm import sessionmaker
import tkinter as tk
import os
import munge_routines as mr
import pandas as pd
import csv
import states_and_files as sf


if __name__ == '__main__':

	project_root = '/Users/Steph-Airbook/Documents/CampaignScientific/NSF2019/State_Data/results_analysis/src/'

	# initialize root widget for tkinter

	# pick db to use
	db_paramfile = '/Users/Steph-Airbook/Documents/CampaignScientific/NSF2019/database.ini'
	db_name = 'NC_5'

	# connect to db
	eng, meta = dbr.sql_alchemy_connect(paramfile=db_paramfile,db_name=db_name)
	Session = sessionmaker(bind=eng)
	sess = Session()

	juris_short_name = 'NC_TEST_5'
	juris = ui.pick_juris_from_filesystem(
		project_root,path_to_jurisdictions=os.path.join(project_root,'jurisdictions'),
		jurisdiction_name=juris_short_name)

	# TODO to test how CandidateContest gets into db
	for element in ['Office','CandidateContest']:
		source_df = pd.read_csv(os.path.join(juris.path_to_juris_dir,f'context/{element}.txt'),sep='\t')
		mr.load_context_dframe_into_cdf(sess,project_root,juris,source_df,element,
									os.path.join(project_root,'election_anomaly/CDF_schema_def_info'))

	# pick munger
	munger = ui.pick_munger(
		sess,munger_dir=os.path.join(project_root,'mungers'),
		root=project_root)

	# get datafile & info
	dfile_d, enum_d, raw_file = ui.pick_datafile(project_root,sess)
	if enum_d['_datafile_separator'] == 'tab':
		sep = '\t'
	elif enum_d['_datafile_separator'] == 'comma':
		sep = ','
	else:
		raise Exception(f'separator {enum_d["_datafile_separator"]} not recognized')

	# load new datafile
	encoding = dfile_d['encoding']
	if encoding == '':
		encoding = 'iso-8859-1'

	raw = pd.read_csv(
			raw_file,sep=sep,dtype=str,encoding=encoding,quoting=csv.QUOTE_MINIMAL,
			header=list(range(munger.header_row_count)))

	[raw,info_cols,num_cols] = mr.clean_raw_df(raw,munger)

	for element in ['ReportingUnit','Election','Party','CandidateContest','Candidate',
		'BallotMeasureContest']:
		munger.finalize_element(element,raw,juris,sess,project_root)
	eng.dispose()
	print('Done! (user_interface)')

	exit()