#!/bin/bash
echo Backing up terrygon
if [ ! -d "backups" ]
then
	mkdir backups
fi

docker exec terrygon_postgres /usr/bin/pg_dump -U terrygon terrygon > backups/terrygon_$(date +"%Y_%m_%d").bak
echo Backing up complete
