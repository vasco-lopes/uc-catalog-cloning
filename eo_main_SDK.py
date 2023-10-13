# Databricks notebook source
# MAGIC %pip install databricks-sdk --upgrade
# MAGIC dbutils.library.restartPython()

# COMMAND ----------

old_external_location_name = 'eo000_ext_loc_ctg2'
old_catalog_name = 'eo000_ctg_ext_loc2'

storage_credential_name = 'field_demos_credential'
external_location_name = 'eo000_ext_loc_ctg5'
external_location_url = 'abfss://eo000ext5@oneenvadls.dfs.core.windows.net/'

new_catalog_name = 'eo000_ctg_ext_loc5'

# COMMAND ----------

from databricks.sdk import WorkspaceClient
from databricks.sdk.service import catalog
w = WorkspaceClient()
def parse_transfer_permissions(securable_type: catalog.SecurableType, old_securable_full_name: str, new_securable_full_name: str) -> int:
  try:
    grants = w.grants.get(securable_type=securable_type, full_name=f'{old_securable_full_name}')
    if grants.privilege_assignments == None:
      return 1
    changes = []
    for principal_permission_pair in grants.privilege_assignments:
      principal = principal_permission_pair.principal
      privileges = [eval('catalog.Privilege.'+privilege) for privilege in principal_permission_pair.privileges if (('VOL' not in privilege) and ('BROWSE' not in privilege))]
      changes.append(catalog.PermissionsChange(add=privileges, principal=principal))
    w.grants.update(full_name=new_securable_full_name, securable_type=securable_type, changes=changes)
    return 1
  except Exception as e:
    print(str(e))
    return 0


# COMMAND ----------

#Create new external location
external_location_created = w.external_locations.create(name=external_location_name,
                                                credential_name=storage_credential_name,
                                                comment="Created with SDK",
                                                url=external_location_url)

parse_transfer_permissions(securable_type=catalog.SecurableType.EXTERNAL_LOCATION, 
                           old_securable_full_name=old_external_location_name,
                           new_securable_full_name=external_location_created.name)                                            

# COMMAND ----------

#Create the new catalog
catalog_created = w.catalogs.create(name=new_catalog_name,
                            comment='Created by SDK',
                            storage_root=external_location_created.url)

parse_transfer_permissions(securable_type=catalog.SecurableType.CATALOG, 
                           old_securable_full_name=old_catalog_name,
                           new_securable_full_name=catalog_created.full_name)

# COMMAND ----------


db_list = w.schemas.list(old_catalog_name)

for db in db_list:
  #schema creation and migration
  if db.name == 'information_schema':
    continue

  print(f'Creating Database {db.name} and transferring permissions ... ', end='')
  if db.name == 'default':
    parse_transfer_permissions(securable_type=catalog.SecurableType.SCHEMA, 
                            old_securable_full_name=db.full_name,
                            new_securable_full_name=f'{catalog_created.name}.default')
  else:
    db_created = w.schemas.create(name=db.name,
                  catalog_name=catalog_created.full_name,
                  storage_root=db.storage_root)

    parse_transfer_permissions(securable_type=catalog.SecurableType.SCHEMA, 
                            old_securable_full_name=db.full_name,
                            new_securable_full_name=db_created.full_name)
  print('DONE!')
  
  #table creation and migraiton
  tbl_list = w.tables.list(catalog_name=old_catalog_name, schema_name=db.name)
  for tbl in tbl_list:
    if tbl.table_type == catalog.TableType.MANAGED:
      print(f'\t Cloning managed table {tbl.name} and transferring permissions ... ', end='')
      spark.sql(f'CREATE TABLE {db_created.full_name}.{tbl.name} DEEP CLONE {tbl.full_name}')

      tbl_created = w.tables.get(full_name=f'{db_created.full_name}.{tbl.name}')

      parse_transfer_permissions(securable_type=catalog.SecurableType.TABLE, 
                            old_securable_full_name=tbl.full_name,
                            new_securable_full_name=tbl_created.full_name)
      print('DONE!')


# COMMAND ----------


