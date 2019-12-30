#!/usr/bin/python3
# munge_routines/__init__.py
# under construction

import psycopg2
from psycopg2 import sql
from datetime import datetime


def id_and_name_from_external (cdf_schema,table,external_name,identifiertype_id,otheridentifiertype,con,cur,internal_name_field='Name'):
    ## find the internal db name and id from external identifier
            
    q = 'SELECT f."Id", f.{2} FROM {0}."ExternalIdentifier" AS e LEFT JOIN {0}.{1} AS f ON e."ForeignId" = f."Id" WHERE e."Value" =  %s AND e."IdentifierType_Id" = %s AND (e."OtherIdentifierType" = %s OR e."OtherIdentifierType" IS NULL OR e."OtherIdentifierType" = \'\'  );'       # *** ( ... OR ... OR ...) condition is kludge to protect from inconsistencies in OtherIdentifierType text when the IdentifierType is *not* other
    cur.execute(sql.SQL(q).format(sql.Identifier(cdf_schema),sql.Identifier(table),sql.Identifier(internal_name_field)),[external_name,identifiertype_id,otheridentifiertype])
    a = cur.fetchall()
    if a:
        return (a[0])
    else:
        return(None,None)


def upsert(schema,table,table_d,value_d,con,cur,mode='no_dupes'):
    ''' tables_d is a dict of table descriptions; value_d gives the values for the fields in the table (.e.g., value_d['Name'] = 'North Carolina;Alamance County'); return the upserted record. E.g., tables_d[table] = {'tablename':'ReportingUnit', 'fields':[{'fieldname':'Name','datatype':'TEXT'}],'enumerations':['ReportingUnitType','CountItemStatus'],'other_element_refs':[], 'unique_constraints':[['Name']],
    'not_null_fields':['ReportingUnitType_Id']
    modes with consequences: 'dupes_ok'
       } '''
    
    f_nt = [  [ dd['fieldname'],dd['datatype']+' %s'] for  dd in table_d['fields']] + [ [e+'_Id','INT %s'] for e in table_d['enumerations']]+ [['Other'+e,'TEXT %s'] for e in table_d['enumerations']]+ [[dd['fieldname'],'INT %s'] for dd in table_d['other_element_refs']]    # name-type pairs for each field
    ### remove any fields missing from the value_d parameter
    good_f_nt = [x for x in f_nt if x[0] in value_d.keys()]
    
    
    #f_names = [dd['fieldname'] for dd in table_d['fields']] + [e+'_Id' for e in table_d['enumerations']] + ['Other'+e for e in table_d['enumerations']] + [dd['fieldname'] for dd in table_d['other_element_refs']]
    
    ### error-check that fields in value_d are all in the table, and that no essentials are missing ***
    
    
    #f_names = list (set(f_name_type_pairs[][0]).intersection(value_d.keys()))   # *** do we need list?
    f_names = [good_f_nt[x][0] for x in range(len(good_f_nt))]
    f_val_slot_list = [good_f_nt[x][1] for x in range(len(good_f_nt))]
    f_vals = [ value_d[n] for n in f_names]
    #f_val_slot_list = [ dd['datatype']+' %s' for dd in table_d['fields'] ] + [ 'INT %s' for e in  table_d['enumerations']] + ['TEXT %s' for e in table_d['enumerations']]+ ['INT %s' for dd in table_d['other_element_refs']]

    cf_names = list(set().union(  *table_d['unique_constraints']))
    f_id_slot_list = ['{'+str(i+2)+'}' for i in range(len(f_names))]
    f_id_slots = ','.join( f_id_slot_list)
    if cf_names:
        cf_id_slots = ','.join( ['{'+str(i+2+len(f_names))+'}' for i in range(len(cf_names))] )
        cf_query_string = ' ON CONFLICT ('+cf_id_slots+') DO NOTHING '
    else:
        cf_query_string = ''
    f_val_slots = ','.join(f_val_slot_list)
    f_val_slots = f_val_slots.replace('INTEGER','').replace('INT','') ## *** kludge: postgres needs us to omit datatype for INTEGER, INT, not sure why. ***
    
    val_return_list = ['c.'+i for i in f_id_slot_list]
    
    q = 'WITH input_rows ('+f_id_slots+') AS (VALUES ('+f_val_slots+') ), ins AS (INSERT INTO {0}.{1} ('+f_id_slots+') SELECT * FROM input_rows '+ cf_query_string +' RETURNING "Id", '+f_id_slots+') SELECT "Id", ' + f_id_slots+', \'inserted\' AS source FROM ins UNION  ALL SELECT c."Id", '+  ','.join(val_return_list)  +',\'selected\' AS source FROM input_rows JOIN {0}.{1} AS c USING ('+ f_id_slots+');'
    
    
    sql_ids = [schema,table]   +f_names + cf_names
    format_args = [sql.Identifier(x) for x in sql_ids]
    strs = f_vals
    cur.execute(sql.SQL(q).format( *format_args ),strs)
    a =  cur.fetchall()
    con.commit()
    if len(a) == 0:
        bb = 1/0 # ***
        return("Error: nothing selected or inserted")
    elif len(a) == 1 or mode == 'dupes_ok':
        return(list(a[0]))
    else:
        bb = 1/0    # ***
        return("Error: multiple records found")
        





def format_type_for_insert(schema,table,txt,con,cur):
    ''' schema.table must have a "txt" field. This function returns a (type_id, othertype_text) pair; for types in the enumeration, returns (type_id for the given txt, ""), while for other types returns (type_id for "other",txt)  '''
    q = 'SELECT "Id" FROM {}.{} WHERE txt = %s'
    sql_ids = [schema,table]
    cur.execute(   sql.SQL(q).format( sql.Identifier(schema),sql.Identifier(table)),[txt,])
    a = cur.fetchall()
    if a:
        return([a[0][0],''])
    else:
        cur.execute(   sql.SQL(q).format( sql.Identifier(schema),sql.Identifier(table)),['other',])
        a = cur.fetchall()
        return([a[0][0],txt])



