# TODO: set up entrypoint script for docker, handle error codes properly for restarting and shutting down.
while true
do
  python "$BOT_PATH/terrygon.py"
  exit_code=$?
  echo $exit_code
  if [ $exit_code -ne 0 ]
  then
    echo quitting
    break
  fi

done